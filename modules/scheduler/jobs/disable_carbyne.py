"""Disable Carbyne workstations job — ported from Skadi
Every 30 min: Reset workstation reservations inactive >720 min.
"""
import psycopg2
from config import settings, logger


async def run():
    if not settings.postgres_connection_string:
        logger.debug("disable_carbyne: no postgres connection, skipping")
        return
    try:
        conn = psycopg2.connect(settings.postgres_connection_string)
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE cat_estaciones_carbyne
                SET en_uso = false, usuario_en_uso = '', usuario_id = ''
                WHERE (EXTRACT(EPOCH FROM NOW() - updated_at) / 60) > 720
            """)
            count = cur.rowcount
            conn.commit()
        conn.close()
        if count > 0:
            logger.info(f"disable_carbyne: reset {count} workstations")
    except Exception as e:
        logger.error(f"disable_carbyne failed: {e}")
