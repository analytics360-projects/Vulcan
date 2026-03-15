"""Hypothesis models — investigative hypothesis generation."""
from typing import List, Optional, Literal
from pydantic import BaseModel


class AccionSugerida(BaseModel):
    descripcion: str
    modulo_sugerido: Optional[str] = None
    prioridad: int = 3  # 1-5


class Hipotesis(BaseModel):
    hypothesis_id: str  # H1, H2, H3...
    titulo: str
    descripcion: str
    evidencia_sustento: List[str]
    acciones_sugeridas: List[AccionSugerida]
    datos_faltantes: List[str]
    prioridad: str  # ALTA, MEDIA, BAJA
    modulos_sugeridos: List[str]
    confianza: float  # 0-1


class HypothesisRequest(BaseModel):
    carpeta_id: str
    force_generate: bool = False
    user: str = ""


class HypothesisResponse(BaseModel):
    hypotheses: List[Hipotesis]
    completitud_carpeta_pct: float
    hash_custodia: str = ""


class AcceptRequest(BaseModel):
    carpeta_id: str
    hypothesis_id: str
    user: str = ""


class AcceptResponse(BaseModel):
    accepted: bool
    actions_enqueued: int
    hash_custodia: str = ""
