"""Data Quality Diagnostics — Pydantic models"""
from typing import List, Dict, Optional
from pydantic import BaseModel


class DataQualityRequest(BaseModel):
    dataset_stats: Dict[str, int]  # {category_name: sample_count}
    min_resolution_avgs: Optional[Dict[str, float]] = None  # {category: avg_min_resolution}


class CategoryQuality(BaseModel):
    name: str
    count: int
    quality_score: float  # 0.0 - 1.0
    min_resolution_avg: Optional[float] = None


class DataQualityResponse(BaseModel):
    total_samples: int
    categories: List[CategoryQuality]
    gaps: List[str]  # under-represented categories
    precision_baseline: float  # estimated from sample count
    recommendations: List[str]
