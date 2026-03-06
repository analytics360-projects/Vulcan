"""Google Search OSINT models"""
from pydantic import BaseModel
from typing import List, Optional, Any


class GoogleSearchResult(BaseModel):
    titulo: str
    url: str
    snippet: str = ""
    dominio: str = ""


class SiteCapture(BaseModel):
    url: str
    titulo: str = ""
    screenshot_path: Optional[str] = None
    html_path: Optional[str] = None
    imagenes: List[str] = []
    texto_extraido: str = ""
    meta_datos: dict = {}


class GoogleSearchResponse(BaseModel):
    query: str
    total_resultados: int = 0
    resultados: List[GoogleSearchResult] = []
    capturas: List[SiteCapture] = []
    errores: List[str] = []
