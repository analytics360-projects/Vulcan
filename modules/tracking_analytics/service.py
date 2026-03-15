"""Tracking Analytics service — heatmap density, speed/distance anomalies, idle clusters."""
import math
from typing import List, Optional

import numpy as np

from config import logger

EARTH_RADIUS_M = 6_371_000.0


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance in meters between two WGS-84 points."""
    rlat1, rlng1, rlat2, rlng2 = map(math.radians, (lat1, lng1, lat2, lng2))
    dlat = rlat2 - rlat1
    dlng = rlng2 - rlng1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


class TrackingAnalyticsService:
    """Stateless tracking analysis: density grids, anomaly detection, idle clusters."""

    # ── Density grid ──

    def density_grid(
        self,
        points: list[dict],
        grid_size: int = 20,
    ) -> dict:
        """
        Build a 2-D density grid from weighted points using numpy histogram2d.

        Args:
            points: list of {lat, lng, weight}.
            grid_size: cells per axis.

        Returns:
            dict with grid (2-D list), bounds, grid_size.
        """
        if not points:
            return {"grid": [], "bounds": None, "grid_size": grid_size}

        lats = np.array([p["lat"] for p in points], dtype=np.float64)
        lngs = np.array([p["lng"] for p in points], dtype=np.float64)
        weights = np.array([p.get("weight", 1.0) for p in points], dtype=np.float64)

        # histogram2d with weights
        grid, lat_edges, lng_edges = np.histogram2d(
            lats, lngs, bins=grid_size, weights=weights,
        )

        # Normalise to 0-1
        max_val = float(grid.max())
        if max_val > 0:
            grid_norm = grid / max_val
        else:
            grid_norm = grid

        return {
            "grid": grid_norm.tolist(),
            "bounds": {
                "lat_min": float(lat_edges[0]),
                "lat_max": float(lat_edges[-1]),
                "lng_min": float(lng_edges[0]),
                "lng_max": float(lng_edges[-1]),
            },
            "grid_size": grid_size,
        }

    # ── Anomaly detection ──

    def detect_anomalies(
        self,
        points: list[dict],
        z_threshold: float = 2.5,
    ) -> dict:
        """
        Detect anomalies in a tracking sequence using z-score on speed and
        inter-point distance.

        Args:
            points: list of {lat, lng, speed, timestamp} sorted by timestamp.
            z_threshold: standard deviations above which a value is flagged.

        Returns:
            dict with speed_outliers, distance_outliers, idle_clusters, summary.
        """
        if len(points) < 2:
            return {
                "speed_outliers": [],
                "distance_outliers": [],
                "idle_clusters": [],
                "summary": {"total_points": len(points), "speed_anomalies": 0, "distance_anomalies": 0, "idle_clusters": 0},
            }

        # Sort by timestamp
        sorted_pts = sorted(points, key=lambda p: p["timestamp"])

        # Compute inter-point distances
        distances: list[float] = []
        for i in range(1, len(sorted_pts)):
            d = _haversine_m(
                sorted_pts[i - 1]["lat"], sorted_pts[i - 1]["lng"],
                sorted_pts[i]["lat"], sorted_pts[i]["lng"],
            )
            distances.append(d)

        speeds = np.array([p.get("speed", 0.0) for p in sorted_pts], dtype=np.float64)
        dist_arr = np.array(distances, dtype=np.float64)

        # Z-scores
        speed_outliers = self._z_score_outliers(speeds, z_threshold, sorted_pts, "speed")
        distance_outliers = self._z_score_outliers(dist_arr, z_threshold, sorted_pts[1:], "distance")

        # Idle clusters
        idle_clusters = self.detect_idle_clusters(sorted_pts)

        return {
            "speed_outliers": speed_outliers,
            "distance_outliers": distance_outliers,
            "idle_clusters": idle_clusters,
            "summary": {
                "total_points": len(sorted_pts),
                "speed_anomalies": len(speed_outliers),
                "distance_anomalies": len(distance_outliers),
                "idle_clusters": len(idle_clusters),
            },
        }

    # ── Idle clusters ──

    def detect_idle_clusters(
        self,
        points: list[dict],
        min_duration_min: float = 5.0,
        radius_m: float = 50.0,
    ) -> list[dict]:
        """
        Simple distance-based idle detection: consecutive points within
        `radius_m` for at least `min_duration_min` minutes.

        Args:
            points: sorted list of {lat, lng, speed, timestamp}.
            min_duration_min: minimum cluster duration in minutes.
            radius_m: maximum radius to consider points as "idle".

        Returns:
            list of idle cluster dicts with centroid, duration, point count.
        """
        if len(points) < 2:
            return []

        sorted_pts = sorted(points, key=lambda p: p["timestamp"])
        clusters: list[dict] = []

        cluster_start = 0
        for i in range(1, len(sorted_pts)):
            anchor = sorted_pts[cluster_start]
            current = sorted_pts[i]
            dist = _haversine_m(anchor["lat"], anchor["lng"], current["lat"], current["lng"])

            if dist > radius_m:
                # Check if accumulated cluster meets duration threshold
                self._maybe_emit_cluster(sorted_pts, cluster_start, i - 1, min_duration_min, clusters)
                cluster_start = i

        # Final cluster
        self._maybe_emit_cluster(sorted_pts, cluster_start, len(sorted_pts) - 1, min_duration_min, clusters)

        return clusters

    # ── Helpers ──

    @staticmethod
    def _z_score_outliers(
        values: np.ndarray,
        threshold: float,
        source_points: list[dict],
        label: str,
    ) -> list[dict]:
        """Return points whose corresponding value exceeds z-score threshold."""
        if len(values) < 2:
            return []

        mean = float(np.mean(values))
        std = float(np.std(values))
        if std == 0:
            return []

        outliers: list[dict] = []
        for idx, val in enumerate(values):
            z = (float(val) - mean) / std
            if abs(z) > threshold:
                pt = source_points[idx]
                outliers.append({
                    "index": idx,
                    "lat": pt["lat"],
                    "lng": pt["lng"],
                    "timestamp": pt["timestamp"],
                    "value": round(float(val), 4),
                    "z_score": round(z, 4),
                    "type": label,
                })
        return outliers

    @staticmethod
    def _maybe_emit_cluster(
        pts: list[dict],
        start: int,
        end: int,
        min_duration_min: float,
        out: list[dict],
    ) -> None:
        """Emit an idle cluster if it meets the minimum duration."""
        if end <= start:
            return
        t_start = pts[start]["timestamp"]
        t_end = pts[end]["timestamp"]
        duration_min = (t_end - t_start) / 60.0
        if duration_min < min_duration_min:
            return

        lats = [pts[i]["lat"] for i in range(start, end + 1)]
        lngs = [pts[i]["lng"] for i in range(start, end + 1)]

        out.append({
            "centroid_lat": round(sum(lats) / len(lats), 6),
            "centroid_lng": round(sum(lngs) / len(lngs), 6),
            "start_timestamp": t_start,
            "end_timestamp": t_end,
            "duration_min": round(duration_min, 2),
            "point_count": end - start + 1,
        })


# Singleton
tracking_analytics_service = TrackingAnalyticsService()
