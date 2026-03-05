"""Parametros Busqueda job — ported from Skadi (C#)
Every 2 min: GET active investigations from Balder, suspend expired, trigger SANS for due ones.
"""
import httpx
from datetime import datetime
from config import settings, logger


async def run():
    balder = settings.balder_api_url
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{balder}/SansParametrosBusqueda/getOptions")
            if resp.status_code != 200:
                logger.warning(f"parametros_busqueda: Balder returned {resp.status_code}")
                return
            items = resp.json()

        now = datetime.now()
        async with httpx.AsyncClient(timeout=60) as client:
            for item in items:
                try:
                    fecha_fin = item.get("fechaFin")
                    if fecha_fin:
                        exp = datetime.fromisoformat(fecha_fin)
                        if exp < now and item.get("status") == 1:
                            await client.get(f"{balder}/SansParametrosBusqueda/suspend/{item['id']}")
                            logger.info(f"Suspended expired investigation {item['id']}")
                            continue

                    updated_at = item.get("updatedAt")
                    periodicidad = item.get("periodicidadHoras", 0)
                    if updated_at and periodicidad:
                        last = datetime.fromisoformat(updated_at)
                        diff_hours = (now - last).total_seconds() / 3600
                        if diff_hours >= periodicidad and item.get("status") == 1:
                            fecha_inicio = item.get("fechaInicio")
                            if fecha_inicio and datetime.fromisoformat(fecha_inicio) <= now:
                                await client.post(f"{balder}/SansParametrosBusqueda/update", json={"id": item["id"], "updatedAt": now.isoformat()})
                                payload = {
                                    "urls": item.get("urls", []),
                                    "user": item.get("user", "scheduler"),
                                    "nombre": item.get("nombre", ""),
                                    "carpeta_investigacion": str(item.get("carpetaInvestigacion", "")),
                                    "investigacion": str(item.get("id", "")),
                                    "tipo_busqueda": item.get("tipoBusqueda", ""),
                                    "status": 1,
                                    "palabras": item.get("palabrasClave", []),
                                }
                                # Internal call to SANS module
                                from modules.sans.service import scrape_multi_urls
                                scrape_multi_urls(**{k: v for k, v in payload.items()})
                                logger.info(f"Triggered SANS for investigation {item['id']}")
                except Exception as e:
                    logger.error(f"parametros_busqueda item error: {e}")
    except Exception as e:
        logger.error(f"parametros_busqueda job failed: {e}")
