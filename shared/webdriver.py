"""Shared Selenium WebDriver management — anti-detection + proxy rotation"""
import random
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from contextlib import contextmanager
import time

from config import settings, logger

# Rotate user agents to reduce fingerprinting
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]


@contextmanager
def get_driver(stealth: bool = False, use_proxy: bool = False):
    """
    Create a Chrome WebDriver instance.
    stealth=True  — anti-detection measures for Facebook/Instagram/TikTok
    use_proxy=True — route traffic through proxy (Tor or configured proxies)
    """
    driver = None
    proxy_obj = None
    try:
        options = Options()
        # Use system Chromium if available (Docker), else use webdriver-manager
        import os
        chrome_bin = os.environ.get("CHROME_BIN")
        chromedriver_path = os.environ.get("CHROMEDRIVER_PATH")
        if chrome_bin:
            options.binary_location = chrome_bin
        if settings.headless_browser:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"--window-size={settings.window_size}")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")

        # Rotate user agent
        ua = random.choice(_USER_AGENTS)
        options.add_argument(f"user-agent={ua}")

        if stealth:
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)
            options.add_argument("--lang=es-MX,es,en-US,en")

        # Proxy configuration
        if use_proxy:
            try:
                from shared.proxy_manager import proxy_manager
                proxy_obj = proxy_manager.get_proxy()
                if proxy_obj:
                    proxy_url = proxy_obj.as_selenium_arg()
                    options.add_argument(f"--proxy-server={proxy_url}")
                    logger.info(f"WebDriver using proxy: {proxy_obj.proxy_type.value}://{proxy_obj.address}:{proxy_obj.port}")
            except Exception as e:
                logger.warning(f"Proxy setup failed, going direct: {e}")

        if chromedriver_path:
            driver = webdriver.Chrome(service=Service(chromedriver_path), options=options)
        else:
            from webdriver_manager.chrome import ChromeDriverManager
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.set_page_load_timeout(settings.default_timeout)

        if stealth:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['es-MX', 'es', 'en-US', 'en']});
                    window.chrome = {runtime: {}};
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) =>
                        parameters.name === 'notifications'
                            ? Promise.resolve({state: Notification.permission})
                            : originalQuery(parameters);
                """
            })

        yield driver

        # Mark proxy as successful if we got here without exception
        if proxy_obj:
            from shared.proxy_manager import proxy_manager
            proxy_manager.mark_success(proxy_obj)

    except Exception as e:
        # Mark proxy as failed
        if proxy_obj:
            try:
                from shared.proxy_manager import proxy_manager
                proxy_manager.mark_failed(proxy_obj)
            except Exception:
                pass
        logger.error(f"Error setting up WebDriver: {e}")
        raise
    finally:
        if driver:
            driver.quit()


def human_delay(min_sec: float = 1.0, max_sec: float = 3.0):
    """Random delay to mimic human behavior."""
    time.sleep(random.uniform(min_sec, max_sec))


def is_blocked(driver) -> str | None:
    """
    Check if the current page shows a block/captcha/login wall.
    Returns a description of the block or None if page looks normal.
    """
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        url = driver.current_url.lower()

        # Facebook/Instagram login walls
        if "login" in url and ("facebook.com" in url or "instagram.com" in url):
            return "login_wall"

        # CAPTCHA detection
        if any(w in page_text for w in ["captcha", "verify you are human", "verifica que eres humano", "robot", "unusual traffic"]):
            return "captcha"

        # Rate limit / blocked
        if any(w in page_text for w in ["rate limit", "too many requests", "demasiadas solicitudes", "try again later"]):
            return "rate_limited"

        # Instagram specific
        if "instagram.com" in url and ("sorry, this page" in page_text or "esta pagina no esta disponible" in page_text):
            return "page_not_found"

        # Facebook specific
        if "facebook.com" in url and "you must log in" in page_text:
            return "login_required"

        # TikTok specific
        if "tiktok.com" in url and "verify" in page_text and "puzzle" in page_text:
            return "captcha"

        # Google CAPTCHA
        if "google.com" in url and ("unusual traffic" in page_text or "not a robot" in page_text):
            return "captcha"

    except Exception:
        pass
    return None


def handle_block_with_proxy_rotation(driver, block_type: str) -> bool:
    """
    When a block is detected, rotate proxy and return True if rotation was possible.
    The caller should retry with a new driver instance.
    """
    try:
        from shared.proxy_manager import proxy_manager
        if block_type in ("captcha", "rate_limited"):
            rotated = proxy_manager.rotate_tor()
            if rotated:
                logger.info(f"Rotated Tor circuit after {block_type}")
                return True
    except Exception as e:
        logger.debug(f"Proxy rotation not available: {e}")
    return False


def handle_facebook_dialogs(driver):
    dialog_buttons = [
        (By.XPATH, '//div[@aria-label="Close" and @role="button"]'),
        (By.XPATH, '//button[contains(text(), "Accept All")]'),
        (By.XPATH, '//button[contains(text(), "Accept")]'),
        (By.XPATH, '//button[contains(text(), "Aceptar")]'),
        (By.XPATH, '//button[contains(text(), "Continue")]'),
        (By.XPATH, '//button[contains(text(), "Continuar")]'),
        (By.XPATH, '//button[contains(text(), "Not Now")]'),
        (By.XPATH, '//button[contains(text(), "Ahora no")]'),
    ]
    try:
        for selector_type, selector in dialog_buttons:
            try:
                button = WebDriverWait(driver, 2).until(
                    EC.element_to_be_clickable((selector_type, selector))
                )
                button.click()
                time.sleep(1)
                logger.info(f"Clicked dialog button: {selector}")
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Error handling dialogs: {e}")


def wait_for_element(driver, by, selector, timeout=None):
    timeout = timeout or settings.default_timeout
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, selector))
    )


def wait_for_clickable(driver, by, selector, timeout=None):
    timeout = timeout or settings.default_timeout
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, selector))
    )
