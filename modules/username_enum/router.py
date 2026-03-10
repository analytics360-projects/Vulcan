"""Username enumeration router — findme-based platform detection."""
import json
import time
from fastapi import APIRouter, Query, Request
from typing import Optional

from config import logger
from modules.username_enum.models import UsernameEnumResponse
from modules.username_enum.service import enumerate_username

router = APIRouter(prefix="/username", tags=["Username Enumeration"])


@router.get("/enumerate", response_model=UsernameEnumResponse)
async def enumerate_endpoint(
    request: Request,
    username: str = Query(..., min_length=1, max_length=100, description="Username to search across platforms"),
    platforms: Optional[str] = Query(None, description="Comma-separated platform names to check (omit for all 400+)"),
    max_concurrent: int = Query(50, ge=5, le=100, description="Max concurrent requests"),
):
    """Enumerate a username across 400+ platforms to find active accounts."""
    client = request.client.host if request.client else "?"
    logger.info(f"[USERNAME-ROUTER] Enumerate request from {client}: username={username}")
    t0 = time.perf_counter()

    platforms_filter = [p.strip() for p in platforms.split(",") if p.strip()] if platforms else None

    result = await enumerate_username(
        username=username,
        platforms_filter=platforms_filter,
        max_concurrent=max_concurrent,
    )

    elapsed = (time.perf_counter() - t0) * 1000
    # Log found platforms as JSON
    found_json = json.dumps([h.model_dump() for h in result.platforms_found], default=str, ensure_ascii=False, indent=2)
    logger.info(
        f"[USERNAME-ENUM] RESPONSE JSON: username={username} "
        f"found={result.total_found}/{result.total_checked} ({elapsed:.0f}ms)\n{found_json}"
    )
    return result
