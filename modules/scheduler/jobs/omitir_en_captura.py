"""Omitir En Captura job — ported from Skadi
Every 59 min: Auto-complete stalled events stuck in 'Captura' >5 min.
"""
import psycopg2
from config import settings, logger


async def run():
    if not settings.postgres_connection_string:
        logger.debug("omitir_en_captura: no postgres connection, skipping")
        return
    try:
        conn = psycopg2.connect(settings.postgres_connection_string)
        with conn.cursor() as cur:
            # Find stalled captures
            cur.execute("""
                SELECT folio, created_by, corporacion_id, MAX(created_at) as latest_created_at
                FROM eventos_historial
                WHERE estatus = 'Captura'
                GROUP BY folio, created_by, corporacion_id
                HAVING (EXTRACT(EPOCH FROM NOW() AT TIME ZONE 'America/Chihuahua' - MAX(created_at)) / 60) > 5
                LIMIT 20
            """)
            stalled = cur.fetchall()

            for folio, created_by, corp_id, latest_at in stalled:
                # Verify still in Captura (race condition guard)
                cur.execute("""
                    SELECT estatus FROM eventos_historial
                    WHERE folio = %s
                    ORDER BY created_at DESC LIMIT 1
                """, (folio,))
                row = cur.fetchone()
                if not row or row[0] != "Captura":
                    continue

                # Insert Omitido record
                cur.execute("""
                    INSERT INTO eventos_historial (folio, estatus, origen, incidencia, created_by, corporacion_id, created_at)
                    VALUES (%s, 'Omitido', 'Automatico', 'No clasificada', %s, %s, NOW() AT TIME ZONE 'America/Chihuahua')
                """, (folio, created_by, corp_id))

                # Update main event
                cur.execute("""
                    UPDATE eventos SET estatus = 'Omitido', fecha_omitido = NOW() AT TIME ZONE 'America/Chihuahua'
                    WHERE folio = %s
                """, (folio,))

                logger.info(f"omitir_en_captura: omitted folio {folio}")

            conn.commit()
        conn.close()
        if stalled:
            logger.info(f"omitir_en_captura: processed {len(stalled)} stalled events")
    except Exception as e:
        logger.error(f"omitir_en_captura failed: {e}")
