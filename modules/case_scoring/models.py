"""Case scoring models — Automated case priority scoring."""
from typing import List, Optional, Dict
from pydantic import BaseModel


class CaseData(BaseModel):
    carpeta_id: int
    tipo_delito: str
    dias_abierto: int = 0
    num_evidencias: int = 0
    num_sujetos: int = 0
    tiene_video: bool = False
    tiene_testigos: bool = False
    tiene_arma: bool = False
    victimas_menores: bool = False
    reincidente: bool = False
    zona_riesgo: bool = False
    sla_restante_horas: Optional[float] = None


class ScoreFactor(BaseModel):
    factor: str
    peso: float
    valor: float
    contribucion: float


class CaseScoreResult(BaseModel):
    carpeta_id: int
    score_total: float
    prioridad: str  # critica, alta, media, baja
    factores: List[ScoreFactor]
    recomendacion: str


class BatchScoreRequest(BaseModel):
    casos: List[CaseData]


class BatchScoreResponse(BaseModel):
    resultados: List[CaseScoreResult]
    promedio_score: float
    distribucion: Dict[str, int]  # {critica: N, alta: N, ...}
