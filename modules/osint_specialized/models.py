"""OSINT Specialized search models"""
from pydantic import BaseModel
from typing import List, Optional, Any


class SearchResponse(BaseModel):
    query: str
    plataformas_consultadas: List[str] = []
    resultados: Any = None
    errores: List[str] = []
