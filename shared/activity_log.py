"""
Vulcan Activity Log — In-memory ring buffer for API request tracking.
Stores the last N requests with timing, status, and params for the dashboard.
"""
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional
import threading


@dataclass
class ActivityEntry:
    id: int = 0
    timestamp: str = ""
    method: str = ""
    path: str = ""
    query: str = ""
    status_code: int = 0
    duration_ms: float = 0.0
    client_ip: str = ""
    module: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class ActivityLog:
    """Thread-safe ring buffer of recent API activity."""

    def __init__(self, max_entries: int = 500):
        self._entries: deque[ActivityEntry] = deque(maxlen=max_entries)
        self._counter = 0
        self._lock = threading.Lock()
        self._stats = {
            "total_requests": 0,
            "total_errors": 0,
            "by_module": {},
            "by_status": {},
        }

    def add(self, entry: ActivityEntry):
        with self._lock:
            self._counter += 1
            entry.id = self._counter
            self._entries.append(entry)

            self._stats["total_requests"] += 1
            if entry.status_code >= 400:
                self._stats["total_errors"] += 1

            mod = entry.module or "unknown"
            self._stats["by_module"][mod] = self._stats["by_module"].get(mod, 0) + 1

            sc = str(entry.status_code)
            self._stats["by_status"][sc] = self._stats["by_status"].get(sc, 0) + 1

    def recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            entries = list(self._entries)
        return [e.to_dict() for e in reversed(entries[:limit if limit else len(entries)])][:limit]

    def stats(self) -> dict:
        with self._lock:
            return {**self._stats}

    def search(self, query: str, limit: int = 50) -> list[dict]:
        q = query.lower()
        with self._lock:
            entries = list(self._entries)
        matches = [e for e in reversed(entries) if q in e.path.lower() or q in (e.query or "").lower() or q in (e.module or "").lower()]
        return [e.to_dict() for e in matches[:limit]]


# Singleton
activity_log = ActivityLog()
