"""Label Taxonomy & Synonyms router"""
from fastapi import APIRouter
from typing import List

from modules.labels.models import (
    TaxonomyResponse, SynonymMap, ResolveRequest, ResolveResponse
)
from modules.labels.service import label_taxonomy_service

router = APIRouter(prefix="/labels", tags=["Labels & Taxonomy"])


@router.get("/taxonomy", response_model=TaxonomyResponse)
async def get_taxonomy():
    """Returns the full label taxonomy tree."""
    return label_taxonomy_service.get_taxonomy()


@router.get("/synonyms/{label}", response_model=SynonymMap)
async def get_synonyms(label: str):
    """Returns synonyms for a given label (English or Spanish)."""
    return label_taxonomy_service.get_synonyms(label)


@router.post("/resolve", response_model=ResolveResponse)
async def resolve_labels(request: ResolveRequest):
    """Batch-resolve labels to their Spanish translation, category, and hierarchy."""
    return label_taxonomy_service.resolve_labels(request.labels)
