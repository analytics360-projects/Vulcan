"""Carpeta integration events — hooks for the pre-carpeta 911 pipeline."""
from datetime import datetime, timezone
from typing import Optional

from config import logger
from services.llm_queue_service import enqueue_llm_task


async def on_carpeta_initialized(carpeta_id: str, folio_data: dict):
    """Called when a carpeta is created from a 911 folio."""
    logger.info(f"Event: carpeta_initialized {carpeta_id}")

    # 1. STT if audio available
    if folio_data.get("audio_url"):
        enqueue_llm_task("stt", {
            "audio_url": folio_data["audio_url"],
            "carpeta_id": carpeta_id,
            "folio_id": folio_data.get("folio_id"),
            "origen": "911_call",
        }, carpeta_id=carpeta_id, priority=10)

    # 2. NER on narrative text
    if folio_data.get("narrativa"):
        enqueue_llm_task("ner", {
            "texto": folio_data["narrativa"],
            "carpeta_id": carpeta_id,
            "folio_id": folio_data.get("folio_id"),
        }, carpeta_id=carpeta_id, priority=9)

    # 3. Multi-case correlation (immediate, not queued)
    try:
        from modules.correlation.service import correlation_service
        await correlation_service.find_similar_from_folio(carpeta_id, folio_data)
    except Exception as e:
        logger.warning(f"Correlation on carpeta init failed: {e}")


async def on_delta_persona_created(persona_data: dict, carpeta_id: str):
    """Called when a person is added to a carpeta."""
    logger.info(f"Event: delta_persona_created in {carpeta_id}")

    # 1. Deduplication check
    try:
        from modules.deduplication.service import db_deduplication_service
        result = db_deduplication_service.check_person_from_dict(persona_data)

        if result.get("status") == "clear":
            # Enqueue dossier generation
            persona_id = persona_data.get("persona_id")
            if persona_id:
                enqueue_llm_task("dossier", {
                    "persona_id": persona_id,
                }, persona_id=persona_id, carpeta_id=carpeta_id, priority=7)
        elif result.get("status") == "definitive_match":
            # Auto-merge
            candidates = result.get("candidates", [])
            if candidates:
                logger.info(f"Auto-merging persona into {candidates[0].get('persona_id')}")
        else:
            # Needs manual review — log for investigator
            logger.info(f"Dedup review needed for persona in carpeta {carpeta_id}")
    except Exception as e:
        logger.warning(f"Dedup on persona created failed: {e}")


async def on_mia_batch_complete(carpeta_id: str, persona_ids: list[str]):
    """Called when MIA batch processing completes for a carpeta."""
    logger.info(f"Event: mia_batch_complete {carpeta_id}, {len(persona_ids)} personas")

    for persona_id in persona_ids:
        enqueue_llm_task("profiler", {
            "persona_id": persona_id,
            "carpeta_id": carpeta_id,
        }, persona_id=persona_id, carpeta_id=carpeta_id, priority=5)


async def on_social_graph_updated(carpeta_id: str, graph_data: dict):
    """Called when the social graph is updated."""
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    if len(nodes) >= 3:
        enqueue_llm_task("communities", {
            "nodes": nodes,
            "edges": edges,
            "carpeta_id": carpeta_id,
        }, carpeta_id=carpeta_id, priority=4)


async def on_declaracion_added(persona_id: str, carpeta_id: str, declaracion: dict):
    """Called when a declaration is added for a person."""
    logger.info(f"Event: declaracion_added persona={persona_id} carpeta={carpeta_id}")

    enqueue_llm_task("consistency", {
        "persona_id": persona_id,
        "carpeta_id": carpeta_id,
    }, persona_id=persona_id, carpeta_id=carpeta_id, priority=6)


async def on_carpeta_progress_update(carpeta_id: str, completitud_pct: float):
    """Called when carpeta completeness changes. Triggers hypothesis at 60%+."""
    if completitud_pct >= 60:
        enqueue_llm_task("hypothesis", {
            "carpeta_id": carpeta_id,
        }, carpeta_id=carpeta_id, priority=3)
