"""Video Analytics router — Real-time analysis pipeline control."""
from fastapi import APIRouter, HTTPException

from config import logger
from modules.video_analytics.models import (
    PipelineConfig, StartAnalysisRequest, WatchlistAddRequest,
)
from modules.video_analytics.service import video_analytics_service as svc

router = APIRouter(prefix="/video-analytics", tags=["Video Analytics"])


# ── Pipeline Control ──

@router.post("/start")
async def start_analysis(req: StartAnalysisRequest):
    """Start real-time analysis on a camera stream."""
    from modules.camera_manager.service import camera_manager_service
    cam = camera_manager_service.get_camera(req.camera_id)
    if not cam:
        raise HTTPException(404, "Camera not found in registry")
    if not cam.rtsp_url:
        raise HTTPException(400, "Camera has no RTSP URL configured")

    config = req.config or PipelineConfig(
        camera_id=req.camera_id,
        **cam.analysis_config,
    )
    config.camera_id = req.camera_id
    status = svc.start_analysis(req.camera_id, cam.rtsp_url, config)
    return {"status": status, "message": "Analysis started"}


@router.post("/stop/{camera_id}")
async def stop_analysis(camera_id: str):
    """Stop analysis on a camera stream."""
    if not svc.stop_analysis(camera_id):
        raise HTTPException(404, "No active pipeline for this camera")
    return {"message": "Analysis stopped"}


@router.get("/status")
async def get_all_status():
    """Get status of all analysis pipelines."""
    return svc.get_all_status()


@router.get("/status/{camera_id}")
async def get_pipeline_status(camera_id: str):
    """Get status of a specific analysis pipeline."""
    status = svc.get_pipeline_status(camera_id)
    if not status:
        raise HTTPException(404, "No pipeline for this camera")
    return status


# ── Alerts ──

@router.get("/alerts")
async def get_alerts(camera_id: str = "", limit: int = 50):
    """Get recent alerts from all or specific camera."""
    alerts = svc.get_recent_alerts(camera_id, limit)
    return {"alerts": alerts, "total": len(alerts)}


# ── Watchlist ──

@router.get("/watchlist")
async def get_watchlist():
    """Get the current watchlist (faces + plates)."""
    return svc.get_watchlist()


@router.post("/watchlist/add")
async def add_to_watchlist(req: WatchlistAddRequest):
    """Add a person (face) or plate to the watchlist."""
    entry = svc.add_to_watchlist(req)
    return {"entry": entry, "message": f"Added to {req.type} watchlist"}


@router.delete("/watchlist/{entry_id}")
async def remove_from_watchlist(entry_id: str):
    """Remove an entry from the watchlist."""
    if not svc.remove_from_watchlist(entry_id):
        raise HTTPException(404, "Watchlist entry not found")
    return {"message": "Removed from watchlist"}
