"""NLP 911 router — T1-2 NLP classification for emergency calls."""
from fastapi import APIRouter, HTTPException
from config import logger
from modules.nlp_911.models import (
    ClassifyIncidentRequest, ClassifyIncidentResponse,
    ClassifyBatchRequest, ClassifyBatchResponse,
)
from modules.nlp_911.service import nlp_911_service

router = APIRouter(prefix="/nlp-911", tags=["NLP 911"])


@router.post("/classify", response_model=ClassifyIncidentResponse)
async def classify_incident(request: ClassifyIncidentRequest):
    """Classify a 911 call text into incident type, priority, and emotional state."""
    try:
        text = request.texto or request.audio_transcription
        return nlp_911_service.classify_incident(text)
    except Exception as e:
        logger.exception(f"NLP 911 classification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/classify-batch", response_model=ClassifyBatchResponse)
async def classify_batch(request: ClassifyBatchRequest):
    """Classify multiple 911 call texts in batch."""
    try:
        results = [nlp_911_service.classify_incident(t) for t in request.textos]
        return ClassifyBatchResponse(resultados=results)
    except Exception as e:
        logger.exception(f"NLP 911 batch classification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
