"""
IC7 — Risk Score Integral Router
POST /intel/risk-score
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from modules.intelligence.services.risk_scoring import RiskScoringService

router = APIRouter(prefix="/intel", tags=["intelligence"])

_risk_service: Optional[RiskScoringService] = None


def _get_service() -> RiskScoringService:
    global _risk_service
    if _risk_service is None:
        _risk_service = RiskScoringService()
    return _risk_service


class RiskScoreRequest(BaseModel):
    persona_id: int
    antecedentes: int = Field(0, ge=0, description="Incidentes previos")
    asociaciones_criminales: int = Field(0, ge=0, description="Asociaciones criminales del grafo")
    zona_riesgo: float = Field(0.0, ge=0.0, le=1.0, description="Riesgo geoespacial (0-1)")
    armas_reportadas: int = Field(0, ge=0, description="Armas vinculadas")
    reincidencia: int = Field(0, ge=0, description="Reincidencias")
    tipo_incidente: str = Field("otro", description="homicidio|secuestro|robo_armado|asalto|robo|otro")


class RiskFactorResponse(BaseModel):
    nombre: str
    peso: int
    score: float
    maximo: int
    descripcion: str


class RiskScoreResponse(BaseModel):
    persona_id: int
    score: int
    nivel: str
    factores: list[RiskFactorResponse]


@router.post("/risk-score", response_model=RiskScoreResponse, summary="Calcular Risk Score Integral")
async def calculate_risk_score(body: RiskScoreRequest):
    """
    Calcula el puntaje de riesgo integral (0-100) para una persona
    basado en 6 factores ponderados.
    """
    service = _get_service()
    result = service.calculate_risk_score(body.model_dump())
    return result
