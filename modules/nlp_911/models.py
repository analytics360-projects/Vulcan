"""NLP 911 models — Incident classification from emergency call text."""
from typing import List, Optional
from pydantic import BaseModel


class ClassifyIncidentRequest(BaseModel):
    texto: str
    audio_transcription: str = ""


class ClassifyIncidentResponse(BaseModel):
    tipo_incidente: str
    subtipo: str
    prioridad: int
    confidence: float
    palabras_clave: List[str]
    estado_emocional: str
    nivel_estres: str
    recursos_sugeridos: List[str]


class ClassifyBatchRequest(BaseModel):
    textos: List[str]


class ClassifyBatchResponse(BaseModel):
    resultados: List[ClassifyIncidentResponse]
