"""NER router — entity extraction endpoints."""
from fastapi import APIRouter, HTTPException
from config import logger
from modules.ner.models import (
    NerRequest, NerResponse,
    ConfirmPreFillRequest, ConfirmPreFillResponse,
    UpdateJargonRequest, UpdateJargonResponse,
)
from modules.ner.service import ner_service

router = APIRouter(prefix="/ner", tags=["NER"])


@router.post("/ExtractFromNarrative", response_model=NerResponse)
async def extract_from_narrative(request: NerRequest):
    """Extract named entities from Spanish narrative text using Ollama LLM."""
    try:
        return await ner_service.extract(request)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"NER extraction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ConfirmPreFill", response_model=ConfirmPreFillResponse)
async def confirm_prefill(request: ConfirmPreFillRequest):
    """Confirm and insert pre-filled delta entities into a carpeta."""
    try:
        # Placeholder — actual insert logic depends on carpeta service
        from modules.ner.models import ConfirmPreFillResponse
        import hashlib, json
        from datetime import datetime, timezone
        total = sum(len(v) for v in request.delta_pre_fill.model_dump().values() if isinstance(v, list))
        payload = f"{request.user}|NER|ConfirmPreFill|{json.dumps({'carpeta_id': request.carpeta_id})}|{datetime.now(timezone.utc).isoformat()}"
        h = hashlib.sha256(payload.encode()).hexdigest()
        return ConfirmPreFillResponse(insertados=total, hash_custodia=h)
    except Exception as e:
        logger.exception(f"NER confirm prefill error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/UpdateJargonDict", response_model=UpdateJargonResponse)
async def update_jargon(request: UpdateJargonRequest):
    """Add or update entries in the jargon dictionary."""
    try:
        return ner_service.update_jargon(request)
    except Exception as e:
        logger.exception(f"NER jargon update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
