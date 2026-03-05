"""
Query service for parsing natural language queries and executing them
"""
from typing import Dict, Any, List, Optional
from modules.intelligence.services.graph_writer import GraphWriterService
from modules.intelligence.services.qdrant_service import QdrantService
from modules.intelligence.services.face_detection import FaceDetectionService
from modules.intelligence.services.entity_extraction import EntityExtractionService
from modules.intelligence.services.storage_service import StorageService
import structlog
import re

logger = structlog.get_logger()


class QueryService:
    """Service for parsing and executing natural language queries"""

    def __init__(
        self,
        graph_writer: GraphWriterService,
        qdrant_service: Optional[QdrantService] = None,
        face_service: Optional[FaceDetectionService] = None,
        entity_service: Optional[EntityExtractionService] = None,
        storage_service: Optional[StorageService] = None
    ):
        self.graph_writer = graph_writer
        self.qdrant_service = qdrant_service
        self.face_service = face_service
        self.entity_service = entity_service
        self.storage_service = storage_service

    def _standard_response(self, intent: str, results: List[Dict], query_params: Optional[Dict] = None, error: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a standardized response structure for all queries

        Args:
            intent: Query intent type
            results: List of result items
            query_params: Query parameters used (e.g., person_name, crime, etc.)
            error: Error message if query failed

        Returns:
            Standardized response with consistent structure
        """
        response = {
            "intent": intent,
            "results": results,
            "count": len(results)
        }

        if query_params:
            response["query"] = query_params

        if error:
            response["error"] = error
            response["count"] = 0

        return response
    
    def parse_query(self, query: str) -> Dict[str, Any]:
        """
        Parse a natural language query in Spanish
        
        Args:
            query: Natural language query in Spanish
            
        Returns:
            Parsed query with intent and parameters
        """
        query_lower = query.lower().strip()
        
        # Pattern 1: "¿en qué folios ha aparecido [persona]?" or "folios de [persona]"
        person_folios_pattern = r'(?:en\s+qu[eé]\s+folios?\s+ha\s+aparecido|folios?\s+de|folios?\s+donde\s+aparece|folios?\s+donde\s+ha\s+aparecido)\s+(.+?)(?:\?|$)'
        match = re.search(person_folios_pattern, query_lower)
        if match:
            person_name = match.group(1).strip()
            return {
                "intent": "person_folios",
                "person_name": person_name,
                "original_query": query
            }
        
        # Pattern 2: "¿qué folios tiene [persona]?" or "folios de [persona]"
        person_folios_pattern2 = r'(?:qu[eé]\s+folios?\s+tiene|folios?\s+de)\s+(.+?)(?:\?|$)'
        match = re.search(person_folios_pattern2, query_lower)
        if match:
            person_name = match.group(1).strip()
            return {
                "intent": "person_folios",
                "person_name": person_name,
                "original_query": query
            }
        
        # Pattern 3: "¿qué personas aparecen en el folio [número]?" or "personas del folio [número]"
        folio_persons_pattern = r'(?:qu[eé]\s+personas?\s+aparecen?\s+en\s+el\s+folio|personas?\s+del\s+folio|personas?\s+en\s+el\s+folio)\s+(\d+)(?:\?|$)'
        match = re.search(folio_persons_pattern, query_lower)
        if match:
            folio_id = match.group(1).strip()
            return {
                "intent": "folio_persons",
                "folio_id": folio_id,
                "original_query": query
            }
        
        # Pattern 4: "buscar persona [nombre]" or "encontrar [nombre]"
        search_person_pattern = r'(?:buscar\s+persona|encontrar|buscar)\s+(.+?)(?:\?|$)'
        match = re.search(search_person_pattern, query_lower)
        if match:
            person_name = match.group(1).strip()
            return {
                "intent": "search_person",
                "person_name": person_name,
                "original_query": query
            }
        
        # Pattern 5: "información de [persona]" or "detalles de [persona]"
        person_details_pattern = r'(?:informaci[oó]n\s+de|detalles\s+de|datos\s+de)\s+(.+?)(?:\?|$)'
        match = re.search(person_details_pattern, query_lower)
        if match:
            person_name = match.group(1).strip()
            return {
                "intent": "person_details",
                "person_name": person_name,
                "original_query": query
            }
        
        # Pattern 6: "¿cuáles son los padres de [persona]?" or "padres de [persona]"
        parents_pattern = r'(?:cu[aá]les?\s+son\s+los\s+padres?\s+de|padres?\s+de|qui[eé]n\s+es\s+el\s+padre\s+de|qui[eé]n\s+es\s+la\s+madre\s+de)\s+(.+?)(?:\?|$)'
        match = re.search(parents_pattern, query_lower)
        if match:
            person_name = match.group(1).strip()
            return {
                "intent": "person_parents",
                "person_name": person_name,
                "original_query": query
            }
        
        # Pattern 7: "¿qué delitos ha cometido [persona]?" or "delitos de [persona]"
        crimes_pattern = r'(?:qu[eé]\s+delitos?\s+ha\s+cometido|delitos?\s+de|cr[ií]menes?\s+de|qu[eé]\s+cr[ií]menes?\s+ha\s+cometido)\s+(.+?)(?:\?|$)'
        match = re.search(crimes_pattern, query_lower)
        if match:
            person_name = match.group(1).strip()
            return {
                "intent": "person_crimes",
                "person_name": person_name,
                "original_query": query
            }
        
        # Pattern 8: "¿qué delitos tiene [persona]?" or "delitos que tiene [persona]"
        crimes_pattern2 = r'(?:qu[eé]\s+delitos?\s+tiene|delitos?\s+que\s+tiene|cr[ií]menes?\s+que\s+tiene)\s+(.+?)(?:\?|$)'
        match = re.search(crimes_pattern2, query_lower)
        if match:
            person_name = match.group(1).strip()
            return {
                "intent": "person_crimes",
                "person_name": person_name,
                "original_query": query
            }

        # Pattern 9: "muéstrame personas con incidentes en [dirección]"
        address_pattern = r'(?:mu[eé]strame\s+personas?\s+con\s+incidentes?\s+en|personas?\s+en\s+(?:la\s+)?direcci[oó]n|qui[eé]nes?\s+viven?\s+en|incidentes?\s+en|personas?\s+asociadas?\s+(?:a|con)\s+(?:la\s+)?direcci[oó]n)\s+(.+?)(?:\?|$)'
        match = re.search(address_pattern, query_lower)
        if match:
            address = match.group(1).strip()
            return {
                "intent": "address_persons",
                "address": address,
                "original_query": query
            }

        # Pattern 10: "personas asociadas con el número [teléfono]"
        phone_pattern = r'(?:personas?\s+asociadas?\s+con\s+(?:el\s+)?n[uú]mero|qui[eé]n\s+tiene\s+(?:el\s+)?tel[eé]fono|buscar\s+por\s+n[uú]mero|tel[eé]fono|personas?\s+con\s+(?:el\s+)?tel[eé]fono)\s+(.+?)(?:\?|$)'
        match = re.search(phone_pattern, query_lower)
        if match:
            phone = match.group(1).strip()
            return {
                "intent": "phone_persons",
                "phone": phone,
                "original_query": query
            }

        # Pattern 11: "¿de quién es el vehículo [placa]?"
        vehicle_pattern = r'(?:de\s+qui[eé]n\s+es\s+el\s+veh[ií]culo|buscar\s+due[ñn]o\s+de\s+(?:la\s+)?placa|veh[ií]culo\s+con\s+placa|qui[eé]n\s+tiene\s+(?:el\s+)?veh[ií]culo|placa)\s+(.+?)(?:\?|$)'
        match = re.search(vehicle_pattern, query_lower)
        if match:
            plate = match.group(1).strip()
            return {
                "intent": "vehicle_owner",
                "plate": plate,
                "original_query": query
            }

        # Pattern 12: "¿quién cometió [delito]?" or "personas con [delito]"
        crime_perpetrators_pattern = r'(?:qui[eé]n\s+cometi[oó]|qui[eé]nes?\s+cometieron|personas?\s+con|personas?\s+que\s+cometieron|buscar\s+personas?\s+por)\s+(?:un\s+)?(.+?)(?:\?|$)'
        match = re.search(crime_perpetrators_pattern, query_lower)
        if match:
            crime = match.group(1).strip()
            # Filter out common non-crime words to avoid false matches
            if crime and crime not in ['el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas']:
                return {
                    "intent": "crime_perpetrators",
                    "crime": crime,
                    "original_query": query
                }

        # If no pattern matches, try to extract person name using entity extraction
        if self.entity_service:
            try:
                entities = self.entity_service.extract_entities_from_text(query, context="query")
                person_entities = [e for e in entities if e.get("entity_type") == "Person"]
                if person_entities:
                    person_name = person_entities[0]["value"]
                    # Default to person_folios intent
                    return {
                        "intent": "person_folios",
                        "person_name": person_name,
                        "original_query": query
                    }
            except Exception as e:
                logger.warning("Failed to extract entities from query", error=str(e))
        
        # Default: unknown intent
        return {
            "intent": "unknown",
            "original_query": query
        }
    
    def execute_query(self, parsed_query: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a parsed query
        
        Args:
            parsed_query: Parsed query from parse_query()
            
        Returns:
            Query results
        """
        intent = parsed_query.get("intent")
        
        if intent == "person_folios":
            person_name = parsed_query.get("person_name")
            if not person_name:
                return self._standard_response("person_folios", [], error="Nombre de persona no especificado")

            folios = self.graph_writer.get_folios_by_person_name(person_name)

            # Convert MinIO URLs to presigned URLs
            if self.storage_service:
                for folio in folios:
                    presigned_urls = []
                    for minio_url in folio.get("photo_urls", []):
                        if minio_url and minio_url.startswith("minio://"):
                            try:
                                # Extract object name from minio://bucket/path format
                                object_name = minio_url.replace(f"minio://{self.storage_service.bucket_name}/", "")
                                presigned_url = self.storage_service.get_presigned_url(object_name, expires_seconds=3600)
                                presigned_urls.append(presigned_url)
                            except Exception as e:
                                logger.warning("Failed to generate presigned URL", minio_url=minio_url, error=str(e))
                    folio["photo_urls"] = presigned_urls

            return self._standard_response("person_folios", folios, query_params={"person_name": person_name})

        elif intent == "folio_persons":
            folio_id = parsed_query.get("folio_id")
            if not folio_id:
                return self._standard_response("folio_persons", [], error="ID de folio no especificado")

            persons = self.graph_writer.get_persons_in_folio(folio_id)
            return self._standard_response("folio_persons", persons, query_params={"folio_id": folio_id})

        elif intent == "search_person":
            person_name = parsed_query.get("person_name")
            if not person_name:
                return self._standard_response("search_person", [], error="Nombre de persona no especificado")

            persons = self.graph_writer.search_person_by_name(person_name)
            return self._standard_response("search_person", persons, query_params={"person_name": person_name})
        
        elif intent == "person_details":
            person_name = parsed_query.get("person_name")
            if not person_name:
                return self._standard_response("person_details", [], error="Nombre de persona no especificado")

            # First search for the person
            persons = self.graph_writer.search_person_by_name(person_name)
            if not persons:
                return self._standard_response("person_details", [], query_params={"person_name": person_name}, error="Persona no encontrada")

            # Get details for the first match
            person_id = persons[0]["person_id"]
            details = self.graph_writer.get_person_details(person_id)

            if not details:
                return self._standard_response("person_details", [], query_params={"person_name": person_name}, error="No se pudieron obtener los detalles")

            return self._standard_response("person_details", [details], query_params={"person_name": person_name})
        
        elif intent == "person_parents":
            person_name = parsed_query.get("person_name")
            if not person_name:
                return self._standard_response("person_parents", [], error="Nombre de persona no especificado")

            # Search for the person
            persons = self.graph_writer.search_person_by_name(person_name)
            if not persons:
                return self._standard_response("person_parents", [], query_params={"person_name": person_name}, error="Persona no encontrada")

            # Get parents for all matching persons
            all_parents = []
            for person in persons:
                parents = self.graph_writer.get_person_parents(person["person_id"])
                for parent in parents:
                    parent["child_person_id"] = person["person_id"]
                    parent["child_person_name"] = person["person_name"]
                all_parents.extend(parents)

            return self._standard_response("person_parents", all_parents, query_params={"person_name": person_name})

        elif intent == "person_crimes":
            person_name = parsed_query.get("person_name")
            if not person_name:
                return self._standard_response("person_crimes", [], error="Nombre de persona no especificado")

            # Search for the person
            persons = self.graph_writer.search_person_by_name(person_name)
            if not persons:
                return self._standard_response("person_crimes", [], query_params={"person_name": person_name}, error="Persona no encontrada")

            # Get crimes/delitos for all matching persons
            all_crimes = []
            for person in persons:
                crimes = self.graph_writer.get_person_crimes(person["person_id"])
                for crime in crimes:
                    crime["person_id"] = person["person_id"]
                    crime["person_name"] = person["person_name"]
                all_crimes.extend(crimes)

            return self._standard_response("person_crimes", all_crimes, query_params={"person_name": person_name})

        elif intent == "address_persons":
            address = parsed_query.get("address")
            if not address:
                return self._standard_response("address_persons", [], error="Dirección no especificada")

            persons = self.graph_writer.get_persons_by_address(address)
            return self._standard_response("address_persons", persons, query_params={"address": address})

        elif intent == "phone_persons":
            phone = parsed_query.get("phone")
            if not phone:
                return self._standard_response("phone_persons", [], error="Número telefónico no especificado")

            persons = self.graph_writer.get_persons_by_phone(phone)
            return self._standard_response("phone_persons", persons, query_params={"phone": phone})

        elif intent == "vehicle_owner":
            plate = parsed_query.get("plate")
            if not plate:
                return self._standard_response("vehicle_owner", [], error="Placa no especificada")

            owners = self.graph_writer.get_vehicle_owners(plate)
            return self._standard_response("vehicle_owner", owners, query_params={"plate": plate})

        elif intent == "crime_perpetrators":
            crime = parsed_query.get("crime")
            if not crime:
                return self._standard_response("crime_perpetrators", [], error="Delito no especificado")

            persons = self.graph_writer.get_persons_by_crime(crime)
            return self._standard_response("crime_perpetrators", persons, query_params={"crime": crime})

        else:
            return self._standard_response(
                "unknown",
                [],
                error="No se pudo entender la consulta. Intenta con: '¿En qué folios ha aparecido [nombre]?', '¿Cuáles son los padres de [nombre]?', '¿Qué delitos ha cometido [nombre]?', '¿Quién cometió [delito]?', 'Personas en la dirección [dirección]', o 'Quién tiene el teléfono [número]?'"
            )
    
    def search_image_matches(self, image_path: str, threshold: float = 0.7, limit: int = 10) -> Dict[str, Any]:
        """
        Search for matches of a face in an uploaded image
        
        Args:
            image_path: Path to the image file
            threshold: Similarity threshold (default: 0.7)
            limit: Maximum number of results (default: 10)
            
        Returns:
            Search results with matches and folios
        """
        if not self.face_service or not self.face_service.initialized:
            return {"error": "Servicio de detección de rostros no disponible"}
        
        if not self.qdrant_service:
            return {"error": "Servicio de búsqueda vectorial no disponible"}
        
        try:
            # Detect faces in the image
            faces = self.face_service.detect_faces(image_path)
            
            if not faces:
                return {
                    "error": "No se detectaron rostros en la imagen",
                    "faces_detected": 0
                }
            
            all_matches = []
            
            # Search for each face
            for face in faces:
                embedding = face.get("embedding")
                if not embedding:
                    continue
                
                # Search in Qdrant
                matches = self.qdrant_service.search_similar_faces(
                    query_embedding=embedding,
                    threshold=threshold,
                    limit=limit
                )
                
                # Enrich matches with folio information and full person details
                enriched_matches = []
                for match in matches:
                    person_id = match.get("person_id")
                    photo_id = match.get("photo_id")
                    analysis_id = match.get("analysis_id")

                    # Get folios for this person if available
                    folios = []
                    if person_id:
                        folios = self.graph_writer.get_folios_by_person(person_id)

                    # Get full person details (name, curp, alias, etc.) for display
                    person_details = None
                    if person_id:
                        person_details = self.graph_writer.get_person_details(person_id)

                    # Get photo URL from MinIO
                    photo_url = None
                    presigned_url = None
                    if analysis_id:
                        photo_url = self.graph_writer.get_photo_url_by_analysis(analysis_id)
                        # Generate presigned URL for temporary access (1 hour)
                        if photo_url and self.storage_service and photo_url.startswith("minio://"):
                            try:
                                # Extract object name from minio://bucket/object format
                                object_name = photo_url.split("/", 3)[-1]  # Get part after bucket
                                presigned_url = self.storage_service.get_presigned_url(object_name, expires_seconds=3600)
                            except Exception as e:
                                logger.warning("Failed to generate presigned URL", photo_url=photo_url, error=str(e))

                    person_name = person_details.get("person_name") if person_details else None
                    # Build match payload with full person details when available
                    match_payload = {
                        "face_id": match.get("face_id"),
                        "person_id": person_id,
                        "person_name": person_name,
                        "photo_id": photo_id,
                        "photo_url": photo_url,
                        "photo_url_presigned": presigned_url,  # Temporary URL for direct access
                        "analysis_id": analysis_id,
                        "similarity_score": match.get("score"),
                        "folios": folios,
                        "folio_count": len(folios)
                    }
                    if person_details:
                        match_payload["person_details"] = {
                            "person_id": person_details.get("person_id"),
                            "person_name": person_details.get("person_name"),
                            "curp": person_details.get("curp"),
                            "birth_date": person_details.get("birth_date"),
                            "alias": person_details.get("alias"),
                            "sex": person_details.get("sex"),
                            "nationality": person_details.get("nationality"),
                            "source": person_details.get("source"),
                            "created_at": person_details.get("created_at"),
                            "folio_ids": person_details.get("folio_ids") or [],
                            "folio_numbers": person_details.get("folio_numbers") or [],
                            "face_count": person_details.get("face_count"),
                        }
                    enriched_matches.append(match_payload)
                
                all_matches.append({
                    "face_index": face.get("face_id"),
                    "matches": enriched_matches,
                    "match_count": len(enriched_matches)
                })
            
            return {
                "faces_detected": len(faces),
                "matches": all_matches,
                "total_matches": sum(len(m["matches"]) for m in all_matches)
            }
            
        except Exception as e:
            logger.error("Image search failed", error=str(e))
            return {"error": f"Error al buscar coincidencias: {str(e)}"}
