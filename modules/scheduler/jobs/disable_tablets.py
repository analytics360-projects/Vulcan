"""Disable Tablets job — ported from Skadi
Every 59 min: Disable physical tablets inactive >120 min.
"""
import psycopg2
from config import settings, logger


async def run():
    if not settings.postgres_connection_string:
        logger.debug("disable_tablets: no postgres connection, skipping")
        return
    try:
        conn = psycopg2.connect(settings.postgres_connection_string)
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE tablet_resources
                SET status = 0
                WHERE is_virtual = false
                  AND status != 0
                  AND (EXTRACT(EPOCH FROM NOW() - updated_at) / 60) > 120
            """)
            count = cur.rowcount
            conn.commit()
        conn.close()
        if count > 0:
            logger.info(f"disable_tablets: disabled {count} tablets")
    except Exception as e:
        logger.error(f"disable_tablets failed: {e}")
