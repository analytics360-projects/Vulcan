"""NER models — entity extraction from narrative text via Ollama."""
from typing import List, Optional, Dict, Literal
from pydantic import BaseModel


class NerEntity(BaseModel):
    texto: str
    tipo: Literal["PERSONA", "VEHICULO", "ARMA", "LUGAR", "FECHA_HORA",
                  "MONTO", "ORGANIZACIÓN", "OBJETO"]
    confianza: float
    delta_sugerido: str = ""
    campo_sugerido: str = ""


class DeltaPreFill(BaseModel):
    personas: List[Dict] = []
    vehiculos: List[Dict] = []
    armas: List[Dict] = []
    lugares: List[Dict] = []
    eventos: List[Dict] = []
    objetos: List[Dict] = []
    corporaciones: List[Dict] = []


class NerRequest(BaseModel):
    texto: str
    carpeta_id: Optional[str] = None
    folio_id: Optional[str] = None
    idioma: str = "es-MX"
    user: str = ""


class NerResponse(BaseModel):
    entities: List[NerEntity]
    delta_pre_fill: DeltaPreFill
    texto_resaltado: str  # HTML with colored spans
    hash_custodia: str = ""


class ConfirmPreFillRequest(BaseModel):
    carpeta_id: str
    delta_pre_fill: DeltaPreFill
    user: str = ""


class ConfirmPreFillResponse(BaseModel):
    insertados: int
    hash_custodia: str = ""


class JargonEntry(BaseModel):
    jerga: str
    canonical: str
    tipo: str


class UpdateJargonRequest(BaseModel):
    entries: List[JargonEntry]
    user: str = ""


class UpdateJargonResponse(BaseModel):
    total: int
    hash_custodia: str = ""
