"""Camera Manager router — ONVIF discovery, VMS sync, PTZ, camera CRUD."""
from fastapi import APIRouter, HTTPException

from config import logger
from modules.camera_manager.models import (
    CameraAddRequest, CameraSourceType, CameraUpdateRequest,
    OnvifDiscoveryRequest, PTZCommand, VMSSyncRequest,
)
from modules.camera_manager.service import camera_manager_service as svc

router = APIRouter(prefix="/cameras", tags=["Camera Manager"])


# ── Camera CRUD ──

@router.get("/list")
async def list_cameras():
    """List all registered cameras with status."""
    return svc.get_status()


@router.post("/add")
async def add_camera(req: CameraAddRequest):
    """Register a new camera source."""
    cam = svc.add_camera(req)
    return {"camera": cam, "message": "Camera registered"}


@router.put("/{camera_id}")
async def update_camera(camera_id: str, req: CameraUpdateRequest):
    """Update camera configuration."""
    cam = svc.update_camera(camera_id, req)
    if not cam:
        raise HTTPException(404, "Camera not found")
    return {"camera": cam}


@router.delete("/{camera_id}")
async def remove_camera(camera_id: str):
    """Remove a camera from the registry."""
    if not svc.remove_camera(camera_id):
        raise HTTPException(404, "Camera not found")
    return {"message": "Camera removed"}


@router.get("/{camera_id}")
async def get_camera(camera_id: str):
    """Get camera details."""
    cam = svc.get_camera(camera_id)
    if not cam:
        raise HTTPException(404, "Camera not found")
    return cam


# ── ONVIF Discovery ──

@router.post("/discover")
async def discover_onvif(req: OnvifDiscoveryRequest):
    """Discover ONVIF cameras on the network via WS-Discovery."""
    return await svc.discover_onvif(req)


# ── VMS Sync ──

@router.post("/sync/milestone")
async def sync_milestone(req: VMSSyncRequest):
    """Sync cameras from Milestone XProtect."""
    req.source_type = CameraSourceType.MILESTONE
    return await svc.sync_milestone(req)


@router.post("/sync/sense")
async def sync_sense(req: VMSSyncRequest):
    """Sync cameras from Senstar Symphony."""
    req.source_type = CameraSourceType.SENSE
    return await svc.sync_sense(req)


# ── PTZ Control ──

@router.post("/ptz")
async def ptz_control(cmd: PTZCommand):
    """Execute PTZ command on a camera."""
    return await svc.ptz_command(cmd)


# ── Health Check ──

@router.post("/health-check")
async def health_check():
    """Check connectivity of all registered cameras."""
    results = await svc.health_check_all()
    return {"results": results, "total_checked": len(results)}
