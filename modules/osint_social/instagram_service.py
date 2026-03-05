"""Instagram OSINT service — Meta Graph API + fallback scraping"""
from datetime import datetime
from config import settings, logger
from shared.rate_limiter import rate_limited
from modules.osint_social.models import OsintResult, PlatformHealth
import httpx


def get_health() -> PlatformHealth:
    if not settings.instagram_access_token:
        return PlatformHealth(available=False, reason="INSTAGRAM_ACCESS_TOKEN not configured")
    return PlatformHealth(available=True)


@rate_limited("instagram")
async def search(username: str = None, hashtag: str = None, max_results: int = 10) -> list[OsintResult]:
    if not settings.instagram_access_token:
        return []
    results = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            token = settings.instagram_access_token

            if username:
                resp = await client.get(
                    f"https://graph.instagram.com/v18.0/{username}",
                    params={"fields": "id,username,media_count,account_type", "access_token": token},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results.append(OsintResult(
                        plataforma="instagram",
                        tipo="perfil",
                        datos=data,
                        timestamp=datetime.now().isoformat(),
                        fuente_url=f"https://instagram.com/{username}",
                    ))

            if hashtag:
                resp = await client.get(
                    "https://graph.instagram.com/ig_hashtag_search",
                    params={"q": hashtag, "access_token": token},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results.append(OsintResult(
                        plataforma="instagram",
                        tipo="hashtag",
                        datos=data,
                        timestamp=datetime.now().isoformat(),
                    ))
    except Exception as e:
        logger.error(f"Instagram search error: {e}")
    return results
