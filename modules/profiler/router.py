"""Profiler router — behavioral profiling endpoints."""
from fastapi import APIRouter, HTTPException
from config import logger
from modules.profiler.models import (
    ProfileRequest, ProfileResponse,
    CompareProfilesRequest, CompareProfilesResponse,
)
from modules.profiler.service import profiler_service

router = APIRouter(prefix="/profiler", tags=["Profiler"])


@router.post("/Generate", response_model=ProfileResponse)
async def generate_profile(request: ProfileRequest):
    """Generate behavioral profile from MIA detection data."""
    try:
        return profiler_service.generate(request)
    except Exception as e:
        logger.exception(f"Profile generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/Update", response_model=ProfileResponse)
async def update_profile(request: ProfileRequest):
    """Regenerate profile with latest data."""
    try:
        return profiler_service.generate(request)
    except Exception as e:
        logger.exception(f"Profile update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ByCarpeta/{carpeta_id}")
async def profiles_by_carpeta(carpeta_id: str):
    """Get all behavioral profiles for a carpeta."""
    try:
        from modules.sans.ravendb_client import get_store
        store = get_store()
        with store.open_session() as session:
            results = list(session.query_collection("behavioral_profiles"))
            filtered = [r.__dict__ if hasattr(r, '__dict__') else r
                       for r in results
                       if getattr(r, 'carpeta_id', '') == carpeta_id]
            return filtered
    except Exception as e:
        logger.exception(f"Profiles by carpeta error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
