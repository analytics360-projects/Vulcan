"""Geospatial router — IC4 Hotspots Geoespaciales."""
from fastapi import APIRouter, HTTPException

from config import logger
from modules.geospatial.models import (
    HotspotRequest,
    HotspotResponse,
    HeatmapRequest,
    HeatmapResponse,
)
from modules.geospatial.service import geospatial_service

router = APIRouter(prefix="/geospatial", tags=["Geospatial"])


@router.post("/hotspots", response_model=HotspotResponse)
async def hotspots(request: HotspotRequest):
    """Detect spatial hotspot clusters using DBSCAN with haversine metric."""
    try:
        result = geospatial_service.calculate_hotspots(
            points=request.puntos,
            eps=request.eps,
            min_samples=request.min_samples,
        )
        return result
    except Exception as e:
        logger.exception(f"Hotspot calculation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/heatmap", response_model=HeatmapResponse)
async def heatmap(request: HeatmapRequest):
    """Generate density heatmap grid from coordinate points."""
    try:
        result = geospatial_service.calculate_heatmap(
            points=request.puntos,
            grid_size=request.grid_size,
        )
        return result
    except Exception as e:
        logger.exception(f"Heatmap calculation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
