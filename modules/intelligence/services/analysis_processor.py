"""
Main analysis processor that orchestrates face detection and entity extraction
"""
import os
import uuid
from typing import Dict, Any, Optional, List
from modules.intelligence.models.analysis import AnalysisResult, AnalysisStatus
import structlog
from datetime import datetime

logger = structlog.get_logger()


class AnalysisProcessor:
    """Main processor for photo analysis"""
    
    def __init__(
        self,
        face_service=None,
        entity_service=None,
        graph_writer=None,
        qdrant_service=None
    ):
        """
        Initialize processor with service instances.
        If services are None, they will be created (for backward compatibility).
        
        Args:
            face_service: FaceDetectionService instance (from app startup)
            entity_service: EntityExtractionService instance (from app startup)
            graph_writer: GraphWriterService instance (from app startup)
        """
        # Use provided services or create new ones (fallback)
        if face_service is None:
            from modules.intelligence.services.face_detection import FaceDetectionService
            logger.warning("Creating new FaceDetectionService instance (should use shared instance)")
            self.face_service = FaceDetectionService()
        else:
            self.face_service = face_service
        
        if entity_service is None:
            from modules.intelligence.services.entity_extraction import EntityExtractionService
            logger.warning("Creating new EntityExtractionService instance (should use shared instance)")
            self.entity_service = EntityExtractionService()
        else:
            self.entity_service = entity_service
        
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
    
    def process_photo(
        self,
        photo_path: str,
        photo_id: str,
        metadata: Dict[str, Any],
        description: Optional[str] = None,
        entity_type: Optional[str] = None,  # "person" or "evidence"/"object"
        photo_url: Optional[str] = None  # MinIO URL
    ) -> AnalysisResult:
        """
        Process a photo: detect faces, extract entities, store in graph

        Args:
            photo_path: Path to photo file (local or temp)
            photo_id: Unique photo identifier
            metadata: Additional metadata
            description: Optional description
            photo_url: Optional MinIO URL for the photo

        Returns:
            AnalysisResult with all findings
        """
        analysis_id = str(uuid.uuid4())

        try:
            logger.info("Starting photo analysis", analysis_id=analysis_id, photo_id=photo_id, photo_url=photo_url)

            # Create analysis node in graph
            self.graph_writer.create_analysis_node(analysis_id, photo_id, metadata, photo_url=photo_url)
            
            # Link to Folio if provided
            folio_id = metadata.get("folio_id")
            if folio_id:
                self.graph_writer.create_or_get_folio(folio_id)
                self.graph_writer.link_analysis_to_folio(analysis_id, folio_id)
            
            # Extract entities early (from description + metadata) so we can use Person name when creating Person for faces
            entities = []
            try:
                if description:
                    entities.extend(self.entity_service.extract_entities_from_text(description, context="photo description"))
                if metadata:
                    entities.extend(self.entity_service.extract_entities_from_metadata(metadata))
            except Exception as e:
                logger.warning("Early entity extraction failed (will retry later)", error=str(e))
            
            def _person_display_name() -> str:
                """Use first extracted Person entity name, or fallback to photo_id placeholder."""
                for e in entities:
                    if e.get("entity_type") == "Person" and e.get("value"):
                        return e["value"].strip()
                return f"Person from {photo_id}"
            
            # 1. Face detection
            faces = []
            person_ids_created = []
            
            try:
                from config import settings
                faces = self.face_service.detect_faces(
                    photo_path,
                    min_confidence=settings.face_min_confidence,
                    min_face_size=settings.face_min_size
                )
                if faces:
                    # Make face IDs globally unique by including photo_id
                    for face in faces:
                        # Replace "face_0" with "photo_id_face_0" to ensure uniqueness
                        original_face_id = face["face_id"]
                        face["face_id"] = f"{photo_id}_{original_face_id}"
                        logger.debug("Renamed face ID", original=original_face_id, new=face["face_id"])

                    self.graph_writer.add_face_detections(analysis_id, faces)

                    # Store embeddings in Qdrant and search for matches
                    for face in faces:
                        embedding = face.get("embedding")
                        if embedding and self.qdrant_service:
                            # Store embedding in Qdrant
                            qdrant_point_id = self.qdrant_service.store_face_embedding(
                                embedding=embedding,
                                face_id=face["face_id"],
                                photo_id=photo_id,
                                analysis_id=analysis_id
                            )
                            
                            # Search for similar faces
                            matches = []
                            if self.qdrant_service:
                                matches = self.qdrant_service.search_similar_faces(
                                    query_embedding=embedding,
                                    threshold=0.7,
                                    limit=5
                                )
                            
                            # If match found, link to existing Person
                            if matches and matches[0]["score"] >= 0.7:
                                best_match = matches[0]
                                existing_person_id = best_match.get("person_id")
                                
                                if existing_person_id:
                                    # Link to existing person
                                    self.graph_writer.link_face_to_person(
                                        face_id=face["face_id"],
                                        person_id=existing_person_id,
                                        similarity_score=best_match["score"]
                                    )
                                    # Update Qdrant with person_id
                                    if self.qdrant_service:
                                        self.qdrant_service.update_person_id(qdrant_point_id, existing_person_id)
                                    person_ids_created.append(existing_person_id)
                                    logger.info(
                                        "Face matched to existing Person",
                                        face_id=face["face_id"],
                                        person_id=existing_person_id,
                                        score=best_match["score"]
                                    )
                                else:
                                    # Create new Person for matched face (no person_id in Qdrant yet)
                                    person_name = _person_display_name()
                                    new_person_id = self.graph_writer.create_or_get_person(
                                        person_name,
                                        attributes={"source": "analysis"}
                                    )
                                    self.graph_writer.link_face_to_person(
                                        face_id=face["face_id"],
                                        person_id=new_person_id,
                                        similarity_score=best_match["score"]
                                    )
                                    if self.qdrant_service:
                                        self.qdrant_service.update_person_id(qdrant_point_id, new_person_id)
                                    person_ids_created.append(new_person_id)
                                    logger.info(
                                        "Face matched to new Person",
                                        face_id=face["face_id"],
                                        person_id=new_person_id,
                                        score=best_match["score"]
                                    )
                            else:
                                # No match found, create new Person
                                person_name = _person_display_name()
                                new_person_id = self.graph_writer.create_or_get_person(
                                    person_name,
                                    attributes={"source": "analysis"}
                                )
                                self.graph_writer.link_face_to_person(
                                    face_id=face["face_id"],
                                    person_id=new_person_id,
                                    similarity_score=0.0  # No match
                                )
                                if self.qdrant_service:
                                    self.qdrant_service.update_person_id(qdrant_point_id, new_person_id)
                                person_ids_created.append(new_person_id)
                                logger.info(
                                    "New Person created for face",
                                    face_id=face["face_id"],
                                    person_id=new_person_id
                                )

                    # Link all persons to Folio if provided (after processing all faces)
                    if folio_id and person_ids_created:
                        for pid in person_ids_created:
                            self.graph_writer.link_person_to_folio(pid, folio_id)

                    logger.info("Face detection completed", faces_found=len(faces))
            except Exception as e:
                logger.error("Face detection failed", error=str(e))
            
            # 2. Add entities to graph and link Person entities to Person nodes (entities already extracted above)
            try:
                if entities:
                    self.graph_writer.add_entities(analysis_id, entities)
                    logger.info("Processing entities", count=len(entities), folio_id=folio_id)

                    # Link Person entities to Person nodes
                    for entity in entities:
                        logger.debug("Processing entity", entity_type=entity["entity_type"], value=entity["value"])
                        if entity["entity_type"] == "Person":
                            # Create or get Person node
                            person_id = self.graph_writer.create_or_get_person(
                                entity["value"],
                                attributes={"source": "analysis"}
                            )
                            
                            # Link entity to Person
                            self.graph_writer.link_entity_to_person(
                                entity_type=entity["entity_type"],
                                entity_value=entity["value"],
                                person_id=person_id
                            )
                            
                            # Link Person to Folio if provided
                            if folio_id:
                                self.graph_writer.link_person_to_folio(person_id, folio_id)
                            
                            logger.info(
                                "Person entity linked to Person node",
                                entity_value=entity["value"],
                                person_id=person_id
                            )
                        elif entity["entity_type"] == "Crime":
                            # Link crime to Folio if available
                            if folio_id:
                                self.graph_writer.add_folio_delito(
                                    folio_id=folio_id,
                                    delito=entity["value"]
                                )
                                logger.info(
                                    "Crime linked to Folio",
                                    crime=entity["value"],
                                    folio_id=folio_id
                                )
                            else:
                                logger.warning(
                                    "Crime entity found but no folio_id to link to",
                                    crime=entity["value"]
                                )
                        elif entity["entity_type"] in ["Alias", "Vehicle", "Phone", "Address", "Weapon"]:
                            # For other entities, try to link to Person if we have faces
                            if faces and person_ids_created:
                                # Link to the first person found in this photo
                                person_id = person_ids_created[0]
                                self.graph_writer.link_entity_to_person(
                                    entity_type=entity["entity_type"],
                                    entity_value=entity["value"],
                                    person_id=person_id
                                )

                logger.info("Entity extraction completed", entities_found=len(entities))
            except Exception as e:
                logger.error("Entity extraction failed", error=str(e))
            
            # Update status to completed
            self.graph_writer.update_analysis_status(analysis_id, "completed")
            
            # Build result
            result = AnalysisResult(
                analysis_id=analysis_id,
                photo_id=photo_id,
                status=AnalysisStatus.COMPLETED,
                created_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                faces_detected=faces,
                face_count=len(faces),
                entities=entities,
                graph_associations=[]  # Will be populated later with graph queries
            )
            
            logger.info("Analysis completed successfully", analysis_id=analysis_id)
            return result
            
        except Exception as e:
            logger.error("Analysis failed", analysis_id=analysis_id, error=str(e))
            self.graph_writer.update_analysis_status(analysis_id, "failed", error=str(e))
            
            return AnalysisResult(
                analysis_id=analysis_id,
                photo_id=photo_id,
                status=AnalysisStatus.FAILED,
                created_at=datetime.utcnow(),
                error=str(e)
            )
