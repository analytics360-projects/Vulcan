"""CDR Analytics router — Call detail record analysis endpoints."""
from fastapi import APIRouter, HTTPException
from config import logger
from modules.cdr_analytics.models import (
    CDRUploadRequest, CDRAnalysisResponse,
    CDRTimelineRequest, CDRTimelineResponse,
)
from modules.cdr_analytics.service import cdr_analytics_service

router = APIRouter(prefix="/cdr-analytics", tags=["CDR Analytics"])


@router.post("/analyze", response_model=CDRAnalysisResponse)
async def analyze_cdr(request: CDRUploadRequest):
    """Analyze call detail records for graph structure and patterns."""
    try:
        return cdr_analytics_service.analyze(request)
    except Exception as e:
        logger.exception(f"CDR analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/timeline", response_model=CDRTimelineResponse)
async def cdr_timeline(request: CDRTimelineRequest):
    """Generate timeline for a specific phone number."""
    try:
        return cdr_analytics_service.timeline(request)
    except Exception as e:
        logger.exception(f"CDR timeline error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
