from fastapi import APIRouter
from .models import SemanticReportRequest, SemanticReportResponse
from .service import analysis_service

router = APIRouter(prefix="/analysis", tags=["Analysis"])


@router.post("/semantic-report", response_model=SemanticReportResponse)
async def generate_semantic_report(req: SemanticReportRequest):
    """Generate a semantic report correlating search params with results."""
    return await analysis_service.generate_report(req)
