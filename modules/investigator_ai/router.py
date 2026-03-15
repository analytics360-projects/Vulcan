"""Investigator AI router — Case summarization, judicial drafts, next steps, MP package."""
from fastapi import APIRouter, HTTPException
from config import logger
from modules.investigator_ai.models import (
    CaseSummaryRequest, CaseSummaryResponse,
    JudicialDraftRequest, JudicialDraftResponse,
    NextStepsRequest, NextStepsResponse,
    MPPackageRequest, MPPackageResponse,
)
from modules.investigator_ai.service import investigator_ai_service

router = APIRouter(prefix="/investigator-ai", tags=["Investigator AI"])


@router.post("/summarize", response_model=CaseSummaryResponse)
async def summarize_case(request: CaseSummaryRequest):
    """Generate AI-assisted case summary."""
    try:
        return investigator_ai_service.summarize_case(request)
    except Exception as e:
        logger.exception(f"Case summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/judicial-draft", response_model=JudicialDraftResponse)
async def generate_judicial_draft(request: JudicialDraftRequest):
    """Generate judicial document draft (CNPP-compliant)."""
    try:
        return investigator_ai_service.generate_judicial_draft(request)
    except Exception as e:
        logger.exception(f"Judicial draft error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/next-steps", response_model=NextStepsResponse)
async def suggest_next_steps(request: NextStepsRequest):
    """Suggest investigation next steps based on protocol."""
    try:
        return investigator_ai_service.suggest_next_steps(request)
    except Exception as e:
        logger.exception(f"Next steps error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mp-package", response_model=MPPackageResponse)
async def generate_mp_package(request: MPPackageRequest):
    """Generate complete document package for Ministerio Público."""
    try:
        return investigator_ai_service.generate_mp_package(request)
    except Exception as e:
        logger.exception(f"MP package error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
