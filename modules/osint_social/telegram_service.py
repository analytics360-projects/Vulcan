"""Telegram OSINT service — Telethon (public channels)"""
from datetime import datetime
from config import settings, logger
from shared.rate_limiter import rate_limited
from modules.osint_social.models import OsintResult, PlatformHealth


def get_health() -> PlatformHealth:
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        return PlatformHealth(available=False, reason="TELEGRAM_API_ID/HASH not configured")
    return PlatformHealth(available=True)


@rate_limited("telegram")
async def search(channel: str = None, query: str = None, max_results: int = 20) -> list[OsintResult]:
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        return []
    results = []
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        client = TelegramClient(StringSession(), int(settings.telegram_api_id), settings.telegram_api_hash)
        await client.start()

        if channel:
            entity = await client.get_entity(channel)
            messages = await client.get_messages(entity, limit=max_results, search=query or "")
            for msg in messages:
                if msg.text:
                    results.append(OsintResult(
                        plataforma="telegram",
                        tipo="mensaje",
                        datos={"text": msg.text[:500], "date": str(msg.date), "views": msg.views, "sender_id": msg.sender_id},
                        timestamp=msg.date.isoformat() if msg.date else datetime.now().isoformat(),
                        fuente_url=f"https://t.me/{channel}/{msg.id}" if channel else None,
                    ))

        await client.disconnect()
    except Exception as e:
        logger.error(f"Telegram search error: {e}")
    return results
