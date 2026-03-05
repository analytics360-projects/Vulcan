"""OSINT Social models"""
from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime


class OsintResult(BaseModel):
    plataforma: str
    tipo: str
    datos: Any
    timestamp: str = ""
    fuente_url: Optional[str] = None
    confianza: float = 1.0


class PlatformHealth(BaseModel):
    available: bool
    reason: str = ""


class SocialSearchResponse(BaseModel):
    query: str
    plataforma: str
    resultados: List[OsintResult] = []
    count: int = 0
    health: PlatformHealth
