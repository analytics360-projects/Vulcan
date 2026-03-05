"""Ping Bitacora job — ported from Skadi
Every 10 min: Ping camera endpoints.
"""
import asyncio
import httpx
from config import settings, logger


async def run():
    balder = settings.balder_api_url
    endpoints = [f"{balder}/Camaras/ping", f"{balder}/Camaras/pingCiudadanas"]
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            tasks = [client.get(ep) for ep in endpoints]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for ep, r in zip(endpoints, results):
                if isinstance(r, Exception):
                    logger.warning(f"Ping failed {ep}: {r}")
                elif r.status_code == 200:
                    logger.debug(f"Ping OK: {ep}")
                else:
                    logger.warning(f"Ping {ep} returned {r.status_code}")
    except Exception as e:
        logger.error(f"ping_bitacora failed: {e}")
