"""Predictive analytics router — Spatiotemporal crime prediction endpoints."""
from fastapi import APIRouter, HTTPException
from config import logger
from modules.predictive.models import (
    PredictionRequest, PredictionResult,
    AnomalyRequest, AnomalyResponse,
    PatrolRouteRequest, PatrolRouteResponse,
    PredictiveStatsResponse,
)
from modules.predictive.service import predictive_service

router = APIRouter(prefix="/predictive", tags=["Predictive Analytics"])


@router.post("/predict", response_model=PredictionResult)
async def predict_crime(request: PredictionRequest):
    """Generate spatiotemporal crime predictions for an area."""
    try:
        return predictive_service.predict(request)
    except Exception as e:
        logger.exception(f"Prediction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/anomalies", response_model=AnomalyResponse)
async def detect_anomalies(request: AnomalyRequest):
    """Detect statistical anomalies in crime patterns."""
    try:
        return predictive_service.detect_anomalies(request)
    except Exception as e:
        logger.exception(f"Anomaly detection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/patrol-route", response_model=PatrolRouteResponse)
async def generate_patrol_route(request: PatrolRouteRequest):
    """Generate optimized patrol route based on crime hotspots."""
    try:
        return predictive_service.generate_patrol_route(request)
    except Exception as e:
        logger.exception(f"Patrol route error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=PredictiveStatsResponse)
async def get_stats():
    """Get prediction system statistics."""
    return predictive_service.get_stats()
