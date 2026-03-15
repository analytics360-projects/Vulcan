"""Correlation models — multi-case similarity search."""
from typing import List, Optional, Dict
from pydantic import BaseModel


class FindSimilarRequest(BaseModel):
    carpeta_id: str
    tipo_delito: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    hora_evento: Optional[int] = None  # 0-23
    dia_semana: Optional[int] = None  # 0-6
    personas_ids: List[str] = []
    vehiculos_placas: List[str] = []
    ventana_meses: int = 6
    radio_km: float = 5.0
    user: str = ""


class CasoSimilar(BaseModel):
    carpeta_id: int
    folio: str
    score_similitud: float
    razones: List[Dict]  # [{campo, similitud_pct}]
    entidades_comunes: List[Dict]  # personas, vehiculos, telefonos en comun


class FindSimilarResponse(BaseModel):
    similar_cases: List[CasoSimilar]
    pattern_alert: Optional[Dict] = None
    common_entities: List[Dict]
    hash_custodia: str = ""


class LinkCasesRequest(BaseModel):
    carpeta_ids: List[str]
    razon: str
    user: str = ""


class LinkCasesResponse(BaseModel):
    linked: bool
    grupo_id: str
    hash_custodia: str = ""


class PersonCasesResponse(BaseModel):
    persona_id: str
    nombre: str
    carpetas: List[Dict]
    total: int
