"""Data Quality Diagnostics — Router"""
from fastapi import APIRouter, HTTPException

from config import logger
from modules.data_quality.models import DataQualityRequest, DataQualityResponse
from modules.data_quality.service import data_quality_service

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.post("/data-quality", response_model=DataQualityResponse)
async def data_quality(request: DataQualityRequest):
    """Analyze dataset quality and return diagnostics with recommendations."""
    try:
        result = data_quality_service.analyze(
            dataset_stats=request.dataset_stats,
            min_resolution_avgs=request.min_resolution_avgs,
        )
        return result
    except Exception as e:
        logger.exception(f"Data quality analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
