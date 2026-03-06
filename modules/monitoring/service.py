"""Monitoring service — stores snapshots of SANS search results over time."""
import json
import hashlib
from datetime import datetime
from pathlib import Path
from config import logger

SNAPSHOTS_DIR = Path("data/monitoring_snapshots")
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def _snapshot_path(investigation_id: str) -> Path:
    safe_id = investigation_id.replace("/", "_").replace("\\", "_")
    return SNAPSHOTS_DIR / f"{safe_id}.json"


def store_snapshot(investigation_id: str, results_summary: dict) -> dict:
    """Store a snapshot for a given investigation."""
    path = _snapshot_path(investigation_id)

    history = []
    if path.exists():
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            history = []

    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "summary": results_summary,
        "hash": hashlib.sha256(json.dumps(results_summary, sort_keys=True).encode()).hexdigest()[:16],
    }

    # Compute diff vs previous snapshot
    if history:
        prev = history[-1]["summary"]
        diff = {}
        all_keys = set(list(prev.keys()) + list(results_summary.keys()))
        for k in all_keys:
            old_val = prev.get(k, 0)
            new_val = results_summary.get(k, 0)
            if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
                delta = new_val - old_val
                if delta != 0:
                    diff[k] = {"previous": old_val, "current": new_val, "delta": delta}
        snapshot["diff"] = diff
    else:
        snapshot["diff"] = {}

    history.append(snapshot)
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Snapshot stored for {investigation_id}: {len(history)} total")
    return snapshot


def get_history(investigation_id: str) -> list[dict]:
    """Get all snapshots for a given investigation."""
    path = _snapshot_path(investigation_id)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
