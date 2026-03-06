"""Geo/LADA router — geographic enrichment for SANS results."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

from modules.geo.lada import resolve_lada, get_all_ladas

router = APIRouter(prefix="/geo", tags=["geo"])


class LadaResolveRequest(BaseModel):
    phones: List[str] = []


@router.get("/lada/all")
async def lada_all():
    """Return full LADA lookup table."""
    return {"ladas": get_all_ladas()}


@router.post("/lada/resolve")
async def lada_resolve(request: LadaResolveRequest):
    """Resolve LADA codes from phone numbers."""
    results = []
    for phone in request.phones:
        info = resolve_lada(phone)
        results.append({"phone": phone, "resolved": info})
    return {"results": results}
