"""Tracking Analytics router — heatmap density grids and movement anomaly detection."""
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import logger
from modules.tracking_analytics.service import tracking_analytics_service

router = APIRouter(prefix="/tracking", tags=["Tracking Analytics"])


# ── Request / Response models ──

class HeatmapPoint(BaseModel):
    lat: float
    lng: float
    weight: float = 1.0


class HeatmapRequest(BaseModel):
    points: List[HeatmapPoint]
    grid_size: int = Field(default=20, ge=2, le=200)


class HeatmapBounds(BaseModel):
    lat_min: float
    lat_max: float
    lng_min: float
    lng_max: float


class HeatmapResponse(BaseModel):
    grid: List[List[float]]
    bounds: Optional[HeatmapBounds] = None
    grid_size: int


class TrackingPoint(BaseModel):
    lat: float
    lng: float
    speed: float = 0.0
    timestamp: float = Field(..., description="Unix epoch seconds")


class AnomaliesRequest(BaseModel):
    points: List[TrackingPoint]
    z_threshold: float = Field(default=2.5, ge=1.0, le=5.0)
    idle_min_duration_min: float = Field(default=5.0, ge=1.0)
    idle_radius_m: float = Field(default=50.0, ge=5.0)


class AnomalyEntry(BaseModel):
    index: int
    lat: float
    lng: float
    timestamp: float
    value: float
    z_score: float
    type: str


class IdleCluster(BaseModel):
    centroid_lat: float
    centroid_lng: float
    start_timestamp: float
    end_timestamp: float
    duration_min: float
    point_count: int


class AnomalySummary(BaseModel):
    total_points: int
    speed_anomalies: int
    distance_anomalies: int
    idle_clusters: int


class AnomaliesResponse(BaseModel):
    speed_outliers: List[AnomalyEntry]
    distance_outliers: List[AnomalyEntry]
    idle_clusters: List[IdleCluster]
    summary: AnomalySummary


# ── Endpoints ──

@router.post("/heatmap", response_model=HeatmapResponse)
async def tracking_heatmap(request: HeatmapRequest):
    """Generate a density grid from weighted lat/lng points using numpy histogram2d."""
    try:
        result = tracking_analytics_service.density_grid(
            points=[p.model_dump() for p in request.points],
            grid_size=request.grid_size,
        )
        return result
    except Exception as e:
        logger.exception(f"Tracking heatmap error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/anomalies", response_model=AnomaliesResponse)
async def tracking_anomalies(request: AnomaliesRequest):
    """Detect speed outliers, distance outliers and idle clusters in a tracking sequence."""
    try:
        points_raw = [p.model_dump() for p in request.points]
        result = tracking_analytics_service.detect_anomalies(
            points=points_raw,
            z_threshold=request.z_threshold,
        )
        # Re-run idle with custom params if they differ from defaults
        if request.idle_min_duration_min != 5.0 or request.idle_radius_m != 50.0:
            sorted_pts = sorted(points_raw, key=lambda p: p["timestamp"])
            result["idle_clusters"] = tracking_analytics_service.detect_idle_clusters(
                sorted_pts,
                min_duration_min=request.idle_min_duration_min,
                radius_m=request.idle_radius_m,
            )
            result["summary"]["idle_clusters"] = len(result["idle_clusters"])
        return result
    except Exception as e:
        logger.exception(f"Tracking anomalies error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
