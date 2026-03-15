"""Social Graph router — G3 Redes de Vínculos Sociales"""
from fastapi import APIRouter, HTTPException

from config import logger
from modules.social_graph.models import BuildGraphRequest, BuildGraphResponse
from modules.social_graph.service import social_graph_service

router = APIRouter(prefix="/social-graph", tags=["social-graph"])


@router.post("/build", response_model=BuildGraphResponse)
async def build_social_graph(request: BuildGraphRequest):
    """Build a social relationship graph from discovered profiles."""
    try:
        return social_graph_service.build_from_sans_results(request.profiles)
    except Exception as e:
        logger.exception(f"Error building social graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))
