"""Intelligence module — ported from Hugin"""
from config import settings, logger
from modules.intelligence import services


def init_services() -> dict:
    """Initialize intelligence services with graceful degradation. Returns status dict."""
    status = {}

    # Face detection
    try:
        from modules.intelligence.services.face_detection import FaceDetectionService
        svc = FaceDetectionService()
        services.face_service = svc
        status["face_detection"] = {"ok": getattr(svc, "initialized", True)}
    except Exception as e:
        logger.warning(f"Face detection unavailable: {e}")
        status["face_detection"] = {"ok": False, "detail": str(e)}

    # Entity extraction
    try:
        from modules.intelligence.services.entity_extraction import EntityExtractionService
        services.entity_service = EntityExtractionService()
        status["entity_extraction"] = {"ok": True}
    except Exception as e:
        logger.warning(f"Entity extraction unavailable: {e}")
        status["entity_extraction"] = {"ok": False, "detail": str(e)}

    # Graph writer (Neo4j)
    try:
        from modules.intelligence.services.graph_writer import GraphWriterService
        services.graph_writer = GraphWriterService()
        status["graph_writer"] = {"ok": True}
    except Exception as e:
        logger.warning(f"Graph writer unavailable: {e}")
        status["graph_writer"] = {"ok": False, "detail": str(e)}

    # Qdrant
    try:
        from modules.intelligence.services.qdrant_service import QdrantService
        services.qdrant_service = QdrantService()
        status["qdrant"] = {"ok": True}
    except Exception as e:
        logger.warning(f"Qdrant unavailable: {e}")
        status["qdrant"] = {"ok": False, "detail": str(e)}

    # MinIO storage
    try:
        from modules.intelligence.services.storage_service import StorageService
        services.storage_service = StorageService()
        status["storage"] = {"ok": True}
    except Exception as e:
        logger.warning(f"MinIO unavailable: {e}")
        status["storage"] = {"ok": False, "detail": str(e)}

    # Object detection (YOLOv8)
    try:
        from modules.intelligence.services.object_detection import ObjectDetectionService
        svc = ObjectDetectionService(model_name=f"yolov8{settings.yolo_model_size}.pt", confidence_threshold=0.25)
        services.object_detection_service = svc
        status["object_detection"] = {"ok": getattr(svc, "initialized", True)}
    except Exception as e:
        logger.warning(f"Object detection unavailable: {e}")
        status["object_detection"] = {"ok": False, "detail": str(e)}

    # Object embeddings (CLIP)
    try:
        from modules.intelligence.services.object_embedding import ObjectEmbeddingService
        svc = ObjectEmbeddingService()
        services.object_embedding_service = svc
        status["object_embedding"] = {"ok": getattr(svc, "initialized", True)}
    except Exception as e:
        logger.warning(f"Object embedding unavailable: {e}")
        status["object_embedding"] = {"ok": False, "detail": str(e)}

    return status
