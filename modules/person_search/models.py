"""Person Search models — unified person intelligence"""
from pydantic import BaseModel
from typing import List, Optional, Any


class PlatformResult(BaseModel):
    plataforma: str
    disponible: bool
    resultados: Any = None
    error: Optional[str] = None


class PersonSearchResponse(BaseModel):
    nombre: str
    email: Optional[str] = None
    telefono: Optional[str] = None
    username: Optional[str] = None
    domicilio: Optional[str] = None
    alias: Optional[str] = None
    zona_geografica: Optional[str] = None
    plataformas: List[PlatformResult] = []
    total_resultados: int = 0
    google_capturas: Any = None
