"""Sentiment analysis + Semantic report router — G2: Typed Interaction Analysis"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from config import logger
from modules.sentiment.models import SentimentRequest as KeywordSentimentRequest, SentimentResponse
from modules.sentiment.service import (
    analyze_sentiment_batch,
    analyze_texts_keyword,
    generate_semantic_report,
)

router = APIRouter(prefix="/sentiment", tags=["sentiment"])


class SentimentRequest(BaseModel):
    texts: List[Dict[str, Any]]


class SemanticReportRequest(BaseModel):
    search_params: Dict[str, Any] = {}
    keywords: List[str] = []
    results_summary: Dict[str, Any] = {}


@router.post("/analyze")
async def analyze_sentiment(request: SentimentRequest):
    """Analyze sentiment for a batch of texts using LLM."""
    try:
        results = analyze_sentiment_batch(request.texts)
        return {"results": results, "count": len(results)}
    except Exception as e:
        logger.exception(f"Sentiment analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-keyword", response_model=SentimentResponse)
async def analyze_sentiment_keyword(request: KeywordSentimentRequest):
    """
    G2: Keyword-based sentiment analysis — no external LLM needed.
    Classifies texts as positivo/negativo/ofensivo/neutral using Spanish keyword dictionaries.
    Fast, deterministic, offline-capable.
    """
    try:
        return analyze_texts_keyword(request.texts)
    except Exception as e:
        logger.exception(f"Keyword sentiment analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/semantic-report")
async def semantic_report(request: SemanticReportRequest):
    """Generate a semantic report correlating search params with results."""
    try:
        report = generate_semantic_report(
            search_params=request.search_params,
            keywords=request.keywords,
            results_summary=request.results_summary,
        )
        return report
    except Exception as e:
        logger.exception(f"Semantic report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
