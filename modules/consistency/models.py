"""Consistency models — declaration comparison via Ollama."""
from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel


class Declaracion(BaseModel):
    texto: str
    fuente: str = "otro"  # 911_call, entrevista, mp_declaracion, redes_sociales, llamada_carcel, transcripcion_bodycam, otro
    fecha: str  # ISO datetime string
    declaracion_id: Optional[str] = None


class InconsistenciaDetectada(BaseModel):
    tema: str
    texto_declaracion_a: str
    texto_declaracion_b: str
    tipo: str  # CONTRADICCION_DIRECTA, OMISION_SIGNIFICATIVA, CAMBIO_ENFASIS, INCONSISTENCIA_MENOR
    severidad: str  # ALTA, MEDIA, BAJA


class ConsistencyAnalyzeRequest(BaseModel):
    persona_id: str
    carpeta_id: str
    declaraciones: List[Declaracion]  # min 2
    ejes_tematicos: Optional[List[str]] = None
    user: str = ""


class ConsistencyReport(BaseModel):
    score: float  # 0-100
    inconsistencias: List[InconsistenciaDetectada]
    red_flags: List[InconsistenciaDetectada]  # only severidad ALTA
    resumen_ejecutivo: str
    total_declaraciones_analizadas: int
    hash_custodia: str = ""


class AddDeclarationRequest(BaseModel):
    persona_id: str
    carpeta_id: str
    declaracion: Declaracion
    user: str = ""


class AddDeclarationResponse(BaseModel):
    stored: bool
    total_declaraciones: int
    hash_custodia: str = ""
