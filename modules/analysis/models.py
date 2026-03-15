from typing import List, Dict, Optional, Any
from pydantic import BaseModel


class SemanticReportRequest(BaseModel):
    search_params: Dict[str, Any] = {}
    keywords: List[str] = []
    results_summary: Dict[str, Any] = {}
    platform_stats: Dict[str, int] = {}


class SemanticReportResponse(BaseModel):
    report_markdown: str
    generated_at: str
    method: str  # "llm" or "template"
