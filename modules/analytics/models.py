"""Analytics models — Trends, Predictions, Clusters"""
from typing import List, Optional
from pydantic import BaseModel


class TrendPoint(BaseModel):
    fecha: str
    count: int
    tipo: str


class TrendSeries(BaseModel):
    name: str
    points: List[TrendPoint]


class TrendsRequest(BaseModel):
    detections: List[dict]
    group_by: str = "day"  # "day" | "week" | "hour"


class TrendsResponse(BaseModel):
    series: List[TrendSeries]
    total_detections: int
    period: str


class PredictionPoint(BaseModel):
    fecha: str
    predicted: float
    lower_bound: float
    upper_bound: float


class PredictionRequest(BaseModel):
    series: List[dict]  # [{fecha: str, count: int}, ...]
    periods: int = 7


class PredictionResponse(BaseModel):
    predictions: List[PredictionPoint]
    model_used: str
    confidence: float


class ClusterInfo(BaseModel):
    cluster_id: int
    label: str
    count: int
    representative_items: List[str]


class ClustersRequest(BaseModel):
    entities: List[dict]  # [{label: str, ...}, ...]


class ClustersResponse(BaseModel):
    clusters: List[ClusterInfo]
    total: int
