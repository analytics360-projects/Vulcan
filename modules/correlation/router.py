"""Correlation router — multi-case similarity endpoints."""
from fastapi import APIRouter, HTTPException
from config import logger
from modules.correlation.models import (
    FindSimilarRequest, FindSimilarResponse,
    LinkCasesRequest, LinkCasesResponse,
    PersonCasesResponse,
)
from modules.correlation.service import correlation_service

router = APIRouter(prefix="/correlation", tags=["Correlation"])


@router.post("/FindSimilar", response_model=FindSimilarResponse)
async def find_similar(request: FindSimilarRequest):
    """Find similar cases by type, location, time, and shared entities."""
    try:
        return correlation_service.find_similar(request)
    except Exception as e:
        logger.exception(f"FindSimilar error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/LinkCases", response_model=LinkCasesResponse)
async def link_cases(request: LinkCasesRequest):
    """Link related cases together."""
    try:
        return correlation_service.link_cases(request)
    except Exception as e:
        logger.exception(f"LinkCases error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/PersonCases/{persona_id}", response_model=PersonCasesResponse)
async def person_cases(persona_id: str):
    """Get all cases involving a person."""
    try:
        return correlation_service.person_cases(persona_id)
    except Exception as e:
        logger.exception(f"PersonCases error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
