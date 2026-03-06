"""
Proxy Manager — rotacion automatica de proxies para evitar baneos.

Fuentes de proxies (en orden de prioridad):
1. Tor SOCKS5 con rotacion de circuitos (gratis, incluido en docker-compose)
2. Lista de proxies externos configurados manualmente
3. Proxies pagados (Bright Data, Oxylabs, etc.)
4. Sin proxy (directo) como fallback

Uso:
    from shared.proxy_manager import proxy_manager
    proxy = proxy_manager.get_proxy()          # Obtiene el siguiente proxy
    proxy_manager.mark_failed(proxy)           # Marca proxy como fallido
    proxy_manager.rotate_tor()                 # Nueva IP de Tor
"""
import random
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from config import settings, logger


class ProxyType(Enum):
    TOR = "tor"
    HTTP = "http"
    SOCKS5 = "socks5"
    DIRECT = "direct"


@dataclass
class Proxy:
    address: str
    port: int
    proxy_type: ProxyType
    username: str = ""
    password: str = ""
    fail_count: int = 0
    last_used: float = 0.0
    last_failed: float = 0.0

    @property
    def is_healthy(self) -> bool:
        # Si fallo hace menos de 60 segundos, no lo uses
        if self.last_failed > 0 and (time.time() - self.last_failed) < 60:
            return False
        # Si fallo mas de 5 veces seguidas, descartalo
        return self.fail_count < 5

    def as_selenium_arg(self) -> str:
        if self.proxy_type == ProxyType.TOR:
            return f"socks5://127.0.0.1:{self.port}"
        elif self.proxy_type == ProxyType.SOCKS5:
            if self.username:
                return f"socks5://{self.username}:{self.password}@{self.address}:{self.port}"
            return f"socks5://{self.address}:{self.port}"
        else:
            if self.username:
                return f"http://{self.username}:{self.password}@{self.address}:{self.port}"
            return f"http://{self.address}:{self.port}"

    def as_chrome_extension_proxy(self) -> dict:
        """For authenticated HTTP proxies that need Chrome extension."""
        return {
            "address": self.address,
            "port": self.port,
            "username": self.username,
            "password": self.password,
        }


class ProxyManager:
    def __init__(self):
        self._proxies: list[Proxy] = []
        self._lock = threading.Lock()
        self._tor_available = False
        self._initialized = False

    def init(self):
        """Initialize proxy sources. Called lazily on first use."""
        if self._initialized:
            return
        self._initialized = True

        # 1. Tor proxy (highest priority, free)
        if settings.tor_socks_port:
            tor_proxy = Proxy(
                address="127.0.0.1",
                port=settings.tor_socks_port,
                proxy_type=ProxyType.TOR,
            )
            self._proxies.append(tor_proxy)
            self._tor_available = True
            logger.info(f"Proxy: Tor SOCKS5 on port {settings.tor_socks_port}")

        # 2. Configured external proxies
        if settings.proxy_list:
            for proxy_str in settings.proxy_list.split(","):
                proxy_str = proxy_str.strip()
                if not proxy_str:
                    continue
                try:
                    proxy = self._parse_proxy(proxy_str)
                    self._proxies.append(proxy)
                    logger.info(f"Proxy: Added {proxy.proxy_type.value}://{proxy.address}:{proxy.port}")
                except Exception as e:
                    logger.warning(f"Proxy: Failed to parse '{proxy_str}': {e}")

        # 3. Bright Data / paid proxy
        if settings.brightdata_proxy_url:
            try:
                proxy = self._parse_proxy(settings.brightdata_proxy_url)
                self._proxies.append(proxy)
                logger.info("Proxy: Bright Data configured")
            except Exception as e:
                logger.warning(f"Proxy: Bright Data parse error: {e}")

        if not self._proxies:
            logger.warning("Proxy: No proxies configured — requests will go direct")

    def _parse_proxy(self, proxy_str: str) -> Proxy:
        """Parse proxy string: [type://][user:pass@]host:port"""
        proxy_type = ProxyType.HTTP
        if proxy_str.startswith("socks5://"):
            proxy_type = ProxyType.SOCKS5
            proxy_str = proxy_str[len("socks5://"):]
        elif proxy_str.startswith("http://"):
            proxy_type = ProxyType.HTTP
            proxy_str = proxy_str[len("http://"):]
        elif proxy_str.startswith("https://"):
            proxy_type = ProxyType.HTTP
            proxy_str = proxy_str[len("https://"):]

        username = ""
        password = ""
        if "@" in proxy_str:
            auth, proxy_str = proxy_str.rsplit("@", 1)
            if ":" in auth:
                username, password = auth.split(":", 1)

        host, port_str = proxy_str.rsplit(":", 1)
        return Proxy(
            address=host,
            port=int(port_str),
            proxy_type=proxy_type,
            username=username,
            password=password,
        )

    def get_proxy(self) -> Proxy | None:
        """Get next healthy proxy using round-robin with health checks."""
        self.init()
        with self._lock:
            healthy = [p for p in self._proxies if p.is_healthy]
            if not healthy:
                # Reset fail counts if everything is failed
                for p in self._proxies:
                    p.fail_count = 0
                    p.last_failed = 0
                healthy = self._proxies

            if not healthy:
                return None

            # Pick the least-recently-used healthy proxy
            proxy = min(healthy, key=lambda p: p.last_used)
            proxy.last_used = time.time()
            return proxy

    def mark_failed(self, proxy: Proxy):
        """Mark a proxy as failed."""
        with self._lock:
            proxy.fail_count += 1
            proxy.last_failed = time.time()
            logger.warning(f"Proxy failed ({proxy.fail_count}x): {proxy.proxy_type.value}://{proxy.address}:{proxy.port}")

    def mark_success(self, proxy: Proxy):
        """Reset fail count on success."""
        with self._lock:
            proxy.fail_count = 0

    def rotate_tor(self):
        """Request a new Tor circuit (new IP)."""
        if not self._tor_available:
            return False
        try:
            from stem import Signal
            from stem.control import Controller
            with Controller.from_port(port=settings.tor_control_port) as controller:
                if settings.tor_control_password:
                    controller.authenticate(password=settings.tor_control_password)
                else:
                    controller.authenticate()
                controller.signal(Signal.NEWNYM)
                logger.info("Proxy: Tor circuit rotated — new IP")
                time.sleep(3)  # Tor needs time to build new circuit
                return True
        except Exception as e:
            logger.error(f"Proxy: Tor rotation failed: {e}")
            return False

    def get_tor_ip(self) -> str | None:
        """Check current Tor exit IP."""
        if not self._tor_available:
            return None
        try:
            import httpx
            proxies = {"all://": f"socks5://127.0.0.1:{settings.tor_socks_port}"}
            resp = httpx.get("https://api.ipify.org?format=json", proxy=proxies["all://"], timeout=10)
            return resp.json().get("ip")
        except Exception as e:
            logger.debug(f"Proxy: Could not get Tor IP: {e}")
            return None

    @property
    def status(self) -> dict:
        """Return proxy pool status."""
        self.init()
        return {
            "total_proxies": len(self._proxies),
            "healthy_proxies": sum(1 for p in self._proxies if p.is_healthy),
            "tor_available": self._tor_available,
            "proxies": [
                {
                    "type": p.proxy_type.value,
                    "address": f"{p.address}:{p.port}",
                    "healthy": p.is_healthy,
                    "fail_count": p.fail_count,
                }
                for p in self._proxies
            ],
        }


# Singleton
proxy_manager = ProxyManager()
