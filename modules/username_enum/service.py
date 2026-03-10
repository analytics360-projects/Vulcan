"""Username enumeration service — async port of findme logic.

Checks 400+ platforms for username existence using httpx.
Detection methods: HTTP status codes and error message matching.
"""
import asyncio
import json
import re
import time
from pathlib import Path

import httpx

from config import logger
from modules.username_enum.models import PlatformHit, UsernameEnumResponse

_PLATFORMS: dict = {}
_DATA_PATH = Path(__file__).parent / "platforms.json"

# Concurrency control — don't blast 400 requests at once
MAX_CONCURRENT = 50
REQUEST_TIMEOUT = 10


def _load_platforms() -> dict:
    global _PLATFORMS
    if not _PLATFORMS:
        with open(_DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Remove schema key
        data.pop("$schema", None)
        _PLATFORMS = data
        logger.info(f"[USERNAME-ENUM] Loaded {len(_PLATFORMS)} platforms from platforms.json")
    return _PLATFORMS


async def _check_platform(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    platform_name: str,
    platform_data: dict,
    username: str,
) -> PlatformHit:
    """Check if username exists on a single platform."""
    # Validate regex if platform has one
    regex = platform_data.get("regexCheck")
    if regex:
        try:
            if not re.match(regex, username):
                return PlatformHit(
                    platform=platform_name,
                    url=platform_data.get("urlMain", ""),
                    status="not_found",
                )
        except re.error:
            pass

    # Build URL — use urlProbe if available, otherwise url
    url_template = platform_data.get("urlProbe") or platform_data.get("url", "")
    url = url_template.replace("{}", username)
    profile_url = platform_data.get("url", "").replace("{}", username)
    error_type = platform_data.get("errorType", "status_code")

    async with semaphore:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                **(platform_data.get("headers") or {}),
            }
            resp = await client.get(url, headers=headers, follow_redirects=True)

            if error_type == "status_code":
                found = resp.status_code != 404 and resp.status_code < 400
            elif error_type == "message":
                error_msgs = platform_data.get("errorMsg", [])
                if isinstance(error_msgs, str):
                    error_msgs = [error_msgs]
                text = resp.text
                found = not any(msg in text for msg in error_msgs)
            elif error_type == "response_url":
                error_url = platform_data.get("errorUrl", "")
                found = error_url not in str(resp.url)
            else:
                found = resp.status_code < 400

            return PlatformHit(
                platform=platform_name,
                url=profile_url,
                status="found" if found else "not_found",
                http_code=resp.status_code,
            )
        except Exception:
            return PlatformHit(
                platform=platform_name,
                url=profile_url,
                status="error",
            )


async def enumerate_username(
    username: str,
    platforms_filter: list[str] | None = None,
    max_concurrent: int = MAX_CONCURRENT,
) -> UsernameEnumResponse:
    """
    Enumerate username across all platforms.

    Args:
        username: The username to search for.
        platforms_filter: Optional list of platform names to check (subset).
        max_concurrent: Max concurrent HTTP requests.
    """
    logger.info(f"[USERNAME-ENUM] ══════ START ══════  username={username}")
    t0 = time.perf_counter()

    platforms = _load_platforms()

    # Filter platforms if requested
    if platforms_filter:
        filter_lower = {p.lower() for p in platforms_filter}
        targets = {k: v for k, v in platforms.items() if k.lower() in filter_lower}
    else:
        targets = platforms

    semaphore = asyncio.Semaphore(max_concurrent)

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, verify=False) as client:
        tasks = [
            _check_platform(client, semaphore, name, data, username)
            for name, data in targets.items()
        ]
        results = await asyncio.gather(*tasks)

    found = []
    not_found = []
    errors = []

    for hit in results:
        if hit.status == "found":
            found.append(hit)
        elif hit.status == "error":
            errors.append(hit.platform)
        else:
            not_found.append(hit.platform)

    elapsed = (time.perf_counter() - t0) * 1000
    logger.info(
        f"[USERNAME-ENUM] ══════ DONE ══════  username={username} "
        f"found={len(found)}/{len(targets)} errors={len(errors)} ({elapsed:.0f}ms)"
    )

    return UsernameEnumResponse(
        username=username,
        total_found=len(found),
        total_checked=len(targets),
        platforms_found=found,
        platforms_not_found=not_found,
        errors=errors,
    )
