"""Semantic search router — Search and contradiction detection endpoints."""
from fastapi import APIRouter, HTTPException
from config import logger
from modules.semantic_search.models import (
    SemanticSearchRequest, SemanticSearchResponse,
    ContradictionRequest, ContradictionResponse,
)
from modules.semantic_search.service import semantic_search_service

router = APIRouter(prefix="/semantic-search", tags=["Semantic Search"])


@router.post("/search", response_model=SemanticSearchResponse)
async def search(request: SemanticSearchRequest):
    """Synonym-aware search over transcriptions and narratives."""
    try:
        return semantic_search_service.search(request)
    except Exception as e:
        logger.exception(f"Semantic search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/contradictions", response_model=ContradictionResponse)
async def detect_contradictions(request: ContradictionRequest):
    """Detect contradictions between multiple statements."""
    try:
        return semantic_search_service.detect_contradictions(request)
    except Exception as e:
        logger.exception(f"Contradiction detection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
