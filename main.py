"""
Vulcan — Unified OSINT Platform
Consolidates: Vulcan, Hades, nyx-crawler, Hugin, Skadi
Port 8000 | FastAPI + lifespan
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings, logger

# ── Module status registry ──
module_status: dict[str, dict] = {}


def _set_status(name: str, ok: bool, detail: str = ""):
    module_status[name] = {"available": ok, "detail": detail}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    # 1. RavenDB (SANS module)
    try:
        from modules.sans.ravendb_client import init_ravendb
        init_ravendb()
        _set_status("ravendb", True)
    except Exception as e:
        logger.warning(f"RavenDB init failed (SANS degraded): {e}")
        _set_status("ravendb", False, str(e))

    # 2. Intelligence services (graceful degradation)
    try:
        from modules.intelligence import init_services
        intel_status = init_services()
        for svc, status in intel_status.items():
            _set_status(f"intelligence.{svc}", status["ok"], status.get("detail", ""))
    except Exception as e:
        logger.warning(f"Intelligence init failed (module degraded): {e}")
        _set_status("intelligence", False, str(e))

    # 3. Scheduler
    if settings.scheduler_enabled:
        try:
            from modules.scheduler.service import start_scheduler
            start_scheduler()
            _set_status("scheduler", True)
        except Exception as e:
            logger.warning(f"Scheduler init failed: {e}")
            _set_status("scheduler", False, str(e))

    # 4. Proxy Manager
    try:
        from shared.proxy_manager import proxy_manager
        proxy_manager.init()
        _set_status("proxy", True, f"{proxy_manager.status['healthy_proxies']} proxies available")
    except Exception as e:
        logger.warning(f"Proxy manager init failed: {e}")
        _set_status("proxy", False, str(e))

    # 5. Dark Web / Tor (lazy — just mark available)
    _set_status("tor", True, "lazy init on first request")

    # 5. OSINT modules — stateless, always available
    for mod in ["marketplace", "groups", "news", "osint_social", "osint_specialized", "google_search", "person_search", "gaming", "public_records"]:
        _set_status(mod, True)

    logger.info(f"Vulcan ready — {sum(1 for s in module_status.values() if s['available'])}/{len(module_status)} modules OK")
    yield

    # Shutdown
    try:
        from modules.scheduler.service import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    logger.info("Vulcan shutdown complete")


# ── App ──
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Consolidated OSINT Platform — Marketplace, Groups, News, SANS, Dark Web, Intelligence, Scheduler, Social, Specialized Search",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers ──
from modules.marketplace.router import router as marketplace_router
from modules.groups.router import router as groups_router
from modules.news.router import router as news_router
from modules.sans.router import router as sans_router
from modules.dark_web.router import router as darkweb_router
from modules.intelligence.router_search import router as intel_search_router
from modules.intelligence.router_objects import router as intel_objects_router
from modules.intelligence.router_list import router as intel_list_router
from modules.scheduler.router import router as scheduler_router
from modules.osint_social.router import router as social_router
from modules.osint_specialized.router import router as search_router
from modules.google_search.router import router as google_router
from modules.person_search.router import router as person_router
from modules.gaming.router import router as gaming_router
from modules.public_records.router import router as records_router

app.include_router(marketplace_router)
app.include_router(groups_router)
app.include_router(news_router)
app.include_router(sans_router)
app.include_router(darkweb_router)
app.include_router(intel_search_router)
app.include_router(intel_objects_router)
app.include_router(intel_list_router)
app.include_router(scheduler_router)
app.include_router(social_router)
app.include_router(search_router)
app.include_router(google_router)
app.include_router(person_router)
app.include_router(gaming_router)
app.include_router(records_router)


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs_url": "/docs",
    }


@app.get("/health")
async def health():
    from datetime import datetime
    return {
        "status": "healthy" if any(s["available"] for s in module_status.values()) else "degraded",
        "timestamp": datetime.now().isoformat(),
        "modules": module_status,
    }


@app.get("/proxy/status")
async def proxy_status():
    """Estado del pool de proxies y Tor."""
    try:
        from shared.proxy_manager import proxy_manager
        status = proxy_manager.status
        status["tor_ip"] = proxy_manager.get_tor_ip()
        return status
    except Exception as e:
        return {"error": str(e)}


@app.post("/proxy/rotate")
async def proxy_rotate():
    """Rotar circuito Tor para obtener nueva IP."""
    try:
        from shared.proxy_manager import proxy_manager
        success = proxy_manager.rotate_tor()
        new_ip = proxy_manager.get_tor_ip() if success else None
        return {"rotated": success, "new_ip": new_ip}
    except Exception as e:
        return {"rotated": False, "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.app_port, reload=True)
