"""Geospatial service — DBSCAN clustering + heatmap grid."""
from typing import List
from collections import Counter

import numpy as np
from sklearn.cluster import DBSCAN

from config import logger
from modules.geospatial.models import (
    CoordinatePoint,
    HotspotCluster,
    HotspotResponse,
    HeatmapCell,
    HeatmapResponse,
)

EARTH_RADIUS_KM = 6371.0


class GeospatialService:
    """Stateless geospatial analysis: hotspot detection and heatmap generation."""

    def calculate_hotspots(
        self,
        points: List[CoordinatePoint],
        eps: float = 0.01,
        min_samples: int = 3,
    ) -> HotspotResponse:
        """
        Detect spatial clusters using DBSCAN with haversine metric.

        Args:
            points: list of coordinate points to cluster.
            eps: neighbourhood radius in km.
            min_samples: minimum points to form a cluster.
        """
        if not points:
            return HotspotResponse(clusters=[], total_puntos=0, total_clusters=0)

        # Convert to radians for haversine
        coords_rad = np.array([[np.radians(p.lat), np.radians(p.lng)] for p in points])
        eps_rad = eps / EARTH_RADIUS_KM  # km → radians

        db = DBSCAN(
            eps=eps_rad,
            min_samples=min_samples,
            metric="haversine",
            algorithm="ball_tree",
        )
        labels = db.fit_predict(coords_rad)

        # Group points by cluster label (-1 = noise, skip)
        cluster_map: dict[int, list[int]] = {}
        for idx, label in enumerate(labels):
            if label == -1:
                continue
            cluster_map.setdefault(label, []).append(idx)

        clusters: list[HotspotCluster] = []
        for cluster_id, indices in cluster_map.items():
            cluster_points = [points[i] for i in indices]
            lats = np.array([p.lat for p in cluster_points])
            lngs = np.array([p.lng for p in cluster_points])

            centroid_lat = float(np.mean(lats))
            centroid_lng = float(np.mean(lngs))

            # Calculate max radius from centroid (haversine)
            radius_km = self._max_radius_km(centroid_lat, centroid_lng, lats, lngs)

            # Predominant incident type
            tipo_counts = Counter(p.tipo for p in cluster_points)
            tipo_predominante = tipo_counts.most_common(1)[0][0]

            clusters.append(
                HotspotCluster(
                    cluster_id=int(cluster_id),
                    centroide_lat=centroid_lat,
                    centroide_lng=centroid_lng,
                    radio_km=round(radius_km, 3),
                    count=len(cluster_points),
                    tipo_predominante=tipo_predominante,
                    puntos=cluster_points,
                )
            )

        # Sort by count descending
        clusters.sort(key=lambda c: c.count, reverse=True)

        return HotspotResponse(
            clusters=clusters,
            total_puntos=len(points),
            total_clusters=len(clusters),
        )

    def calculate_heatmap(
        self,
        points: List[CoordinatePoint],
        grid_size: int = 50,
    ) -> HeatmapResponse:
        """
        Generate a density heatmap by binning points into a grid.

        Args:
            points: list of coordinate points.
            grid_size: number of cells per axis.
        """
        if not points:
            return HeatmapResponse(celdas=[], min_densidad=0.0, max_densidad=0.0)

        lats = np.array([p.lat for p in points])
        lngs = np.array([p.lng for p in points])

        lat_min, lat_max = float(lats.min()), float(lats.max())
        lng_min, lng_max = float(lngs.min()), float(lngs.max())

        # Add small padding to avoid edge issues
        lat_pad = max((lat_max - lat_min) * 0.01, 1e-6)
        lng_pad = max((lng_max - lng_min) * 0.01, 1e-6)
        lat_min -= lat_pad
        lat_max += lat_pad
        lng_min -= lng_pad
        lng_max += lng_pad

        lat_step = (lat_max - lat_min) / grid_size
        lng_step = (lng_max - lng_min) / grid_size

        # Bin points
        grid = np.zeros((grid_size, grid_size), dtype=np.float64)
        for lat, lng in zip(lats, lngs):
            row = min(int((lat - lat_min) / lat_step), grid_size - 1)
            col = min(int((lng - lng_min) / lng_step), grid_size - 1)
            grid[row, col] += 1.0

        max_count = float(grid.max())
        if max_count > 0:
            grid_norm = grid / max_count
        else:
            grid_norm = grid

        # Build cells (skip empty)
        celdas: list[HeatmapCell] = []
        for r in range(grid_size):
            for c in range(grid_size):
                density = float(grid_norm[r, c])
                if density > 0:
                    cell_lat = lat_min + (r + 0.5) * lat_step
                    cell_lng = lng_min + (c + 0.5) * lng_step
                    celdas.append(
                        HeatmapCell(lat=round(cell_lat, 6), lng=round(cell_lng, 6), densidad=round(density, 4))
                    )

        densities = [c.densidad for c in celdas] if celdas else [0.0]
        return HeatmapResponse(
            celdas=celdas,
            min_densidad=min(densities),
            max_densidad=max(densities),
        )

    # ── Helpers ──

    @staticmethod
    def _max_radius_km(
        center_lat: float, center_lng: float, lats: np.ndarray, lngs: np.ndarray
    ) -> float:
        """Calculate max distance (km) from centroid to any point using haversine."""
        clat = np.radians(center_lat)
        clng = np.radians(center_lng)
        plats = np.radians(lats)
        plngs = np.radians(lngs)

        dlat = plats - clat
        dlng = plngs - clng

        a = np.sin(dlat / 2) ** 2 + np.cos(clat) * np.cos(plats) * np.sin(dlng / 2) ** 2
        c = 2 * np.arcsin(np.sqrt(a))
        distances = EARTH_RADIUS_KM * c

        return float(np.max(distances)) if len(distances) > 0 else 0.0


# Singleton
geospatial_service = GeospatialService()
