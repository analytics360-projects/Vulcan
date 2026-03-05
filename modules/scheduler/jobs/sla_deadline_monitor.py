"""SLA Deadline Monitor — checks carpetas approaching/past deadline and posts system alerts.
Every 15 min: GET SLA Dashboard from Balder, POST SeguimientoSLA for urgent/expired carpetas.
"""
import httpx
from datetime import datetime, timezone
from config import settings, logger


async def run():
    balder = settings.balder_api_url
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{balder}/PreCarpetas/SLA/Dashboard")
            if resp.status_code != 200:
                logger.warning(f"sla_deadline_monitor: Balder returned {resp.status_code}")
                return
            dashboard = resp.json()

        carpetas = dashboard.get("carpetas", [])
        if not carpetas:
            return

        async with httpx.AsyncClient(timeout=30) as client:
            for carpeta in carpetas:
                semaforo = carpeta.get("semaforoColor", "")
                dias = carpeta.get("diasRestantes", 999)
                carpeta_id = carpeta.get("id")

                if not carpeta_id:
                    continue

                nota = None
                if semaforo == "vencida" and dias >= -1:
                    nota = f"[SISTEMA] Carpeta ha vencido (hace {abs(dias)} día(s))"
                elif semaforo == "urgente" and dias <= 3:
                    nota = f"[SISTEMA] Carpeta vence en {dias} día(s)"

                if not nota:
                    continue

                # Deduplication: check if system note already exists for today
                sla_resp = await client.get(f"{balder}/PreCarpetas/SLA/{carpeta_id}")
                if sla_resp.status_code == 200:
                    existing = sla_resp.json()
                    already_posted = any(
                        s.get("nota", "").startswith("[SISTEMA]")
                        and s.get("fechaCreacion", "")[:10] == today_str
                        for s in existing
                    )
                    if already_posted:
                        continue

                payload = {
                    "carpetaId": carpeta_id,
                    "nota": nota,
                    "creadoPor": "sistema",
                    "creadoPorNombre": "Monitor SLA",
                }
                post_resp = await client.post(f"{balder}/PreCarpetas/SLA/Create", json=payload)
                if post_resp.status_code == 200:
                    logger.info(f"sla_deadline_monitor: Alert posted for carpeta {carpeta_id} — {nota}")
                else:
                    logger.warning(f"sla_deadline_monitor: Failed to post SLA for carpeta {carpeta_id}: {post_resp.status_code}")

    except Exception as e:
        logger.error(f"sla_deadline_monitor job failed: {e}")
