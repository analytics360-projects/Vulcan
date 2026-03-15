"""Hypothesis router — investigative hypothesis endpoints."""
from fastapi import APIRouter, HTTPException
from config import logger
from modules.hypothesis.models import (
    HypothesisRequest, HypothesisResponse,
    AcceptRequest, AcceptResponse,
)
from modules.hypothesis.service import hypothesis_service

router = APIRouter(prefix="/hypothesis", tags=["Hypothesis"])


@router.post("/Generate", response_model=HypothesisResponse)
async def generate_hypotheses(request: HypothesisRequest):
    """Generate investigative hypotheses from carpeta data."""
    try:
        return await hypothesis_service.generate(request)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"Hypothesis generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/Accept", response_model=AcceptResponse)
async def accept_hypothesis(request: AcceptRequest):
    """Accept a hypothesis and enqueue suggested actions."""
    try:
        return hypothesis_service.accept(request)
    except Exception as e:
        logger.exception(f"Accept hypothesis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/Dismiss")
async def dismiss_hypothesis(request: AcceptRequest):
    """Dismiss a hypothesis (mark as dismissed)."""
    try:
        from modules.sans.ravendb_client import get_store
        store = get_store()
        with store.open_session() as session:
            doc = {"carpeta_id": request.carpeta_id,
                   "hypothesis_id": request.hypothesis_id,
                   "action": "dismissed",
                   "user": request.user,
                   "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()}
            session.store(doc, f"hypothesis_actions/{request.carpeta_id}/{request.hypothesis_id}")
            session.save_changes()
        return {"dismissed": True}
    except Exception as e:
        logger.exception(f"Dismiss hypothesis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/Regenerate", response_model=HypothesisResponse)
async def regenerate_hypotheses(request: HypothesisRequest):
    """Regenerate hypotheses (force even if completeness < 60%)."""
    try:
        request.force_generate = True
        return await hypothesis_service.generate(request)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"Regenerate hypothesis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
