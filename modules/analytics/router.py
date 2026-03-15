"""Analytics router — Trends, Predictions, Clusters"""
from fastapi import APIRouter, HTTPException

from config import logger
from modules.analytics.models import (
    TrendsRequest,
    TrendsResponse,
    PredictionRequest,
    PredictionResponse,
    ClustersRequest,
    ClustersResponse,
)
from modules.analytics.service import analytics_service

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.post("/trends", response_model=TrendsResponse)
async def trends(request: TrendsRequest):
    """Analyze detection list and return time-series trends grouped by type."""
    try:
        result = analytics_service.get_trends(
            detections=request.detections,
            group_by=request.group_by,
        )
        return result
    except Exception as e:
        logger.exception(f"Trends analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    """Given a time series, predict future values using linear regression."""
    try:
        result = analytics_service.predict(
            series=request.series,
            periods=request.periods,
        )
        return result
    except Exception as e:
        logger.exception(f"Prediction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clusters", response_model=ClustersResponse)
async def clusters(request: ClustersRequest):
    """Cluster entities by label similarity."""
    try:
        result = analytics_service.cluster_entities(
            entities=request.entities,
        )
        return result
    except Exception as e:
        logger.exception(f"Clustering error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
