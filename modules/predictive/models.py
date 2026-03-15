"""Predictive analytics models — Spatiotemporal crime prediction."""
from typing import List, Optional
from pydantic import BaseModel, model_validator


class _CamelSnakeMixin(BaseModel):
    """Accept both camelCase and snake_case field names."""

    @model_validator(mode="before")
    @classmethod
    def _accept_camel(cls, values):
        if isinstance(values, dict):
            mapping = {
                "radioKm": "radio_km",
                "diasHistoricos": "dias_historicos",
                "diasPrediccion": "dias_prediccion",
                "tiposDelito": "tipos_delito",
                "umbralZ": "umbral_z",
                "latCentro": "lat_centro",
                "lonCentro": "lon_centro",
                "numPuntos": "num_puntos",
                "fechaInicio": "fecha_inicio",
                "fechaFin": "fecha_fin",
                "hoursAhead": "hours_ahead",
                "subcentroIds": "subcentro_ids",
            }
            for camel, snake in mapping.items():
                if camel in values and snake not in values:
                    values[snake] = values[camel]
        return values


class InputPoint(BaseModel):
    """Real event coordinate passed from Balder/frontend."""
    lat: float
    lng: float = 0.0
    lon: float = 0.0
    tipo: str = ""
    fecha: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_lng(cls, values):
        if isinstance(values, dict):
            if "lng" in values and "lon" not in values:
                values["lon"] = values["lng"]
            elif "lon" in values and "lng" not in values:
                values["lng"] = values["lon"]
        return values


class PredictionRequest(_CamelSnakeMixin):
    lat: float = 0.0
    lon: float = 0.0
    radio_km: float = 5.0
    dias_historicos: int = 90
    dias_prediccion: int = 7
    tipos_delito: List[str] = []
    fecha_inicio: str = ""
    fecha_fin: str = ""
    hours_ahead: int = 8
    puntos: List[InputPoint] = []


class HotspotPoint(BaseModel):
    lat: float
    lon: float
    intensidad: float
    tipo_delito: str
    cluster_id: int


class PredictionResult(BaseModel):
    hotspots: List[HotspotPoint]
    tendencia: str  # alza, baja, estable
    tasa_cambio: float
    confianza: float
    periodo: str
    cells: List[dict] = []  # Flattened cells for frontend compatibility


class AnomalyAlert(BaseModel):
    lat: float
    lon: float
    tipo_delito: str
    frecuencia_esperada: float
    frecuencia_observada: float
    z_score: float
    severidad: str  # critica, alta, media, baja


class AnomalyRequest(_CamelSnakeMixin):
    lat: float = 0.0
    lon: float = 0.0
    radio_km: float = 5.0
    dias: int = 30
    umbral_z: float = 2.0
    fecha_inicio: str = ""
    fecha_fin: str = ""
    puntos: List[InputPoint] = []


class AnomalyResponse(BaseModel):
    alertas: List[AnomalyAlert]
    anomalies: List[dict] = []  # Frontend-compatible format
    total_anomalias: int


class PatrolRoutePoint(BaseModel):
    lat: float
    lon: float
    prioridad: int
    tiempo_sugerido_min: int
    razon: str


class PatrolRouteRequest(_CamelSnakeMixin):
    lat_centro: float = 0.0
    lon_centro: float = 0.0
    radio_km: float = 10.0
    num_puntos: int = 8
    turno: str = "noche"
    puntos: List[InputPoint] = []
    top_cells: List[dict] = []


class PatrolRouteResponse(BaseModel):
    puntos: List[PatrolRoutePoint]
    routes: List[dict] = []  # Frontend-compatible format
    distancia_total_km: float
    tiempo_estimado_min: int


class PredictiveStatsResponse(BaseModel):
    total_predicciones: int
    precision_historica: float
    hotspots_activos: int
    anomalias_activas: int
    ultima_actualizacion: str
