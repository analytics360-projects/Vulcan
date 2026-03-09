"""Dossier Batch Processor — processes queued dossier OSINT analyses by calling Balder's ProcessNext endpoint.
Every 30 seconds: POST DossierProcessing/ProcessNext. Skips if nothing pending.
"""
import httpx
from config import settings, logger


async def run():
    balder = settings.balder_api_url

    try:
        async with httpx.AsyncClient(timeout=300) as client:  # 5min para OSINT
            resp = await client.post(f"{balder}/DossierProcessing/ProcessNext")
            if resp.status_code != 200:
                logger.warning(f"dossier_batch_processor: Balder returned {resp.status_code}")
                return

            data = resp.json()
            if not data.get("processed", False):
                return

            if data.get("error"):
                logger.warning(f"dossier_batch_processor: Error procesando — {data['error']}")
            else:
                logger.info(
                    f"dossier_batch_processor: persona #{data.get('personaId')} → {data.get('status')}"
                )

    except Exception as e:
        logger.error(f"dossier_batch_processor job failed: {e}")
