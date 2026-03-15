"""
IC9 — Modus Operandi Detection Router
POST /intel/modus-operandi/index
POST /intel/modus-operandi/search
GET  /intel/modus-operandi/clusters
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

router = APIRouter(prefix="/intel", tags=["intelligence"])

_service = None


def _get_service():
    global _service
    if _service is None:
        try:
            from modules.intelligence.services.modus_operandi import ModusOperandiService
            _service = ModusOperandiService()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"ModusOperandiService no disponible: {e}")
    return _service


# ── Request / Response models ──────────────────────────────────

class IndexRequest(BaseModel):
    carpeta_id: int
    narrative_text: str = Field(..., min_length=10, description="Texto narrativo del hecho delictivo")
    metadata: Optional[Dict[str, Any]] = None


class IndexResponse(BaseModel):
    point_id: str
    carpeta_id: int


class SearchRequest(BaseModel):
    text: str = Field(..., min_length=5, description="Texto para buscar modus operandi similares")
    limit: int = Field(10, ge=1, le=100)
    min_score: float = Field(0.6, ge=0.0, le=1.0)


class SimilarNarrative(BaseModel):
    carpeta_id: Optional[int] = None
    text_preview: str = ""
    score: float = 0.0
    metadata: Dict[str, Any] = {}


class SearchResponse(BaseModel):
    results: List[SimilarNarrative]
    count: int


class ClusterNarrative(BaseModel):
    carpeta_id: Optional[int] = None
    text_preview: str = ""


class Cluster(BaseModel):
    cluster_id: int
    label: str
    narrativas: List[ClusterNarrative]
    count: int


class ClustersResponse(BaseModel):
    clusters: List[Cluster]
    total_clusters: int


# ── Endpoints ──────────────────────────────────────────────────

@router.post(
    "/modus-operandi/index",
    response_model=IndexResponse,
    summary="Indexar narrativa de hecho delictivo",
)
async def index_narrative(body: IndexRequest):
    """Genera embedding de la narrativa y la almacena en Qdrant para deteccion de modus operandi."""
    try:
        svc = _get_service()
        point_id = svc.index_narrative(
            carpeta_id=body.carpeta_id,
            narrative_text=body.narrative_text,
            metadata=body.metadata,
        )
        return IndexResponse(point_id=point_id, carpeta_id=body.carpeta_id)
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error indexando narrativa: {e}")


@router.post(
    "/modus-operandi/search",
    response_model=SearchResponse,
    summary="Buscar modus operandi similares",
)
async def search_similar(body: SearchRequest):
    """Busca narrativas semanticamente similares al texto proporcionado."""
    try:
        svc = _get_service()
        results = svc.search_similar(
            text=body.text,
            limit=body.limit,
            min_score=body.min_score,
        )
        return SearchResponse(
            results=[SimilarNarrative(**r) for r in results],
            count=len(results),
        )
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en busqueda: {e}")


@router.get(
    "/modus-operandi/clusters",
    response_model=ClustersResponse,
    summary="Agrupar narrativas por modus operandi",
)
async def get_clusters(min_cluster_size: int = 3):
    """Ejecuta clustering sobre todas las narrativas indexadas para detectar patrones."""
    try:
        svc = _get_service()
        clusters = svc.cluster_narratives(min_cluster_size=min_cluster_size)
        return ClustersResponse(
            clusters=[Cluster(**c) for c in clusters],
            total_clusters=len(clusters),
        )
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en clustering: {e}")
