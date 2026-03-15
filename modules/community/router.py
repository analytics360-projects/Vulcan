"""Community detection router — graph analysis endpoints."""
from fastapi import APIRouter, HTTPException
from config import logger
from modules.community.models import (
    DetectCommunitiesRequest, DetectCommunitiesResponse,
    IntelligenceReportRequest, IntelligenceReportResponse,
)
from modules.community.service import community_service

router = APIRouter(prefix="/community", tags=["Community Detection"])


@router.post("/DetectCommunities", response_model=DetectCommunitiesResponse)
async def detect_communities(request: DetectCommunitiesRequest):
    """Detect communities using Louvain algorithm with weighted edges."""
    if not request.nodes:
        raise HTTPException(status_code=400, detail="Se necesitan nodos")
    try:
        return community_service.detect(request)
    except Exception as e:
        logger.exception(f"Community detection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/IntelligenceReport", response_model=IntelligenceReportResponse)
async def intelligence_report(request: IntelligenceReportRequest):
    """Generate intelligence report from graph analysis."""
    try:
        return await community_service.intelligence_report(request)
    except Exception as e:
        logger.exception(f"Intelligence report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/EnrichedGraph/{carpeta_id}")
async def enriched_graph(carpeta_id: str):
    """Get enriched graph data for a carpeta (from stored results)."""
    try:
        from modules.sans.ravendb_client import get_store
        store = get_store()
        with store.open_session() as session:
            doc = session.load(f"graph_analysis/{carpeta_id}")
            if not doc:
                raise HTTPException(status_code=404, detail="No graph data found")
            return doc.__dict__ if hasattr(doc, '__dict__') else doc
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Enriched graph error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
