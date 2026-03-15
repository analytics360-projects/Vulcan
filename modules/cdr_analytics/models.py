"""CDR Analytics models — Call detail record graph analysis."""
from typing import List, Optional, Dict
from pydantic import BaseModel


class CallRecord(BaseModel):
    id: str = ""
    numero_origen: str
    numero_destino: str
    fecha: str
    duracion_seg: int
    tipo: str = "voz"  # voz, sms, datos
    celda_id: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


class CDRUploadRequest(BaseModel):
    registros: List[CallRecord]
    carpeta_id: Optional[int] = None


class PhoneNode(BaseModel):
    numero: str
    total_llamadas: int
    total_duracion_seg: int
    contactos_unicos: int
    es_central: bool
    grado_centralidad: float


class CDREdge(BaseModel):
    origen: str
    destino: str
    total_llamadas: int
    total_duracion_seg: int
    primera_llamada: str
    ultima_llamada: str


class CDRPattern(BaseModel):
    tipo: str  # burst, nocturno, triangular, torre_fija, nuevo_contacto
    descripcion: str
    numeros_involucrados: List[str]
    severidad: float
    fecha_inicio: str
    fecha_fin: str


class CDRAnalysisResponse(BaseModel):
    nodos: List[PhoneNode]
    enlaces: List[CDREdge]
    patrones: List[CDRPattern]
    total_registros: int
    rango_fechas: Dict[str, str]
    numero_central: Optional[str] = None


class CDRTimelineRequest(BaseModel):
    numero: str
    registros: List[CallRecord]


class CDRTimelineEntry(BaseModel):
    fecha: str
    llamadas_entrantes: int
    llamadas_salientes: int
    duracion_total: int
    contactos_nuevos: int


class CDRTimelineResponse(BaseModel):
    numero: str
    timeline: List[CDRTimelineEntry]
    total_dias: int
