"""
Object analysis processor that orchestrates object detection and embedding generation
"""
import os
import uuid
from typing import Dict, Any, Optional, List
from modules.intelligence.models.analysis import AnalysisResult, AnalysisStatus
import structlog
from datetime import datetime

logger = structlog.get_logger()


class ObjectProcessor:
    """Processor for object detection and analysis"""

    def __init__(
        self,
        object_detection_service=None,
        object_embedding_service=None,
        graph_writer=None,
        qdrant_service=None
    ):
        """
        Initialize processor with service instances

        Args:
            object_detection_service: ObjectDetectionService instance
            object_embedding_service: ObjectEmbeddingService instance
            graph_writer: GraphWriterService instance
            qdrant_service: QdrantService instance
        """
        if object_detection_service is None:
            from modules.intelligence.services.object_detection import ObjectDetectionService
            logger.warning("Creating new ObjectDetectionService instance (should use shared instance)")
            self.object_detection_service = ObjectDetectionService()
        else:
            self.object_detection_service = object_detection_service

        if object_embedding_service is None:
            from modules.intelligence.services.object_embedding import ObjectEmbeddingService
            logger.warning("Creating new ObjectEmbeddingService instance (should use shared instance)")
            self.object_embedding_service = ObjectEmbeddingService()
        else:
            self.object_embedding_service = object_embedding_service

        if graph_writer is None:
            from modules.intelligence.services.graph_writer import GraphWriterService
            logger.warning("Creating new GraphWriterService instance (should use shared instance)")
            self.graph_writer = GraphWriterService()
        else:
            self.graph_writer = graph_writer

        if qdrant_service is None:
            from modules.intelligence.services.qdrant_service import QdrantService
            logger.warning("Creating new QdrantService instance (should use shared instance)")
            self.qdrant_service = QdrantService()
        else:
            self.qdrant_service = qdrant_service

    def process_object_photo(
        self,
        photo_path: str,
        photo_id: str,
        metadata: Dict[str, Any],
        description: Optional[str] = None,
        photo_url: Optional[str] = None,
        tags: Optional[List[str]] = None,
        confidence_threshold: float = 0.5
    ) -> AnalysisResult:
        """
        Process a photo for object detection

        Args:
            photo_path: Path to photo file (local or temp)
            photo_id: Unique photo identifier
            metadata: Additional metadata
            description: Optional description
            photo_url: Optional MinIO URL for the photo
            tags: Optional Spanish tags
            confidence_threshold: Minimum confidence for object detection

        Returns:
            AnalysisResult with detected objects
        """
        analysis_id = str(uuid.uuid4())
        objects_created = []

        try:
            logger.info("Starting object analysis", analysis_id=analysis_id, photo_id=photo_id, photo_url=photo_url)

            # Create analysis node in graph
            self.graph_writer.create_analysis_node(analysis_id, photo_id, metadata, photo_url=photo_url)

            # Link to Folio if provided
            folio_id = metadata.get("folio_id")
            if folio_id:
                self.graph_writer.create_or_get_folio(folio_id)
                self.graph_writer.link_analysis_to_folio(analysis_id, folio_id)

            # 1. Object detection with YOLOv8
            detected_objects = []
            try:
                if not self.object_detection_service.initialized:
                    logger.error("Object detection service not initialized")
                    raise Exception("Object detection service not available")

                detected_objects = self.object_detection_service.detect_objects(
                    image_path=photo_path,
                    confidence_threshold=confidence_threshold,
                    include_bbox=True
                )

                if not detected_objects:
                    logger.info("No objects detected in photo", analysis_id=analysis_id)

                logger.info("Object detection completed", objects_found=len(detected_objects))

            except Exception as e:
                logger.error("Object detection failed", error=str(e))
                raise

            # 2a. Fallback: if YOLO detected nothing, still index the full image
            #     so it remains searchable via CLIP semantic similarity using the
            #     user-provided tags and description.
            if not detected_objects and self.object_embedding_service and self.object_embedding_service.initialized:
                logger.info(
                    "YOLO detected no objects — indexing full image as fallback",
                    analysis_id=analysis_id,
                    tags=tags,
                    description=description,
                )
                try:
                    embedding = self.object_embedding_service.generate_image_embedding(
                        image_path=photo_path,
                        bbox=None,
                    )

                    if embedding is not None and self.qdrant_service:
                        fallback_id = f"{photo_id}_full"
                        fallback_tags = list(tags or [])
                        fallback_type_es = description or "objeto no identificado"
                        fallback_type = "undetected"

                        qdrant_point_id = self.qdrant_service.store_object_embedding(
                            embedding=embedding,
                            object_id=fallback_id,
                            object_type=fallback_type,
                            object_type_es=fallback_type_es,
                            category="otros",
                            photo_id=photo_id,
                            photo_url=photo_url,
                            analysis_id=analysis_id,
                            folio_id=folio_id,
                            tags=fallback_tags,
                            metadata=metadata,
                        )

                        self.graph_writer.create_object_node(
                            object_id=fallback_id,
                            object_type=fallback_type,
                            object_type_es=fallback_type_es,
                            category="otros",
                            confidence=0.0,
                            photo_url=photo_url,
                            bbox=None,
                            tags=fallback_tags,
                            description=description,
                            metadata=metadata,
                        )
                        self.graph_writer.link_object_to_analysis(fallback_id, analysis_id)
                        if folio_id:
                            self.graph_writer.link_object_to_folio(fallback_id, folio_id)

                        logger.info(
                            "Fallback full-image embedding stored",
                            object_id=fallback_id,
                            point_id=qdrant_point_id,
                            embedding_dim=len(embedding),
                            tags=fallback_tags,
                        )

                        objects_created.append({
                            "object_id": fallback_id,
                            "object_type_es": fallback_type_es,
                            "category": "otros",
                            "confidence": 0.0,
                            "bbox": None,
                            "tags": fallback_tags,
                            "fallback": True,
                        })

                except Exception as e:
                    logger.error("Fallback full-image indexing failed", error=str(e), analysis_id=analysis_id)

            # 2b. Process each detected object
            for idx, obj in enumerate(detected_objects):
                try:
                    object_id = f"{photo_id}_obj_{idx}"
                    object_type = obj["object_type"]
                    object_type_es = obj["object_type_es"]
                    category = obj["category"]
                    confidence = obj["confidence"]
                    bbox = obj.get("bbox")

                    logger.info(
                        "Processing detected object",
                        object_id=object_id,
                        object_type_es=object_type_es,
                        category=category,
                        confidence=confidence
                    )

                    # Generate embedding using the object's bounding box crop.
                    # CLIP resizes input to 224x224 internally, so even small crops work.
                    # If the crop is very small (< 80px on either side), fall back to full
                    # image to avoid feeding extremely distorted patches to the model.
                    embedding = None
                    if self.object_embedding_service.initialized:
                        try:
                            crop_bbox = bbox
                            if bbox:
                                x1, y1, x2, y2 = bbox
                                if (x2 - x1) < 80 or (y2 - y1) < 80:
                                    logger.info(
                                        "Crop too small, using full image",
                                        object_id=object_id,
                                        crop_w=int(x2 - x1),
                                        crop_h=int(y2 - y1),
                                    )
                                    crop_bbox = None
                            embedding = self.object_embedding_service.generate_image_embedding(
                                image_path=photo_path,
                                bbox=crop_bbox
                            )
                        except Exception as e:
                            logger.warning("Failed to generate object embedding", error=str(e), object_id=object_id)

                    # Merge user tags with category-based tags
                    object_tags = list(tags or [])
                    if category not in object_tags:
                        object_tags.append(category)
                    if object_type_es not in object_tags:
                        object_tags.append(object_type_es)

                    # Create Object node in Neo4j
                    self.graph_writer.create_object_node(
                        object_id=object_id,
                        object_type=object_type,
                        object_type_es=object_type_es,
                        category=category,
                        confidence=confidence,
                        photo_url=photo_url,
                        bbox=bbox,
                        tags=object_tags,
                        description=description,
                        metadata=metadata
                    )

                    # Link object to Analysis
                    self.graph_writer.link_object_to_analysis(object_id, analysis_id)

                    # Link object to Folio if provided
                    if folio_id:
                        self.graph_writer.link_object_to_folio(object_id, folio_id)

                    # Store embedding in Qdrant
                    if embedding is not None and self.qdrant_service:
                        try:
                            qdrant_point_id = self.qdrant_service.store_object_embedding(
                                embedding=embedding,
                                object_id=object_id,
                                object_type=object_type,
                                object_type_es=object_type_es,
                                category=category,
                                photo_id=photo_id,
                                photo_url=photo_url,
                                analysis_id=analysis_id,
                                folio_id=folio_id,
                                tags=object_tags,
                                metadata=metadata
                            )
                            logger.info(
                                "Object embedding stored",
                                object_id=object_id,
                                object_type=object_type_es,
                                category=category,
                                yolo_confidence=f"{confidence:.2f}",
                                point_id=qdrant_point_id,
                                embedding_dim=len(embedding)
                            )
                        except Exception as e:
                            logger.error(
                                "Failed to store embedding",
                                error=str(e),
                                object_id=object_id,
                                object_type=object_type_es
                            )

                    objects_created.append({
                        "object_id": object_id,
                        "object_type_es": object_type_es,
                        "category": category,
                        "confidence": confidence,
                        "bbox": bbox,
                        "tags": object_tags
                    })

                except Exception as e:
                    logger.error("Failed to process object", error=str(e), object_index=idx)
                    # Continue processing other objects

            # Update analysis status to completed
            self.graph_writer.update_analysis_status(analysis_id, "completed")

            # Build result
            result = AnalysisResult(
                analysis_id=analysis_id,
                photo_id=photo_id,
                status=AnalysisStatus.COMPLETED,
                created_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                faces_detected=[],  # No faces in object analysis
                face_count=0,
                entities=[],  # Could extract entities from description if needed
                graph_associations=objects_created
            )

            logger.info(
                "Object analysis completed successfully",
                analysis_id=analysis_id,
                objects_detected=len(objects_created)
            )
            return result

        except Exception as e:
            logger.error("Object analysis failed", analysis_id=analysis_id, error=str(e))
            self.graph_writer.update_analysis_status(analysis_id, "failed", error=str(e))

            return AnalysisResult(
                analysis_id=analysis_id,
                photo_id=photo_id,
                status=AnalysisStatus.FAILED,
                created_at=datetime.utcnow(),
                error=str(e)
            )
