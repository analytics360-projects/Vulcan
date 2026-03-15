"""Investigator AI models — Case summarization, judicial drafts, investigation suggestions."""
from typing import List, Optional, Dict
from pydantic import BaseModel


class CaseSummaryRequest(BaseModel):
    carpeta_id: int
    narrativas: List[str] = []
    evidencias: List[Dict] = []
    sujetos: List[Dict] = []
    delitos: List[str] = []
    idioma: str = "es"


class CaseSummaryResponse(BaseModel):
    resumen_ejecutivo: str
    hechos_clave: List[str]
    lineas_investigacion: List[str]
    evidencia_pendiente: List[str]
    fortalezas: List[str]
    debilidades: List[str]
    conclusion: str


class JudicialDraftRequest(BaseModel):
    tipo_documento: str  # dictamen, oficio_canalizacion, solicitud_peritaje, informe_policial, acta_circunstanciada
    carpeta_id: int
    datos_caso: Dict
    fiscalia: str = "Fiscalía General de Justicia"
    agente_mp: str = ""
    fecha: str = ""


class JudicialDraftResponse(BaseModel):
    tipo_documento: str
    titulo: str
    contenido: str
    fundamento_legal: List[str]
    articulos_cnpp: List[str]


class NextStepsRequest(BaseModel):
    carpeta_id: int
    tipo_delito: str
    dias_transcurridos: int = 0
    acciones_realizadas: List[str] = []
    evidencias_disponibles: List[str] = []
    sujetos_identificados: int = 0


class InvestigationStep(BaseModel):
    paso: int
    accion: str
    justificacion: str
    prioridad: str  # inmediata, alta, media, baja
    responsable: str  # mp, policia, perito, analista
    plazo_horas: int


class NextStepsResponse(BaseModel):
    pasos_sugeridos: List[InvestigationStep]
    protocolo_aplicable: str
    articulos_referencia: List[str]


class MPPackageRequest(BaseModel):
    carpeta_id: int
    datos_caso: Dict
    evidencias: List[Dict] = []
    sujetos: List[Dict] = []
    narrativa: str = ""
    delitos: List[str] = []
    fiscalia: str = "Fiscalía General de Justicia"


class MPPackageDocument(BaseModel):
    tipo: str
    titulo: str
    contenido: str


class MPPackageResponse(BaseModel):
    documentos: List[MPPackageDocument]
    checklist_completitud: Dict[str, bool]
    observaciones: List[str]
