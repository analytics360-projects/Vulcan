"""Sentiment analysis Pydantic models — G2: Typed Interaction Analysis"""
from typing import List, Optional
from pydantic import BaseModel, Field


class SentimentRequest(BaseModel):
    """Request body for batch sentiment analysis."""
    texts: List[str] = Field(..., description="List of texts to analyze")


class SentimentItem(BaseModel):
    """Single sentiment analysis result."""
    text: str
    sentimiento: str = Field(
        default="neutral",
        description="Sentiment classification: positivo, negativo, ofensivo, neutral"
    )
    score: float = Field(
        default=0.0,
        ge=0.0, le=1.0,
        description="Confidence score (ratio of sentiment words to total words)"
    )
    categorias: List[str] = Field(
        default_factory=list,
        description="Detected categories: insulto, amenaza, odio, aprobacion, etc."
    )


class SentimentResponse(BaseModel):
    """Response from batch sentiment analysis."""
    resultados: List[SentimentItem]
    total: int = 0
    ofensivos: int = 0
    positivos: int = 0
    negativos: int = 0
    neutrales: int = 0


class ReactionBreakdown(BaseModel):
    """Facebook-style reaction breakdown."""
    like: int = 0
    love: int = 0
    haha: int = 0
    wow: int = 0
    sad: int = 0
    angry: int = 0
    care: int = 0
