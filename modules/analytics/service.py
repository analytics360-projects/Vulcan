"""Analytics service — Trends, Predictions, Clusters"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List

import numpy as np

from config import logger
from modules.analytics.models import (
    TrendPoint,
    TrendSeries,
    TrendsResponse,
    PredictionPoint,
    PredictionResponse,
    ClusterInfo,
    ClustersResponse,
)


class AnalyticsService:
    """Stateless analytics service for MIA detection data."""

    def get_trends(self, detections: List[dict], group_by: str = "day") -> TrendsResponse:
        """Group detections by date (day/week/hour) and type, return time series per type."""
        logger.info(f"[ANALYTICS] get_trends: {len(detections)} detections, group_by={group_by}")

        type_date_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        total = len(detections)

        for det in detections:
            tipo = det.get("tipo") or det.get("type") or det.get("analysisType") or "unknown"
            fecha_raw = det.get("fecha") or det.get("date") or det.get("createdAt") or ""
            key = self._date_key(fecha_raw, group_by)
            if key:
                type_date_counts[tipo][key] += 1

        series: List[TrendSeries] = []
        for tipo, date_counts in sorted(type_date_counts.items()):
            points = [
                TrendPoint(fecha=fecha, count=count, tipo=tipo)
                for fecha, count in sorted(date_counts.items())
            ]
            series.append(TrendSeries(name=tipo, points=points))

        return TrendsResponse(
            series=series,
            total_detections=total,
            period=group_by,
        )

    def predict(self, series: List[dict], periods: int = 7) -> PredictionResponse:
        """Simple linear regression prediction using numpy polyfit."""
        logger.info(f"[ANALYTICS] predict: {len(series)} data points, periods={periods}")

        # Extract dates and counts
        dates = []
        counts = []
        for item in series:
            fecha = item.get("fecha") or item.get("date") or ""
            count = item.get("count", 0)
            if isinstance(count, (int, float)):
                dates.append(fecha)
                counts.append(float(count))

        if len(counts) < 2:
            return PredictionResponse(predictions=[], model_used="insufficient_data", confidence=0.0)

        x = np.arange(len(counts), dtype=float)
        y = np.array(counts, dtype=float)

        # Linear regression
        coeffs = np.polyfit(x, y, 1)
        poly = np.poly1d(coeffs)

        # Standard deviation of residuals for confidence interval
        residuals = y - poly(x)
        std_dev = float(np.std(residuals)) if len(residuals) > 1 else 0.0

        # R-squared as confidence
        ss_res = float(np.sum(residuals ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r_squared = max(0.0, 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0)

        # Generate future predictions
        predictions: List[PredictionPoint] = []
        last_date = self._parse_date(dates[-1]) if dates else datetime.utcnow()

        for i in range(1, periods + 1):
            future_x = len(counts) - 1 + i
            predicted = max(0.0, float(poly(future_x)))
            lower = max(0.0, predicted - std_dev)
            upper = predicted + std_dev

            future_date = last_date + timedelta(days=i)
            predictions.append(PredictionPoint(
                fecha=future_date.strftime("%Y-%m-%d"),
                predicted=round(predicted, 2),
                lower_bound=round(lower, 2),
                upper_bound=round(upper, 2),
            ))

        return PredictionResponse(
            predictions=predictions,
            model_used="linear_regression",
            confidence=round(r_squared, 4),
        )

    def cluster_entities(self, entities: List[dict]) -> ClustersResponse:
        """Group entities by label similarity (simple string matching/grouping)."""
        logger.info(f"[ANALYTICS] cluster_entities: {len(entities)} entities")

        label_groups: dict[str, list[str]] = defaultdict(list)

        for entity in entities:
            label = (entity.get("label") or entity.get("name") or entity.get("tipo") or "sin_etiqueta").strip().lower()
            # Normalize: group by base word (first word or full label)
            base = label.split()[0] if " " in label else label
            representative = entity.get("label") or entity.get("name") or label
            label_groups[base].append(representative)

        clusters: List[ClusterInfo] = []
        for idx, (base, items) in enumerate(sorted(label_groups.items(), key=lambda x: -len(x[1]))):
            # Pick up to 5 representative items (unique)
            unique_items = list(dict.fromkeys(items))[:5]
            clusters.append(ClusterInfo(
                cluster_id=idx,
                label=base.capitalize(),
                count=len(items),
                representative_items=unique_items,
            ))

        return ClustersResponse(
            clusters=clusters,
            total=len(entities),
        )

    # ── Helpers ──

    @staticmethod
    def _date_key(fecha_raw: str, group_by: str) -> str | None:
        """Convert a date string to a grouping key."""
        dt = AnalyticsService._parse_date(fecha_raw)
        if dt is None:
            return None
        if group_by == "hour":
            return dt.strftime("%Y-%m-%d %H:00")
        if group_by == "week":
            # ISO week start (Monday)
            start = dt - timedelta(days=dt.weekday())
            return start.strftime("%Y-%m-%d")
        # default: day
        return dt.strftime("%Y-%m-%d")

    @staticmethod
    def _parse_date(fecha_raw: str) -> datetime | None:
        """Try multiple date formats."""
        if not fecha_raw:
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
            try:
                return datetime.strptime(fecha_raw[:len(fmt.replace("%f", "000000"))], fmt)
            except (ValueError, IndexError):
                continue
        # Last resort: try parsing just the first 10 chars as date
        try:
            return datetime.strptime(fecha_raw[:10], "%Y-%m-%d")
        except (ValueError, IndexError):
            return None


analytics_service = AnalyticsService()
