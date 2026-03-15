"""
Vulcan — Unified OSINT Platform
Consolidates: Vulcan, Hades, nyx-crawler, Hugin, Skadi
Port 8000 | FastAPI + lifespan
"""
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings, logger
from shared.activity_log import activity_log, ActivityEntry
from shared.dashboard_html import DASHBOARD_HTML

# ── Path → module mapping ──
PATH_MODULE_MAP = {
    "/vehicle": "vehicle",
    "/marketplace": "marketplace",
    "/groups": "groups",
    "/news": "news",
    "/sans": "sans",
    "/darkweb": "dark_web",
    "/intel": "intelligence",
    "/scheduler": "scheduler",
    "/social": "osint_social",
    "/search": "osint_specialized",
    "/google": "google_search",
    "/person": "person_search",
    "/gaming": "gaming",
    "/records": "public_records",
    "/fb-accounts": "fb_accounts",
    "/social-accounts": "social_accounts",
    "/sentiment": "sentiment",
    "/geo": "geo",
    "/monitoring": "monitoring",
    "/username": "username_enum",
    "/osint-tools": "osint_tools",
    "/pdl": "pdl",
    "/health": "health",
    "/dashboard": "dashboard",
    "/api/activity": "dashboard",
    "/proxy": "proxy",
    "/geospatial": "geospatial",
    "/speech": "speech",
    "/analysis": "analysis",
    "/ocr": "ocr",
    "/social-graph": "social_graph",
    "/analytics": "analytics",
    "/training": "training",
    "/labels": "labels",
    "/nlp-911": "nlp_911",
    "/predictive": "predictive",
    "/semantic-search": "semantic_search",
    "/case-scoring": "case_scoring",
    "/deduplication": "deduplication",
    "/cdr-analytics": "cdr_analytics",
    "/investigator-ai": "investigator_ai",
    "/ner": "ner",
    "/consistency": "consistency",
    "/community": "community",
    "/correlation": "correlation",
    "/profiler": "profiler",
    "/hypothesis": "hypothesis",
    "/tracking": "tracking_analytics",
}

SKIP_LOG_PREFIXES = ("/dashboard", "/api/activity", "/favicon", "/docs", "/openapi")


def _resolve_module(path: str) -> str:
    for prefix, mod in PATH_MODULE_MAP.items():
        if path.startswith(prefix):
            return mod
    return "root"


class ActivityLogMiddleware(BaseHTTPMiddleware):
    """Logs every request to the in-memory activity log + stdout."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        path = request.url.path
        query = str(request.url.query) if request.url.query else ""
        module = _resolve_module(path)
        skip_log = any(path.startswith(p) for p in SKIP_LOG_PREFIXES)

        # Log incoming request (skip dashboard polling)
        if not skip_log:
            logger.info(
                f"→ {request.method} {path}"
                + (f"?{query}" if query else "")
                + f"  [module={module}, client={request.client.host if request.client else '?'}]"
            )

        error_msg = None
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            error_msg = str(exc)[:500]
            logger.error(f"✗ {request.method} {path} — unhandled error: {error_msg}")
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0

            if not skip_log:
                level = "INFO" if status_code < 400 else ("WARNING" if status_code < 500 else "ERROR")
                getattr(logger, level.lower(), logger.info)(
                    f"← {request.method} {path} → {status_code} ({duration_ms:.0f}ms)"
                    + (f"  ERROR: {error_msg}" if error_msg else "")
                )

            activity_log.add(ActivityEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                method=request.method,
                path=path,
                query=query,
                status_code=status_code,
                duration_ms=duration_ms,
                client_ip=request.client.host if request.client else "",
                module=module,
                error=error_msg,
            ))

        return response


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

    # 3b. LLM Queue table
    try:
        from services.llm_queue_service import ensure_queue_table
        ensure_queue_table()
        _set_status("llm_queue", True)
    except Exception as e:
        logger.warning(f"LLM queue table init failed (non-critical): {e}")
        _set_status("llm_queue", False, str(e))

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

    # 6. Social Account Manager (Facebook, Instagram, TikTok)
    try:
        from shared.social_account_manager import social_account_manager
        social_account_manager.init()
        _set_status("social_accounts", True)
    except Exception as e:
        logger.warning(f"Social Account Manager init failed (login degraded): {e}")
        _set_status("social_accounts", False, str(e))

    # 7. OSINT modules — stateless, always available
    for mod in ["marketplace", "groups", "news", "osint_social", "osint_specialized", "google_search", "person_search", "gaming", "public_records", "sentiment", "geo", "monitoring", "vehicle_osint", "username_enum", "osint_tools", "pdl", "geospatial", "speech", "analysis", "social_graph", "data_quality", "analytics", "training", "ocr", "labels", "nlp_911", "predictive", "semantic_search", "case_scoring", "deduplication", "cdr_analytics", "investigator_ai", "ner", "consistency", "community", "correlation", "profiler", "hypothesis", "tracking_analytics"]:
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

app.add_middleware(ActivityLogMiddleware)


# ── Dashboard & Activity API ──
@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    return DASHBOARD_HTML


@app.get("/api/activity/recent")
async def activity_recent(limit: int = 50):
    return activity_log.recent(limit)


@app.get("/api/activity/stats")
async def activity_stats():
    return activity_log.stats()


@app.get("/api/activity/search")
async def activity_search(q: str = "", limit: int = 50):
    return activity_log.search(q, limit)


# ── Register routers ──
from modules.marketplace.router import router as marketplace_router
from modules.groups.router import router as groups_router
from modules.news.router import router as news_router
from modules.sans.router import router as sans_router
from modules.dark_web.router import router as darkweb_router
try:
    from modules.intelligence.router_search import router as intel_search_router
    from modules.intelligence.router_objects import router as intel_objects_router
    from modules.intelligence.router_list import router as intel_list_router
    from modules.intelligence.router_risk import router as intel_risk_router
    _intel_available = True
except ImportError as e:
    logger.warning(f"Intelligence module not available (missing deps): {e}")
    _intel_available = False
try:
    from modules.intelligence.router_metrics import router as intel_metrics_router
    _intel_metrics_available = True
except ImportError as e:
    logger.warning(f"Intelligence metrics module not available: {e}")
    _intel_metrics_available = False
try:
    from modules.intelligence.router_modus import router as intel_modus_router
    _intel_modus_available = True
except ImportError as e:
    logger.warning(f"Intelligence modus operandi module not available: {e}")
    _intel_modus_available = False
from modules.scheduler.router import router as scheduler_router
from modules.osint_social.router import router as social_router
from modules.osint_specialized.router import router as search_router
from modules.google_search.router import router as google_router
from modules.person_search.router import router as person_router
from modules.gaming.router import router as gaming_router
from modules.public_records.router import router as records_router
from modules.fb_accounts.router import router as fb_accounts_router
from modules.social_accounts.router import router as social_accounts_router
from modules.sentiment.router import router as sentiment_router
from modules.geo.router import router as geo_router
from modules.monitoring.router import router as monitoring_router
from modules.vehicle_osint.router import router as vehicle_osint_router
from modules.username_enum.router import router as username_enum_router
from modules.osint_tools.router import router as osint_tools_router
from modules.pdl.router import router as pdl_router
from modules.geospatial.router import router as geospatial_router
from modules.speech.router import router as speech_router
from modules.analysis.router import router as analysis_router
from modules.social_graph.router import router as social_graph_router
from modules.data_quality.router import router as data_quality_router
from modules.analytics.router import router as analytics_router
from modules.training.router import router as training_router
from modules.ocr.router import router as ocr_router
from modules.labels.router import router as labels_router
from modules.nlp_911.router import router as nlp_911_router
from modules.predictive.router import router as predictive_router
from modules.semantic_search.router import router as semantic_search_router
from modules.case_scoring.router import router as case_scoring_router
from modules.deduplication.router import router as deduplication_router
from modules.cdr_analytics.router import router as cdr_analytics_router
from modules.investigator_ai.router import router as investigator_ai_router
from modules.ner.router import router as ner_router
from modules.consistency.router import router as consistency_router
from modules.community.router import router as community_router
from modules.correlation.router import router as correlation_router
from modules.profiler.router import router as profiler_router
from modules.hypothesis.router import router as hypothesis_router
from modules.tracking_analytics.router import router as tracking_analytics_router

app.include_router(marketplace_router)
app.include_router(groups_router)
app.include_router(news_router)
app.include_router(sans_router)
app.include_router(darkweb_router)
if _intel_available:
    app.include_router(intel_search_router)
    app.include_router(intel_objects_router)
    app.include_router(intel_list_router)
    app.include_router(intel_risk_router)
if _intel_metrics_available:
    app.include_router(intel_metrics_router)
if _intel_modus_available:
    app.include_router(intel_modus_router)
app.include_router(scheduler_router)
app.include_router(social_router)
app.include_router(search_router)
app.include_router(google_router)
app.include_router(person_router)
app.include_router(gaming_router)
app.include_router(records_router)
app.include_router(fb_accounts_router)
app.include_router(social_accounts_router)
app.include_router(sentiment_router)
app.include_router(geo_router)
app.include_router(monitoring_router)
app.include_router(vehicle_osint_router)
app.include_router(username_enum_router)
app.include_router(osint_tools_router)
app.include_router(pdl_router)
app.include_router(geospatial_router)
app.include_router(speech_router)
app.include_router(analysis_router)
app.include_router(social_graph_router)
app.include_router(data_quality_router)
app.include_router(analytics_router)
app.include_router(training_router)
app.include_router(ocr_router)
app.include_router(labels_router)
app.include_router(nlp_911_router)
app.include_router(predictive_router)
app.include_router(semantic_search_router)
app.include_router(case_scoring_router)
app.include_router(deduplication_router)
app.include_router(cdr_analytics_router)
app.include_router(investigator_ai_router)
app.include_router(ner_router)
app.include_router(consistency_router)
app.include_router(community_router)
app.include_router(correlation_router)
app.include_router(profiler_router)
app.include_router(hypothesis_router)
app.include_router(tracking_analytics_router)


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
