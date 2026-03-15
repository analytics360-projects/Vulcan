"""LLM task queue — PostgreSQL-backed async job processing with SKIP LOCKED."""
import json
import os
from datetime import datetime, timezone
from typing import Any

from config import settings, logger

MAX_RETRIES = 3
LLM_QUEUE_MAX_CONCURRENT = int(os.getenv("LLM_QUEUE_MAX_CONCURRENT", "2"))


def _get_conn():
    """Get PostgreSQL connection from main connection string."""
    import psycopg2
    conn_str = settings.postgres_main_connection_string
    if not conn_str:
        raise RuntimeError("postgres_main_connection_string not configured")
    return psycopg2.connect(conn_str)


def ensure_queue_table():
    """Create llm_task_queue table if not exists."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS llm_task_queue (
                    id SERIAL PRIMARY KEY,
                    task_type VARCHAR(50) NOT NULL,
                    payload JSONB NOT NULL DEFAULT '{}',
                    carpeta_id UUID,
                    persona_id UUID,
                    priority INT DEFAULT 5,
                    status VARCHAR(20) DEFAULT 'pending',
                    retries INT DEFAULT 0,
                    result JSONB,
                    error_message TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    started_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_llm_queue_status_priority
                ON llm_task_queue (status, priority DESC, created_at ASC)
            """)
            conn.commit()
    finally:
        conn.close()


def enqueue_llm_task(
    task_type: str,
    payload: dict,
    carpeta_id: str | None = None,
    persona_id: str | None = None,
    priority: int = 5,
) -> int:
    """Enqueue a task for async LLM processing. Returns task ID."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO llm_task_queue (task_type, payload, carpeta_id, persona_id, priority)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (task_type, json.dumps(payload), carpeta_id, persona_id, priority),
            )
            task_id = cur.fetchone()[0]
            conn.commit()
            logger.info(f"Enqueued LLM task {task_id}: {task_type} (priority={priority})")
            return task_id
    finally:
        conn.close()


async def process_llm_queue():
    """Process up to LLM_QUEUE_MAX_CONCURRENT pending LLM tasks. Called by scheduler."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, task_type, payload, carpeta_id, persona_id, retries
                   FROM llm_task_queue
                   WHERE status = 'pending'
                   ORDER BY priority DESC, created_at ASC
                   LIMIT %s
                   FOR UPDATE SKIP LOCKED""",
                (LLM_QUEUE_MAX_CONCURRENT,),
            )
            tasks = cur.fetchall()

            for task in tasks:
                task_id, task_type, payload, carpeta_id, persona_id, retries = task

                cur.execute(
                    "UPDATE llm_task_queue SET status='processing', started_at=NOW() WHERE id=%s",
                    (task_id,),
                )
                conn.commit()

                try:
                    result = await _dispatch_llm_task(task_type, payload if isinstance(payload, dict) else json.loads(payload))
                    cur.execute(
                        "UPDATE llm_task_queue SET status='done', completed_at=NOW(), result=%s WHERE id=%s",
                        (json.dumps(result), task_id),
                    )
                    conn.commit()
                    logger.info(f"LLM task {task_id} ({task_type}) completed")
                except Exception as e:
                    new_retries = retries + 1
                    new_status = "failed" if new_retries >= MAX_RETRIES else "pending"
                    cur.execute(
                        "UPDATE llm_task_queue SET status=%s, retries=%s, error_message=%s WHERE id=%s",
                        (new_status, new_retries, str(e)[:500], task_id),
                    )
                    conn.commit()
                    logger.error(f"LLM task {task_id} ({task_type}) failed (attempt {new_retries}): {e}")
    finally:
        conn.close()


async def _dispatch_llm_task(task_type: str, payload: dict) -> dict:
    """Route task to the appropriate service handler."""
    if task_type == "ner":
        from modules.ner.service import ner_service
        return await ner_service.extract_async(payload)
    elif task_type == "consistency":
        from modules.consistency.service import consistency_service
        return await consistency_service.analyze_async(payload)
    elif task_type == "profiler":
        from modules.profiler.service import profiler_service
        return await profiler_service.generate_async(payload)
    elif task_type == "hypothesis":
        from modules.hypothesis.service import hypothesis_service
        return await hypothesis_service.generate_async(payload)
    elif task_type == "communities":
        from modules.community.service import community_service
        return community_service.detect_from_payload(payload)
    elif task_type == "stt":
        from modules.speech.service import forensic_speech_service
        return forensic_speech_service.transcribe_from_payload(payload)
    else:
        raise ValueError(f"Unknown task_type: {task_type}")


def get_task_status(task_id: int) -> dict | None:
    """Get status of a queued task."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, task_type, status, retries, result, error_message,
                          created_at, started_at, completed_at
                   FROM llm_task_queue WHERE id = %s""",
                (task_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "task_type": row[1],
                "status": row[2],
                "retries": row[3],
                "result": row[4],
                "error_message": row[5],
                "created_at": row[6].isoformat() if row[6] else None,
                "started_at": row[7].isoformat() if row[7] else None,
                "completed_at": row[8].isoformat() if row[8] else None,
            }
    finally:
        conn.close()
