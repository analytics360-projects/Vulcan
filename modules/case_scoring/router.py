"""Case scoring router — Case prioritization endpoints."""
from fastapi import APIRouter, HTTPException
from config import logger
from modules.case_scoring.models import (
    CaseData, CaseScoreResult,
    BatchScoreRequest, BatchScoreResponse,
)
from modules.case_scoring.service import case_scoring_service

router = APIRouter(prefix="/case-scoring", tags=["Case Scoring"])


@router.post("/score", response_model=CaseScoreResult)
async def score_case(request: CaseData):
    """Score a single case for priority."""
    try:
        return case_scoring_service.score_case(request)
    except Exception as e:
        logger.exception(f"Case scoring error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/score-batch", response_model=BatchScoreResponse)
async def score_batch(request: BatchScoreRequest):
    """Score multiple cases in batch."""
    try:
        return case_scoring_service.score_batch(request)
    except Exception as e:
        logger.exception(f"Batch scoring error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
