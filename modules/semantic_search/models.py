"""Semantic search models — Synonym-aware search and contradiction detection."""
from typing import List, Optional, Dict
from pydantic import BaseModel


class SemanticSearchRequest(BaseModel):
    query: str
    carpeta_id: Optional[int] = None
    max_results: int = 20
    umbral_similitud: float = 0.3


class SearchHit(BaseModel):
    source_id: str
    source_type: str  # transcripcion, narrativa, declaracion, evidencia
    texto: str
    fragmento: str
    score: float
    palabras_clave: List[str]
    fecha: Optional[str] = None


class SemanticSearchResponse(BaseModel):
    resultados: List[SearchHit]
    total: int
    query_expandida: List[str]
    tiempo_ms: int


class ContradictionRequest(BaseModel):
    textos: List[Dict[str, str]]  # [{id, texto, autor, fecha}]
    umbral: float = 0.5


class ContradictionPair(BaseModel):
    texto_a_id: str
    texto_b_id: str
    fragmento_a: str
    fragmento_b: str
    tipo: str  # temporal, factual, cuantitativa, locativa
    explicacion: str
    severidad: float


class ContradictionResponse(BaseModel):
    contradicciones: List[ContradictionPair]
    total: int
    consistencia_global: float
