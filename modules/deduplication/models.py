"""Deduplication models — person matching with pg_trgm and exact fields."""
import unicodedata
from datetime import date
from typing import List, Optional, Literal
from pydantic import BaseModel


# ── Name normalization ──

_ABBREVIATIONS = {
    "Mª": "MARIA", "Ma.": "MARIA", "MA.": "MARIA",
    "Mtro": "MAESTRO", "MTRO": "MAESTRO", "MTRO.": "MAESTRO",
    "Lic": "LICENCIADO", "LIC": "LICENCIADO", "LIC.": "LICENCIADO",
    "Ing": "INGENIERO", "ING": "INGENIERO", "ING.": "INGENIERO",
    "Dr": "DOCTOR", "DR": "DOCTOR", "DR.": "DOCTOR",
    "Dra": "DOCTORA", "DRA": "DOCTORA", "DRA.": "DOCTORA",
    "Sra": "SEÑORA", "SRA": "SEÑORA", "SRA.": "SEÑORA",
    "Sr": "SEÑOR", "SR": "SEÑOR", "SR.": "SEÑOR",
    "Gral": "GENERAL", "GRAL": "GENERAL", "GRAL.": "GENERAL",
}


def normalize_name(nombre: str) -> str:
    """Normalize a name: uppercase, remove accents, expand abbreviations."""
    if not nombre:
        return ""
    nombre = nombre.upper().strip()
    # Expand abbreviations
    for abbr, full in _ABBREVIATIONS.items():
        nombre = nombre.replace(abbr.upper(), full)
    # Remove accents
    nombre = unicodedata.normalize("NFKD", nombre)
    nombre = "".join(c for c in nombre if not unicodedata.combining(c))
    # Collapse multiple spaces
    nombre = " ".join(nombre.split())
    return nombre


# ── Request/Response models ──

class CheckPersonRequest(BaseModel):
    nombre: str
    curp: Optional[str] = None
    rfc: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    fecha_nacimiento: Optional[str] = None  # ISO date string
    carpeta_id: Optional[str] = None
    user: str = ""

class DuplicateCandidate(BaseModel):
    persona_id: int
    nombre: str
    score: float  # 0.0 - 1.0
    campos_coincidentes: List[str]
    curp: Optional[str] = None

class CheckPersonResponse(BaseModel):
    status: str  # clear, review_required, definitive_match
    candidates: List[DuplicateCandidate]
    suggested_action: str  # insert, merge, link_as_alias
    confidence: float
    hash_custodia: str = ""

class MergePersonRequest(BaseModel):
    persona_principal_id: int
    persona_duplicada_id: int
    user: str = ""

class MergePersonResponse(BaseModel):
    persona_id: int
    registros_actualizados: int
    alias_agregados: List[str]
    carpetas_reasignadas: List[int]
    hash_custodia: str = ""

class MarkAliasRequest(BaseModel):
    persona_id: int
    alias: str
    tipo: str = "nombre_alterno"  # nombre_alterno, apodo, nombre_legal
    user: str = ""

class MarkAliasResponse(BaseModel):
    persona_id: int
    alias_total: int
    alias_nuevo: str
    hash_custodia: str = ""


# ── Legacy in-memory models (kept for backward compat) ──

class PersonRecord(BaseModel):
    id: str
    nombre: str
    apellido_paterno: str = ""
    apellido_materno: str = ""
    fecha_nacimiento: Optional[str] = None
    curp: Optional[str] = None
    telefono: Optional[str] = None
    alias: List[str] = []
    carpeta_id: Optional[int] = None

class MatchPair(BaseModel):
    persona_a: PersonRecord
    persona_b: PersonRecord
    score_nombre: float
    score_fonetico: float
    score_total: float
    campos_coincidentes: List[str]
    recomendacion: str

class DeduplicationRequest(BaseModel):
    personas: List[PersonRecord]
    umbral_fusion: float = 0.85
    umbral_revision: float = 0.60

class DeduplicationResponse(BaseModel):
    pares_duplicados: List[MatchPair]
    total_personas: int
    total_duplicados: int
    tasa_duplicacion: float
