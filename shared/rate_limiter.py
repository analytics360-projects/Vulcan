"""Token-bucket rate limiter per platform with decorator."""
import asyncio
import time
from functools import wraps
from config import logger

_buckets: dict[str, dict] = {}

PLATFORM_LIMITS = {
    "twitter": {"rate": 1.0, "burst": 15},
    "instagram": {"rate": 2.0, "burst": 10},
    "tiktok": {"rate": 3.0, "burst": 5},
    "telegram": {"rate": 1.0, "burst": 20},
    "forums": {"rate": 1.0, "burst": 10},
    "numverify": {"rate": 1.0, "burst": 5},
    "hunter": {"rate": 1.0, "burst": 5},
    "hibp": {"rate": 6.0, "burst": 1},
    "default": {"rate": 1.0, "burst": 10},
}


def _get_bucket(platform: str) -> dict:
    if platform not in _buckets:
        cfg = PLATFORM_LIMITS.get(platform, PLATFORM_LIMITS["default"])
        _buckets[platform] = {
            "tokens": cfg["burst"],
            "max_tokens": cfg["burst"],
            "refill_interval": cfg["rate"],
            "last_refill": time.monotonic(),
            "lock": asyncio.Lock(),
        }
    return _buckets[platform]


async def _acquire(platform: str):
    bucket = _get_bucket(platform)
    async with bucket["lock"]:
        now = time.monotonic()
        elapsed = now - bucket["last_refill"]
        refill = int(elapsed / bucket["refill_interval"])
        if refill > 0:
            bucket["tokens"] = min(bucket["max_tokens"], bucket["tokens"] + refill)
            bucket["last_refill"] = now
        if bucket["tokens"] <= 0:
            wait = bucket["refill_interval"] - (now - bucket["last_refill"])
            logger.debug(f"Rate limit {platform}: waiting {wait:.1f}s")
            await asyncio.sleep(max(wait, 0.1))
            bucket["tokens"] = 1
        bucket["tokens"] -= 1


def rate_limited(platform: str):
    """Decorator: @rate_limited("twitter")"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            await _acquire(platform)
            return await func(*args, **kwargs)
        return wrapper
    return decorator
