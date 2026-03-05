"""MIA Batch Processor — processes queued MIA analyses by calling Balder's ProcessNext endpoint.
Every 30 seconds: POST MiaProcessing/ProcessNext. Skips if nothing pending.
"""
import httpx
from config import settings, logger


async def run():
    balder = settings.balder_api_url

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{balder}/MiaProcessing/ProcessNext")
            if resp.status_code != 200:
                logger.warning(f"mia_batch_processor: Balder returned {resp.status_code}")
                return

            data = resp.json()
            if not data.get("processed", False):
                return

            if data.get("error"):
                logger.warning(f"mia_batch_processor: Error procesando — {data['error']}")
            else:
                logger.info(
                    f"mia_batch_processor: Procesado análisis {data.get('tipo')} "
                    f"para evidencia #{data.get('evidenciaId')} — ID: {data.get('analysisId')}"
                )

    except Exception as e:
        logger.error(f"mia_batch_processor job failed: {e}")
