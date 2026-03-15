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

# Risk scoring
risk_scoring_service = None

# Graph metrics (IC5 — Neo4j GDS)
graph_metrics_service = None

# Modus operandi (IC9 — sentence-transformers + Qdrant)
modus_operandi_service = None