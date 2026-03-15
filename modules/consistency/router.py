"""Consistency router — declaration comparison endpoints."""
from fastapi import APIRouter, HTTPException
from config import logger
from modules.consistency.models import (
    ConsistencyAnalyzeRequest, ConsistencyReport,
    AddDeclarationRequest, AddDeclarationResponse,
)
from modules.consistency.service import consistency_service

router = APIRouter(prefix="/consistency", tags=["Consistency"])


@router.post("/Analyze", response_model=ConsistencyReport)
async def analyze_consistency(request: ConsistencyAnalyzeRequest):
    """Compare multiple declarations and find inconsistencies using Ollama LLM."""
    if len(request.declaraciones) < 2:
        raise HTTPException(status_code=400, detail="Se necesitan al menos 2 declaraciones")
    try:
        return await consistency_service.analyze(request)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"Consistency analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/AddDeclaration", response_model=AddDeclarationResponse)
async def add_declaration(request: AddDeclarationRequest):
    """Store a declaration for future consistency analysis."""
    try:
        return consistency_service.add_declaration(request)
    except Exception as e:
        logger.exception(f"Add declaration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/Report/{persona_id}/{carpeta_id}")
async def get_report(persona_id: str, carpeta_id: str):
    """Get the latest consistency report for a person in a carpeta."""
    try:
        report = consistency_service.get_report(persona_id, carpeta_id)
        if not report:
            raise HTTPException(status_code=404, detail="No report found")
        return report
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Get report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
