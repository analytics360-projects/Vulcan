"""Plate Batch Processor — processes queued vehicle plate searches by calling Balder's ProcessNext endpoint.
Every 30 seconds: POST PreCarpetas/BusquedasVehiculares/ProcessNext. Skips if nothing pending.
"""
import httpx
from config import settings, logger


async def run():
    balder = settings.balder_api_url

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{balder}/PreCarpetas/BusquedasVehiculares/ProcessNext")
            if resp.status_code != 200:
                logger.warning(f"plate_batch_processor: Balder returned {resp.status_code}")
                return

            data = resp.json()
            if not data.get("processed", False):
                return

            if data.get("error"):
                logger.warning(f"plate_batch_processor: Error procesando — {data['error']}")
            else:
                logger.info(
                    f"plate_batch_processor: Búsqueda placa {data.get('placas')} "
                    f"— {data.get('totalCoincidencias', 0)} coincidencia(s) — ID: {data.get('busquedaId')}"
                )

    except Exception as e:
        logger.error(f"plate_batch_processor job failed: {e}")
