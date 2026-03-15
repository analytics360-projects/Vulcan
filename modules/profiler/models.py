"""Profiler models — behavioral profiling from MIA data."""
from typing import List, Optional, Dict
from pydantic import BaseModel


class ProfileRequest(BaseModel):
    persona_id: str
    carpeta_id: Optional[str] = None
    user: str = ""


class EmotionPattern(BaseModel):
    emotion: str
    percentage: float


class FrequentObject(BaseModel):
    label: str
    frecuencia_pct: float


class ActivityWindow(BaseModel):
    hora_inicio: int
    hora_fin: int
    frecuencia_pct: float


class BehavioralFlag(BaseModel):
    tipo: str  # ARMA, DROGA, NOCTURNO, VIOLENCIA
    descripcion: str
    confianza: float


class ProfileResponse(BaseModel):
    persona_id: str
    total_detections: int
    emotion_pattern: List[EmotionPattern]
    frequent_objects: List[FrequentObject]
    activity_windows: List[ActivityWindow]
    flags: List[BehavioralFlag]
    narrative: str  # LLM-generated profile summary
    co_occurrences: List[Dict]  # other persons seen with
    hash_custodia: str = ""


class CompareProfilesRequest(BaseModel):
    persona_id_a: str
    persona_id_b: str
    user: str = ""


class CompareProfilesResponse(BaseModel):
    similitud: float
    patrones_comunes: List[str]
    diferencias_clave: List[str]
    hash_custodia: str = ""
