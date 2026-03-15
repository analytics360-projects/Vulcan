"""Data Quality Diagnostics — Service"""
from typing import Dict, Optional, List

from config import logger
from modules.data_quality.models import (
    CategoryQuality,
    DataQualityResponse,
)


class DataQualityService:
    """Heuristic-based data quality diagnostics for MIA datasets."""

    MIN_SAMPLES_THRESHOLD = 10  # categories below this are considered gaps
    GOOD_SAMPLES_THRESHOLD = 50  # categories above this have high quality

    def analyze(
        self,
        dataset_stats: Dict[str, int],
        min_resolution_avgs: Optional[Dict[str, float]] = None,
    ) -> DataQualityResponse:
        """Analyze dataset statistics and return quality diagnostics."""
        if not dataset_stats:
            return DataQualityResponse(
                total_samples=0,
                categories=[],
                gaps=[],
                precision_baseline=0.0,
                recommendations=["No hay datos para analizar. Cargue evidencias al sistema."],
            )

        total_samples = sum(dataset_stats.values())
        max_count = max(dataset_stats.values()) if dataset_stats else 1

        categories: List[CategoryQuality] = []
        gaps: List[str] = []
        recommendations: List[str] = []

        for name, count in sorted(dataset_stats.items(), key=lambda x: -x[1]):
            # Quality score: based on sample count relative to thresholds
            if count >= self.GOOD_SAMPLES_THRESHOLD:
                quality_score = min(1.0, 0.7 + (count / max_count) * 0.3)
            elif count >= self.MIN_SAMPLES_THRESHOLD:
                quality_score = 0.4 + (count / self.GOOD_SAMPLES_THRESHOLD) * 0.3
            else:
                quality_score = max(0.1, count / self.MIN_SAMPLES_THRESHOLD * 0.4)
                gaps.append(name)

            res_avg = None
            if min_resolution_avgs and name in min_resolution_avgs:
                res_avg = min_resolution_avgs[name]
                # Penalize low resolution
                if res_avg < 100:
                    quality_score *= 0.7
                elif res_avg < 200:
                    quality_score *= 0.85

            categories.append(CategoryQuality(
                name=name,
                count=count,
                quality_score=round(min(1.0, quality_score), 3),
                min_resolution_avg=res_avg,
            ))

        # Precision baseline heuristic
        precision_baseline = min(0.95, total_samples / 1000)
        if precision_baseline < 0.3:
            precision_baseline = max(0.1, precision_baseline)

        # Build recommendations
        if total_samples < 100:
            recommendations.append(
                f"Dataset muy reducido ({total_samples} muestras). "
                "Se recomienda un minimo de 100 muestras para estimaciones confiables."
            )

        if gaps:
            gap_names = ", ".join(gaps[:5])
            recommendations.append(
                f"Categorias sub-representadas (<{self.MIN_SAMPLES_THRESHOLD} muestras): {gap_names}. "
                "Agregue mas evidencias de estas categorias para mejorar precision."
            )

        # Check for imbalance
        if categories and max_count > 0:
            min_count = min(c.count for c in categories)
            if max_count > min_count * 10 and len(categories) > 1:
                recommendations.append(
                    "Desbalance significativo entre categorias. "
                    "La categoria mas grande es 10x+ la mas pequena. "
                    "Considere balancear el dataset."
                )

        if not recommendations:
            recommendations.append(
                "Dataset en buen estado. Mantenga la ingesta de evidencias para mejorar continuamente."
            )

        return DataQualityResponse(
            total_samples=total_samples,
            categories=categories,
            gaps=gaps,
            precision_baseline=round(precision_baseline, 4),
            recommendations=recommendations,
        )


# Singleton
data_quality_service = DataQualityService()
