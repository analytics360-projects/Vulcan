"""Geospatial hotspot models — IC4 Hotspots Geoespaciales."""
from typing import List, Optional, Any
from pydantic import BaseModel, Field, model_validator


# ── Request models ──

class CoordinatePoint(BaseModel):
    lat: float
    lng: float
    tipo: str = "Sin tipo"
    fecha: str = ""
    folio: Optional[Any] = None


class _CamelSnakeMixin(BaseModel):
    """Accept both camelCase (from Balder proxy) and snake_case field names."""

    @model_validator(mode="before")
    @classmethod
    def _accept_camel(cls, values):
        if isinstance(values, dict):
            mapping = {
                "fechaInicio": "fecha_inicio",
                "fechaFin": "fecha_fin",
                "tipoIncidente": "tipo_incidente",
                "gridSize": "grid_size",
                "minSamples": "min_samples",
            }
            for camel, snake in mapping.items():
                if camel in values and snake not in values:
                    values[snake] = values[camel]
        return values


class HotspotRequest(_CamelSnakeMixin):
    fecha_inicio: str = ""
    fecha_fin: str = ""
    tipo_incidente: Optional[str] = None
    eps: float = 0.01
    min_samples: int = 3
    puntos: List[CoordinatePoint] = []


class HeatmapRequest(_CamelSnakeMixin):
    fecha_inicio: str = ""
    fecha_fin: str = ""
    tipo_incidente: Optional[str] = None
    grid_size: int = 50
    puntos: List[CoordinatePoint] = []


# ── Response models ──

class HotspotCluster(BaseModel):
    cluster_id: int
    centroide_lat: float
    centroide_lng: float
    radio_km: float
    count: int
    tipo_predominante: str
    puntos: List[CoordinatePoint]


class HotspotResponse(BaseModel):
    clusters: List[HotspotCluster]
    total_puntos: int
    total_clusters: int


class HeatmapCell(BaseModel):
    lat: float
    lng: float
    densidad: float


class HeatmapResponse(BaseModel):
    celdas: List[HeatmapCell]
    min_densidad: float
    max_densidad: float
