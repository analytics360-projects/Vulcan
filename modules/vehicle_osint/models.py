"""Vehicle OSINT models"""
from typing import Optional
from pydantic import BaseModel


class VinDecodeResult(BaseModel):
    vin: str
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    vehicle_type: Optional[str] = None
    engine: Optional[str] = None
    country: Optional[str] = None
    body_class: Optional[str] = None
    raw: Optional[dict] = None
    error: Optional[str] = None


class RepuveResult(BaseModel):
    placa: Optional[str] = None
    niv: Optional[str] = None
    nci: Optional[str] = None
    estatus: Optional[str] = None  # "registrado" | "robado" | "no_encontrado" | "error"
    marca: Optional[str] = None
    modelo: Optional[str] = None
    anio: Optional[str] = None
    clase: Optional[str] = None
    tipo: Optional[str] = None
    entidad: Optional[str] = None
    version: Optional[str] = None
    puertas: Optional[str] = None
    pais_origen: Optional[str] = None
    desplazamiento: Optional[str] = None
    cilindros: Optional[str] = None
    planta_ensamble: Optional[str] = None
    institucion_inscripcion: Optional[str] = None
    fecha_inscripcion: Optional[str] = None
    fecha_emplacado: Optional[str] = None
    fecha_actualizacion: Optional[str] = None
    datos_complementarios: Optional[str] = None
    detalles: Optional[str] = None
    url_fuente: str = "https://www2.repuve.gob.mx:8443/ciudadania/"
    error: Optional[str] = None


class VehicleOsintResult(BaseModel):
    marketplace: list = []
    twitter: list = []
    google: list = []
    forums: list = []
    total: int = 0
    error: Optional[str] = None


class VehicleFullSearchResponse(BaseModel):
    vin_decode: Optional[VinDecodeResult] = None
    repuve: Optional[RepuveResult] = None
    osint: Optional[VehicleOsintResult] = None
    placa: Optional[str] = None
    niv: Optional[str] = None
    timestamp: str = ""
