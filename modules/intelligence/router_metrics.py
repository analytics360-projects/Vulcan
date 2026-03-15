"""
IC5 — Network Criminal Metrics endpoints
GET /intel/metrics/{carpeta_id}           — all metrics combined
GET /intel/metrics/{carpeta_id}/pagerank  — PageRank scores
GET /intel/metrics/{carpeta_id}/betweenness — Betweenness centrality
GET /intel/metrics/{carpeta_id}/communities — Louvain communities
"""
from fastapi import APIRouter, HTTPException
from config import logger

router = APIRouter(prefix="/intel/metrics", tags=["intelligence-metrics"])

_service = None
_init_error: str | None = None


def _get_service():
    """Lazy-init GraphMetricsService; caches result or error."""
    global _service, _init_error
    if _service is not None:
        return _service
    if _init_error is not None:
        return None
    try:
        from modules.intelligence.services.graph_metrics import GraphMetricsService
        _service = GraphMetricsService()
        return _service
    except Exception as e:
        _init_error = str(e)
        logger.warning(f"GraphMetricsService unavailable: {e}")
        return None


def _require_service():
    svc = _get_service()
    if svc is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Neo4j is not available",
                "message": _init_error or "GraphMetricsService failed to initialize",
            },
        )
    return svc


def _safe_call(fn, carpeta_id: int):
    """Execute a metrics function with graceful error handling."""
    try:
        svc = _require_service()
        return fn(svc, carpeta_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Graph metrics error (carpeta {carpeta_id}): {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Graph metrics computation failed", "message": str(e)},
        )


@router.get("/{carpeta_id}")
async def get_all_metrics(carpeta_id: int):
    """All network metrics for a carpeta: PageRank + Betweenness + Communities."""
    return _safe_call(lambda svc, cid: svc.get_all_metrics(cid), carpeta_id)


@router.get("/{carpeta_id}/pagerank")
async def get_pagerank(carpeta_id: int):
    """PageRank scores for nodes in a carpeta."""
    return {
        "carpeta_id": carpeta_id,
        "pagerank": _safe_call(lambda svc, cid: svc.calculate_pagerank(cid), carpeta_id),
    }


@router.get("/{carpeta_id}/betweenness")
async def get_betweenness(carpeta_id: int):
    """Betweenness centrality scores for nodes in a carpeta."""
    return {
        "carpeta_id": carpeta_id,
        "betweenness": _safe_call(lambda svc, cid: svc.calculate_betweenness(cid), carpeta_id),
    }


@router.get("/{carpeta_id}/communities")
async def get_communities(carpeta_id: int):
    """Community detection (Louvain / connected components fallback)."""
    return {
        "carpeta_id": carpeta_id,
        "communities": _safe_call(lambda svc, cid: svc.detect_communities(cid), carpeta_id),
    }
