"""Monitoring router — SANS temporal tracking snapshots."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any

from modules.monitoring.service import store_snapshot, get_history

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


class SnapshotRequest(BaseModel):
    investigation_id: str
    results_summary: Dict[str, Any] = {}


@router.post("/snapshot")
async def create_snapshot(request: SnapshotRequest):
    """Store a new snapshot of results for temporal tracking."""
    snapshot = store_snapshot(request.investigation_id, request.results_summary)
    return {"snapshot": snapshot}


@router.get("/history/{investigation_id}")
async def monitoring_history(investigation_id: str):
    """Get all snapshots for a given investigation."""
    history = get_history(investigation_id)
    return {"investigation_id": investigation_id, "snapshots": history, "count": len(history)}
