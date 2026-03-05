"""Core business logic services"""

# Global service instances (initialized on app startup)
face_service = None
entity_service = None
graph_writer = None
qdrant_service = None
storage_service = None

# Object detection service instances
object_detection_service = None
object_embedding_service = None