"""Public Records models — Mexican & international open data sources"""
from pydantic import BaseModel
from typing import Any, Optional, List


class PublicRecordResult(BaseModel):
    fuente: str
    tipo: str  # curp, rfc, vehiculo, denuncia, empresa, dominio, etc.
    disponible: bool = True
    datos: Any = None
    error: Optional[str] = None
    url_fuente: Optional[str] = None


class PersonDossierResponse(BaseModel):
    """Full person dossier — ancestry-style comprehensive profile"""
    nombre: str
    curp: Optional[str] = None
    rfc: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    username: Optional[str] = None
    domicilio: Optional[str] = None
    alias: Optional[str] = None
    zona_geografica: Optional[str] = None
    registros: List[PublicRecordResult] = []
    redes_sociales: List[Any] = []
    total_fuentes: int = 0
    total_resultados: int = 0
