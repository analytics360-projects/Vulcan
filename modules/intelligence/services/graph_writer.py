"""
Neo4j graph writer service for storing analysis results
"""
from neo4j import GraphDatabase
from typing import List, Dict, Any, Optional
from config import settings
import structlog
from datetime import datetime
import uuid
import json

logger = structlog.get_logger()


class GraphWriterService:
    """Service for writing analysis results to Neo4j graph"""
    
    def __init__(self):
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password)
        )
        self.driver.verify_connectivity()
        logger.info("Neo4j connection verified")
    
    def create_analysis_node(self, analysis_id: str, photo_id: str, metadata: Dict[str, Any], photo_url: Optional[str] = None) -> str:
        """
        Create an Analysis node in Neo4j

        Args:
            analysis_id: Unique analysis ID
            photo_id: Photo identifier
            metadata: Additional metadata (will be stored as JSON string)
            photo_url: Optional MinIO URL for the photo

        Returns:
            Node ID
        """
        with self.driver.session() as session:
            # Convert metadata dict to JSON string (Neo4j doesn't support nested objects)
            metadata_json = json.dumps(metadata) if metadata else "{}"

            query = """
            CREATE (a:Analysis {
                id: $analysis_id,
                photo_id: $photo_id,
                photo_url: $photo_url,
                created_at: $created_at,
                status: $status,
                metadata: $metadata_json
            })
            RETURN a.id as id
            """

            result = session.run(
                query,
                analysis_id=analysis_id,
                photo_id=photo_id,
                photo_url=photo_url,
                created_at=datetime.utcnow().isoformat(),
                status="processing",
                metadata_json=metadata_json
            )

            node_id = result.single()["id"]
            logger.info("Analysis node created", analysis_id=analysis_id, node_id=node_id, photo_url=photo_url)
            return node_id
    
    def add_folio_delito(self, folio_id: str, delito: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a delito (crime) to a Folio node

        Args:
            folio_id: Folio node ID
            delito: Crime/delito description
            metadata: Optional metadata (e.g., motivoDetencion, fecha, etc.)
        """
        with self.driver.session() as session:
            # Create Folio if it doesn't exist, then link to Delito node
            query = """
            MERGE (f:Folio {id: $folio_id})
            ON CREATE SET
                f.folio_number = $folio_id,
                f.created_at = $created_at
            MERGE (d:Delito {value: $delito})
            ON CREATE SET d.created_at = $created_at
            MERGE (f)-[:HAS_DELITO {
                created_at: $created_at
            }]->(d)
            RETURN f.id as folio_id, d.value as delito_value
            """

            result = session.run(
                query,
                folio_id=folio_id,
                delito=delito,
                created_at=datetime.utcnow().isoformat()
            )

            record = result.single()
            if record:
                logger.info(
                    "Crime added to Folio",
                    folio_id=record["folio_id"],
                    delito=record["delito_value"]
                )
            else:
                logger.error("Failed to add crime to Folio", folio_id=folio_id, delito=delito)

            # Also store in folio properties for quick access (as array)
            update_query = """
            MATCH (f:Folio {id: $folio_id})
            SET f.delitos = COALESCE(f.delitos, []) + [$delito]
            """
            session.run(update_query, folio_id=folio_id, delito=delito)
            
            logger.info("Delito added to Folio", folio_id=folio_id, delito=delito)
    
    def add_face_detections(self, analysis_id: str, faces: List[Dict[str, Any]]) -> None:
        """
        Add face detection results to graph
        
        Args:
            analysis_id: Analysis ID
            faces: List of face detection results
        """
        with self.driver.session() as session:
            for face in faces:
                query = """
                MATCH (a:Analysis {id: $analysis_id})
                CREATE (f:Face {
                    id: $face_id,
                    bbox: $bbox,
                    confidence: $confidence,
                    age: $age,
                    gender: $gender
                })
                CREATE (a)-[:DETECTED_FACE]->(f)
                """
                
                session.run(
                    query,
                    analysis_id=analysis_id,
                    face_id=face["face_id"],
                    bbox=face["bbox"],
                    confidence=face["confidence"],
                    age=face.get("age"),
                    gender=face.get("gender")
                )
            
            logger.info("Face detections added to graph", analysis_id=analysis_id, count=len(faces))
    
    def add_entities(self, analysis_id: str, entities: List[Dict[str, Any]]) -> None:
        """
        Add extracted entities to graph

        Args:
            analysis_id: Analysis ID
            entities: List of entity extraction results
        """
        with self.driver.session() as session:
            for entity in entities:
                entity_type = entity["entity_type"]
                value = entity["value"]

                # Sanitize entity_type for Neo4j label (remove spaces, special chars)
                # Neo4j labels can't have spaces or special characters
                safe_entity_type = entity_type.replace(" ", "_").replace("-", "_")

                # Create or merge entity node
                query = f"""
                MATCH (a:Analysis {{id: $analysis_id}})
                MERGE (e:{safe_entity_type} {{value: $value}})
                ON CREATE SET
                    e.created_at = $created_at,
                    e.confidence = $confidence,
                    e.entity_type = $original_type
                ON MATCH SET e.confidence = CASE
                    WHEN e.confidence < $confidence THEN $confidence
                    ELSE e.confidence
                END
                CREATE (a)-[:EXTRACTED_ENTITY {{
                    confidence: $confidence,
                    context: $context
                }}]->(e)
                """

                session.run(
                    query,
                    analysis_id=analysis_id,
                    value=value,
                    original_type=entity_type,  # Store original type as property
                    created_at=datetime.utcnow().isoformat(),
                    confidence=entity["confidence"],
                    context=entity.get("context", "")
                )

            logger.info("Entities added to graph", analysis_id=analysis_id, count=len(entities))
    
    def update_analysis_status(self, analysis_id: str, status: str, error: Optional[str] = None) -> None:
        """Update analysis status"""
        with self.driver.session() as session:
            query = """
            MATCH (a:Analysis {id: $analysis_id})
            SET a.status = $status,
                a.completed_at = CASE WHEN $status IN ['completed', 'failed'] THEN $completed_at ELSE a.completed_at END,
                a.error = CASE WHEN $error IS NOT NULL THEN $error ELSE a.error END
            """
            
            session.run(
                query,
                analysis_id=analysis_id,
                status=status,
                completed_at=datetime.utcnow().isoformat() if status in ["completed", "failed"] else None,
                error=error
            )
    
    def create_or_get_person(
        self,
        person_name: str,
        person_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create or get a Person node with extended attributes
        
        Args:
            person_name: Person's name
            person_id: Optional person ID (if None, will be generated)
            attributes: Optional dictionary with additional attributes:
                - curp: CURP (Mexican ID)
                - birth_date: Date of birth
                - alias: Aliases
                - sex: Gender
                - nationality: Nationality
                - address: Address information
                - parent_names: Parent names
                - etc.
            
        Returns:
            Person ID
        """
        attributes = attributes or {}

        with self.driver.session() as session:
            # First, try to find existing person by name (case-insensitive)
            find_query = """
            MATCH (p:Person)
            WHERE toLower(p.name) = toLower($name)
            RETURN p.id as id
            LIMIT 1
            """

            find_result = session.run(find_query, name=person_name)
            existing = find_result.single()

            if existing:
                # Person exists, update and return existing ID
                person_id = existing["id"]
                logger.info("Found existing Person by name", person_id=person_id, name=person_name)
            else:
                # Create new person
                if person_id is None:
                    person_id = str(uuid.uuid4())

            # Now MERGE by ID (will create if new, update if exists)
            query = """
            MERGE (p:Person {id: $person_id})
            ON CREATE SET
                p.name = $name,
                p.created_at = $created_at
            ON MATCH SET
                p.updated_at = $updated_at
            """

            params = {
                "person_id": person_id,
                "name": person_name,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            # Add optional attributes
            if attributes.get("curp"):
                query += ", p.curp = $curp"
                params["curp"] = attributes["curp"]
            
            if attributes.get("birth_date"):
                query += ", p.birth_date = $birth_date"
                params["birth_date"] = attributes["birth_date"]
            
            if attributes.get("alias"):
                query += ", p.alias = $alias"
                params["alias"] = attributes["alias"]
            
            if attributes.get("sex"):
                query += ", p.sex = $sex"
                params["sex"] = attributes["sex"]
            
            if attributes.get("nationality"):
                query += ", p.nationality = $nationality"
                params["nationality"] = attributes["nationality"]
            
            if attributes.get("apellido_uno"):
                query += ", p.apellido_uno = $apellido_uno"
                params["apellido_uno"] = attributes["apellido_uno"]
            
            if attributes.get("apellido_dos"):
                query += ", p.apellido_dos = $apellido_dos"
                params["apellido_dos"] = attributes["apellido_dos"]
            
            # Track source of person (detenido, analysis, manual)
            if attributes.get("source"):
                query += ", p.source = $source"
                params["source"] = attributes["source"]
            
            # Note: biometric_id removed - not reliable in current data
            
            query += " RETURN p.id as id"
            
            result = session.run(query, **params)
            node_id = result.single()["id"]
            logger.info("Person node created/retrieved", person_id=node_id, name=person_name)
            return node_id
    
    def link_face_to_person(
        self,
        face_id: str,
        person_id: str,
        similarity_score: float,
        threshold: float = 0.7
    ) -> None:
        """
        Link a Face node to a Person node
        
        Args:
            face_id: Face node ID
            person_id: Person node ID
            similarity_score: Face matching similarity score
            threshold: Threshold used for matching
        """
        with self.driver.session() as session:
            query = """
            MATCH (f:Face {id: $face_id})
            MATCH (p:Person {id: $person_id})
            MERGE (f)-[r:MATCH_CANDIDATE {
                score: $score,
                threshold: $threshold,
                created_at: $created_at
            }]->(p)
            """
            
            session.run(
                query,
                face_id=face_id,
                person_id=person_id,
                score=similarity_score,
                threshold=threshold,
                created_at=datetime.utcnow().isoformat()
            )
            
            logger.info(
                "Face linked to Person",
                face_id=face_id,
                person_id=person_id,
                score=similarity_score
            )
    
    def create_or_get_folio(self, folio_id: str, folio_number: Optional[str] = None) -> str:
        """
        Create or get a Folio node
        
        Args:
            folio_id: Folio identifier (can be a number like "1" or "100")
            folio_number: Optional folio number (if different from folio_id)
            
        Returns:
            Folio ID
        """
        if folio_number is None:
            folio_number = folio_id
        
        with self.driver.session() as session:
            query = """
            MERGE (f:Folio {id: $folio_id})
            ON CREATE SET 
                f.folio_number = $folio_number,
                f.created_at = $created_at
            ON MATCH SET
                f.updated_at = $updated_at
            RETURN f.id as id
            """
            
            result = session.run(
                query,
                folio_id=folio_id,
                folio_number=folio_number,
                created_at=datetime.utcnow().isoformat(),
                updated_at=datetime.utcnow().isoformat()
            )
            
            node_id = result.single()["id"]
            logger.info("Folio node created/retrieved", folio_id=node_id, folio_number=folio_number)
            return node_id
    
    def link_analysis_to_folio(self, analysis_id: str, folio_id: str) -> None:
        """
        Link an Analysis node to a Folio node
        
        Args:
            analysis_id: Analysis node ID
            folio_id: Folio node ID
        """
        with self.driver.session() as session:
            query = """
            MATCH (a:Analysis {id: $analysis_id})
            MATCH (f:Folio {id: $folio_id})
            MERGE (a)-[:BELONGS_TO]->(f)
            """
            
            session.run(query, analysis_id=analysis_id, folio_id=folio_id)
            logger.info("Analysis linked to Folio", analysis_id=analysis_id, folio_id=folio_id)
    
    def link_person_to_folio(self, person_id: str, folio_id: str, relationship_type: str = "INVOLVES") -> None:
        """
        Link a Person node to a Folio node
        
        Args:
            person_id: Person node ID
            folio_id: Folio node ID
            relationship_type: Relationship type (default: "INVOLVES")
        """
        with self.driver.session() as session:
            query = f"""
            MATCH (p:Person {{id: $person_id}})
            MATCH (f:Folio {{id: $folio_id}})
            MERGE (f)-[:{relationship_type}]->(p)
            """
            
            session.run(query, person_id=person_id, folio_id=folio_id)
            logger.info(
                "Person linked to Folio",
                person_id=person_id,
                folio_id=folio_id,
                relationship=relationship_type
            )
    
    def create_family_relationship(
        self,
        person1_id: str,
        person2_id: str,
        relationship_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Create a family relationship between two persons
        
        Args:
            person1_id: First person ID
            person2_id: Second person ID
            relationship_type: Relationship type (PARENT_OF, CHILD_OF, SIBLING_OF, SPOUSE_OF)
            metadata: Optional metadata
        """
        with self.driver.session() as session:
            query = f"""
            MATCH (p1:Person {{id: $person1_id}})
            MATCH (p2:Person {{id: $person2_id}})
            MERGE (p1)-[r:{relationship_type}]->(p2)
            ON CREATE SET
                r.created_at = $created_at,
                r.metadata = $metadata_json
            ON MATCH SET
                r.updated_at = $updated_at
            """
            
            metadata_json = json.dumps(metadata) if metadata else "{}"
            
            session.run(
                query,
                person1_id=person1_id,
                person2_id=person2_id,
                metadata_json=metadata_json,
                created_at=datetime.utcnow().isoformat(),
                updated_at=datetime.utcnow().isoformat()
            )
            
            logger.info(
                "Family relationship created",
                person1_id=person1_id,
                person2_id=person2_id,
                relationship_type=relationship_type
            )
    
    def find_persons_by_last_names(
        self,
        apellido_uno: Optional[str] = None,
        apellido_dos: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Find persons with matching last names (for sibling detection)
        
        Args:
            apellido_uno: First last name
            apellido_dos: Second last name
            
        Returns:
            List of persons with matching last names
        """
        with self.driver.session() as session:
            conditions = []
            params = {}
            
            # Search by stored last name properties (more accurate)
            if apellido_uno:
                conditions.append("(p.apellido_uno IS NOT NULL AND toLower(p.apellido_uno) = toLower($apellido_uno))")
                params["apellido_uno"] = apellido_uno
            
            if apellido_dos:
                conditions.append("(p.apellido_dos IS NOT NULL AND toLower(p.apellido_dos) = toLower($apellido_dos))")
                params["apellido_dos"] = apellido_dos
            
            # Fallback: also search by name pattern if no stored last names
            if not conditions:
                if apellido_uno:
                    conditions.append("toLower(p.name) CONTAINS toLower($apellido_uno)")
                    params["apellido_uno"] = apellido_uno
                if apellido_dos:
                    conditions.append("toLower(p.name) CONTAINS toLower($apellido_dos)")
                    params["apellido_dos"] = apellido_dos
            
            if not conditions:
                return []
            
            query = f"""
            MATCH (p:Person)
            WHERE {' OR '.join(conditions)}
            RETURN p.id as person_id, p.name as person_name, p.apellido_uno as apellido_uno, p.apellido_dos as apellido_dos
            LIMIT 50
            """
            
            result = session.run(query, **params)
            persons = []
            
            for record in result:
                persons.append({
                    "person_id": record["person_id"],
                    "person_name": record["person_name"],
                    "apellido_uno": record["apellido_uno"],
                    "apellido_dos": record["apellido_dos"]
                })
            
            return persons
    
    def link_entity_to_person(self, entity_type: str, entity_value: str, person_id: str) -> None:
        """
        Link an Entity node to a Person node
        
        Args:
            entity_type: Entity type (Person, Alias, Vehicle, Phone, etc.)
            entity_value: Entity value
            person_id: Person node ID
        """
        with self.driver.session() as session:
            # For Person entities, create an Identity node
            if entity_type == "Person":
                query = """
                MATCH (e:Person {value: $value})
                MATCH (p:Person {id: $person_id})
                MERGE (p)-[:HAS_IDENTITY]->(e)
                """
            # For Alias entities, create an Alias node and link
            elif entity_type == "Alias":
                query = """
                MATCH (e:Alias {value: $value})
                MATCH (p:Person {id: $person_id})
                MERGE (p)-[:HAS_ALIAS]->(e)
                """
            # For other entities, use generic relationship
            else:
                query = f"""
                MATCH (e:{entity_type} {{value: $value}})
                MATCH (p:Person {{id: $person_id}})
                MERGE (p)-[:ASSOCIATED_WITH]->(e)
                """
            
            session.run(query, value=entity_value, person_id=person_id)
            logger.info(
                "Entity linked to Person",
                entity_type=entity_type,
                entity_value=entity_value,
                person_id=person_id
            )
    
    def get_folios_by_person(self, person_id: str) -> List[Dict[str, Any]]:
        """
        Get all folios where a person has appeared
        
        Args:
            person_id: Person node ID
            
        Returns:
            List of folios with metadata
        """
        with self.driver.session() as session:
            query = """
            MATCH (p:Person {id: $person_id})<-[:INVOLVES]-(f:Folio)
            RETURN f.id as folio_id, f.folio_number as folio_number, f.created_at as created_at
            ORDER BY f.folio_number
            """
            
            result = session.run(query, person_id=person_id)
            folios = []
            for record in result:
                folios.append({
                    "folio_id": record["folio_id"],
                    "folio_number": record["folio_number"],
                    "created_at": record["created_at"]
                })
            
            return folios
    
    def get_folios_by_person_name(self, person_name: str) -> List[Dict[str, Any]]:
        """
        Get all folios where a person (by name) has appeared

        Uses case-insensitive partial matching to find persons.

        Args:
            person_name: Person's name (can be partial)

        Returns:
            List of folios with metadata including photo URLs
        """
        with self.driver.session() as session:
            # Use case-insensitive partial match and get photo URLs from Analysis nodes
            query = """
            MATCH (p:Person)<-[:INVOLVES]-(f:Folio)
            WHERE toLower(p.name) CONTAINS toLower($person_name)
            OPTIONAL MATCH (f)<-[:BELONGS_TO]-(a:Analysis)
            WITH f, p, collect(DISTINCT a.photo_url) as photo_urls
            RETURN DISTINCT
                f.id as folio_id,
                f.folio_number as folio_number,
                f.created_at as created_at,
                p.id as person_id,
                p.name as person_name,
                [url IN photo_urls WHERE url IS NOT NULL] as photo_urls
            ORDER BY f.folio_number, p.name
            """

            result = session.run(query, person_name=person_name)
            folios = []
            for record in result:
                folios.append({
                    "folio_id": record["folio_id"],
                    "folio_number": record["folio_number"],
                    "created_at": record["created_at"],
                    "person_id": record["person_id"],
                    "person_name": record["person_name"],
                    "photo_urls": record["photo_urls"]
                })

            return folios
    
    def get_persons_in_folio(self, folio_id: str) -> List[Dict[str, Any]]:
        """
        Get all persons that appear in a folio
        
        Args:
            folio_id: Folio node ID
            
        Returns:
            List of persons with metadata
        """
        with self.driver.session() as session:
            query = """
            MATCH (f:Folio {id: $folio_id})-[:INVOLVES]->(p:Person)
            RETURN DISTINCT p.id as person_id, p.name as person_name, p.created_at as created_at
            ORDER BY p.name
            """
            
            result = session.run(query, folio_id=folio_id)
            persons = []
            for record in result:
                persons.append({
                    "person_id": record["person_id"],
                    "person_name": record["person_name"],
                    "created_at": record["created_at"]
                })
            
            return persons
    
    def search_person_by_name(self, name_query: str) -> List[Dict[str, Any]]:
        """
        Search for persons by name (case-insensitive partial match)
        
        Args:
            name_query: Name to search for
            
        Returns:
            List of matching persons
        """
        with self.driver.session() as session:
            query = """
            MATCH (p:Person)
            WHERE toLower(p.name) CONTAINS toLower($name_query)
            RETURN p.id as person_id, p.name as person_name, p.created_at as created_at
            ORDER BY p.name
            LIMIT 20
            """
            
            result = session.run(query, name_query=name_query)
            persons = []
            for record in result:
                persons.append({
                    "person_id": record["person_id"],
                    "person_name": record["person_name"],
                    "created_at": record["created_at"]
                })
            
            return persons
    
    def get_person_details(self, person_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a person including all folios and faces
        
        Args:
            person_id: Person node ID
            
        Returns:
            Person details with folios, face count, and attributes
        """
        with self.driver.session() as session:
            query = """
            MATCH (p:Person {id: $person_id})
            OPTIONAL MATCH (p)<-[:INVOLVES]-(f:Folio)
            OPTIONAL MATCH (p)<-[:MATCH_CANDIDATE]-(face:Face)
            RETURN p.id as person_id, 
                   p.name as person_name,
                   p.curp as curp,
                   p.birth_date as birth_date,
                   p.alias as alias,
                   p.sex as sex,
                   p.nationality as nationality,
                   p.source as source,
                   p.created_at as created_at,
                   collect(DISTINCT f.id) as folio_ids,
                   collect(DISTINCT f.folio_number) as folio_numbers,
                   count(DISTINCT face) as face_count
            """
            
            result = session.run(query, person_id=person_id)
            record = result.single()
            
            if not record:
                return None
            
            return {
                "person_id": record["person_id"],
                "person_name": record["person_name"],
                "curp": record["curp"],
                "birth_date": record["birth_date"],
                "alias": record["alias"],
                "sex": record["sex"],
                "nationality": record["nationality"],
                "source": record["source"],
                "created_at": record["created_at"],
                "folio_ids": [f for f in record["folio_ids"] if f],
                "folio_numbers": [f for f in record["folio_numbers"] if f],
                "face_count": record["face_count"]
            }

    def get_photo_url_by_analysis(self, analysis_id: str) -> Optional[str]:
        """
        Get the MinIO photo URL for a given analysis_id

        Args:
            analysis_id: Analysis node ID

        Returns:
            Photo URL (MinIO path) or None if not found
        """
        with self.driver.session() as session:
            query = """
            MATCH (a:Analysis {id: $analysis_id})
            RETURN a.photo_url as photo_url
            """
            result = session.run(query, analysis_id=analysis_id)
            record = result.single()

            if record:
                return record["photo_url"]
            return None

    def merge_persons(
        self,
        source_person_id: str,
        target_person_id: str,
        merge_reason: str = "Identity match"
    ) -> None:
        """
        Merge two Person nodes (source into target)
        
        Moves all relationships from source to target, then deletes source.
        
        Args:
            source_person_id: Person ID to merge (will be deleted)
            target_person_id: Person ID to merge into (kept)
            merge_reason: Reason for merge
        """
        with self.driver.session() as session:
            # Move all relationships from source to target
            # Note: Neo4j doesn't support dynamic relationship types in MERGE,
            # so we'll use a more explicit approach
            
            # 1. Move face relationships
            query1 = """
            MATCH (source:Person {id: $source_id})<-[r:MATCH_CANDIDATE]-(f:Face)
            MATCH (target:Person {id: $target_id})
            MERGE (f)-[:MATCH_CANDIDATE {score: r.score, threshold: r.threshold, created_at: r.created_at}]->(target)
            DELETE r
            """
            session.run(query1, source_id=source_person_id, target_id=target_person_id)
            
            # 2. Move folio relationships
            query2 = """
            MATCH (source:Person {id: $source_id})<-[r:INVOLVES]-(f:Folio)
            MATCH (target:Person {id: $target_id})
            MERGE (f)-[:INVOLVES]->(target)
            DELETE r
            """
            session.run(query2, source_id=source_person_id, target_id=target_person_id)
            
            # 3. Move entity relationships (HAS_IDENTITY, HAS_ALIAS, ASSOCIATED_WITH)
            query3 = """
            MATCH (source:Person {id: $source_id})-[r:HAS_IDENTITY|HAS_ALIAS|ASSOCIATED_WITH]->(e)
            MATCH (target:Person {id: $target_id})
            WITH source, target, r, e, type(r) as rel_type
            CALL apoc.create.relationship(target, rel_type, properties(r), e) YIELD rel
            DELETE r
            """
            # If APOC is not available, use individual queries
            try:
                session.run(query3, source_id=source_person_id, target_id=target_person_id)
            except:
                # Fallback: handle each relationship type separately
                for rel_type in ["HAS_IDENTITY", "HAS_ALIAS", "ASSOCIATED_WITH"]:
                    query_fallback = f"""
                    MATCH (source:Person {{id: $source_id}})-[r:{rel_type}]->(e)
                    MATCH (target:Person {{id: $target_id}})
                    MERGE (target)-[:{rel_type}]->(e)
                    DELETE r
                    """
                    session.run(query_fallback, source_id=source_person_id, target_id=target_person_id)
            
            # 4. Move outgoing relationships (CO_OCCURRED, SHARED_ADDRESS, etc.)
            # Get all relationship types first, then move them individually
            query4_get_types = """
            MATCH (source:Person {id: $source_id})-[r]->(other:Person)
            WHERE other.id <> $target_id
            RETURN DISTINCT type(r) as rel_type, other.id as other_id, properties(r) as props
            """
            result = session.run(query4_get_types, source_id=source_person_id, target_id=target_person_id)
            
            for record in result:
                rel_type = record["rel_type"]
                other_id = record["other_id"]
                props = record["props"]
                
                # Create relationship with properties
                query4_move = f"""
                MATCH (target:Person {{id: $target_id}})
                MATCH (other:Person {{id: $other_id}})
                MATCH (source:Person {{id: $source_id}})-[r:{rel_type}]->(other)
                MERGE (target)-[new_r:{rel_type}]->(other)
                SET new_r = $props
                DELETE r
                """
                session.run(query4_move, target_id=target_person_id, other_id=other_id, source_id=source_person_id, props=props)
            
            # 5. Create merge record
            query5 = """
            MATCH (source:Person {id: $source_id})
            MATCH (target:Person {id: $target_id})
            CREATE (source)-[:MERGED_INTO {
                target_id: $target_id,
                reason: $reason,
                merged_at: $merged_at
            }]->(target)
            """
            session.run(
                query5,
                source_id=source_person_id,
                target_id=target_person_id,
                reason=merge_reason,
                merged_at=datetime.utcnow().isoformat()
            )
            
            # 6. Delete source person
            query6 = """
            MATCH (source:Person {id: $source_id})
            DELETE source
            """
            session.run(query6, source_id=source_person_id)
            
            logger.info(
                "Persons merged",
                source_id=source_person_id,
                target_id=target_person_id,
                reason=merge_reason
            )
    
    def propose_person_merge(
        self,
        person1_id: str,
        person2_id: str,
        confidence: float,
        reasons: List[str]
    ) -> str:
        """
        Create a merge proposal (doesn't actually merge, just records the proposal)
        
        Args:
            person1_id: First person ID
            person2_id: Second person ID
            confidence: Confidence score (0.0-1.0)
            reasons: List of reasons for merge
            
        Returns:
            Proposal ID
        """
        proposal_id = str(uuid.uuid4())
        
        with self.driver.session() as session:
            query = """
            MATCH (p1:Person {id: $person1_id})
            MATCH (p2:Person {id: $person2_id})
            CREATE (p1)-[:MERGE_PROPOSAL {
                id: $proposal_id,
                target_id: $person2_id,
                confidence: $confidence,
                reasons: $reasons,
                created_at: $created_at,
                status: 'pending'
            }]->(p2)
            RETURN $proposal_id as proposal_id
            """
            
            session.run(
                query,
                person1_id=person1_id,
                person2_id=person2_id,
                proposal_id=proposal_id,
                confidence=confidence,
                reasons=reasons,
                created_at=datetime.utcnow().isoformat()
            )
            
            logger.info(
                "Merge proposal created",
                proposal_id=proposal_id,
                person1_id=person1_id,
                person2_id=person2_id,
                confidence=confidence
            )
            
            return proposal_id
    
    def create_relationship(
        self,
        person1_id: str,
        person2_id: str,
        relationship_type: str,
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Create a relationship between two persons
        
        Args:
            person1_id: First person ID
            person2_id: Second person ID
            relationship_type: Type of relationship (e.g., "CO_OCCURRED", "SHARED_ADDRESS", "FAMILY", "ASSOCIATED")
            confidence: Confidence score (0.0-1.0)
            metadata: Optional metadata (e.g., {"folio_id": "1", "address": "..."})
        """
        with self.driver.session() as session:
            query = f"""
            MATCH (p1:Person {{id: $person1_id}})
            MATCH (p2:Person {{id: $person2_id}})
            MERGE (p1)-[r:{relationship_type}]->(p2)
            ON CREATE SET
                r.confidence = $confidence,
                r.created_at = $created_at,
                r.metadata = $metadata_json
            ON MATCH SET
                r.confidence = CASE 
                    WHEN r.confidence < $confidence THEN $confidence 
                    ELSE r.confidence 
                END,
                r.updated_at = $updated_at
            """
            
            metadata_json = json.dumps(metadata) if metadata else "{}"
            
            session.run(
                query,
                person1_id=person1_id,
                person2_id=person2_id,
                confidence=confidence,
                metadata_json=metadata_json,
                created_at=datetime.utcnow().isoformat(),
                updated_at=datetime.utcnow().isoformat()
            )
            
            logger.info(
                "Relationship created",
                person1_id=person1_id,
                person2_id=person2_id,
                relationship_type=relationship_type,
                confidence=confidence
            )
    
    def get_person_relationships(self, person_id: str) -> List[Dict[str, Any]]:
        """
        Get all relationships for a person
        
        Args:
            person_id: Person ID
            
        Returns:
            List of relationships with other persons
        """
        with self.driver.session() as session:
            query = """
            MATCH (p:Person {id: $person_id})-[r]->(other:Person)
            RETURN 
                other.id as person_id,
                other.name as person_name,
                type(r) as relationship_type,
                r.confidence as confidence,
                r.metadata as metadata,
                r.created_at as created_at
            ORDER BY r.confidence DESC
            """
            
            result = session.run(query, person_id=person_id)
            relationships = []
            
            for record in result:
                metadata = {}
                if record["metadata"]:
                    try:
                        metadata = json.loads(record["metadata"])
                    except:
                        pass
                
                relationships.append({
                    "person_id": record["person_id"],
                    "person_name": record["person_name"],
                    "relationship_type": record["relationship_type"],
                    "confidence": record["confidence"],
                    "metadata": metadata,
                    "created_at": record["created_at"]
                })
            
            return relationships
    
    def find_persons_by_address(self, address_parts: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Find persons by address (for relationship inference)
        
        Args:
            address_parts: Dictionary with address fields (calle, colonia, municipio, etc.)
            
        Returns:
            List of persons with matching addresses
        """
        with self.driver.session() as session:
            # Build query based on available address parts
            conditions = []
            params = {}
            
            if address_parts.get("calle"):
                conditions.append("p.calle = $calle")
                params["calle"] = address_parts["calle"]
            
            if address_parts.get("colonia"):
                conditions.append("p.colonia = $colonia")
                params["colonia"] = address_parts["colonia"]
            
            if address_parts.get("municipio"):
                conditions.append("p.municipio = $municipio")
                params["municipio"] = address_parts["municipio"]
            
            if not conditions:
                return []
            
            query = f"""
            MATCH (p:Person)
            WHERE {' AND '.join(conditions)}
            RETURN DISTINCT p.id as person_id, p.name as person_name
            LIMIT 100
            """
            
            result = session.run(query, **params)
            persons = []
            
            for record in result:
                persons.append({
                    "person_id": record["person_id"],
                    "person_name": record["person_name"]
                })
            
            return persons
    
    def get_person_parents(self, person_id: str) -> List[Dict[str, Any]]:
        """
        Get parents of a person
        
        Args:
            person_id: Person node ID
            
        Returns:
            List of parents with relationship metadata
        """
        with self.driver.session() as session:
            query = """
            MATCH (child:Person {id: $person_id})<-[:PARENT_OF]-(parent:Person)
            RETURN parent.id as parent_id, 
                   parent.name as parent_name,
                   parent.source as source,
                   parent.created_at as created_at
            ORDER BY parent.name
            """
            
            result = session.run(query, person_id=person_id)
            parents = []
            
            for record in result:
                parents.append({
                    "parent_id": record["parent_id"],
                    "parent_name": record["parent_name"],
                    "source": record["source"],
                    "created_at": record["created_at"]
                })
            
            return parents
    
    def get_person_crimes(self, person_id: str) -> List[Dict[str, Any]]:
        """
        Get crimes/delitos associated with a person through folios
        
        Args:
            person_id: Person node ID
            
        Returns:
            List of crimes with folio information
        """
        with self.driver.session() as session:
            # Get folios where person appears and their delitos
            query = """
            MATCH (p:Person {id: $person_id})<-[:INVOLVES]-(f:Folio)
            OPTIONAL MATCH (f)-[:HAS_DELITO]->(d:Delito)
            OPTIONAL MATCH (f)<-[:BELONGS_TO]-(a:Analysis)
            WITH f, 
                 collect(DISTINCT d.value) as delitos,
                 collect(DISTINCT a.metadata) as analysis_metadata
            RETURN DISTINCT
                f.id as folio_id,
                f.folio_number as folio_number,
                f.delitos as folio_delitos,
                f.created_at as folio_created_at,
                analysis_metadata
            ORDER BY f.folio_number
            """
            
            result = session.run(query, person_id=person_id)
            crimes = []
            
            for record in result:
                folio_id = record["folio_id"]
                folio_number = record["folio_number"]
                
                # Get delitos from Delito nodes
                delitos_from_nodes = record["delitos"] or []
                
                # Also extract motivoDetencion from analysis metadata
                analysis_metadata = record["analysis_metadata"] or []
                delitos_from_metadata = []
                
                for metadata_json in analysis_metadata:
                    if metadata_json:
                        try:
                            metadata = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
                            motivo = metadata.get("motivoDetencion") or metadata.get("motivo_detencion")
                            if motivo:
                                delitos_from_metadata.append(motivo)
                        except:
                            pass
                
                # Combine all delitos
                all_delitos = list(set(delitos_from_nodes + delitos_from_metadata))
                
                if all_delitos:
                    for delito in all_delitos:
                        crimes.append({
                            "folio_id": folio_id,
                            "folio_number": folio_number,
                            "delito": delito,
                            "folio_created_at": record["folio_created_at"]
                        })
                else:
                    # Return folio even if no delito found
                    crimes.append({
                        "folio_id": folio_id,
                        "folio_number": folio_number,
                        "delito": None,
                        "folio_created_at": record["folio_created_at"]
                    })
            
            return crimes
    
    def get_co_occurring_persons(self, person_id: str) -> List[Dict[str, Any]]:
        """
        Find persons who appear in the same folios (co-occurrence)
        
        Args:
            person_id: Person ID
            
        Returns:
            List of co-occurring persons with folio information
        """
        with self.driver.session() as session:
            query = """
            MATCH (p1:Person {id: $person_id})<-[:INVOLVES]-(f:Folio)-[:INVOLVES]->(p2:Person)
            WHERE p1 <> p2
            RETURN DISTINCT
                p2.id as person_id,
                p2.name as person_name,
                collect(DISTINCT f.id) as folio_ids,
                collect(DISTINCT f.folio_number) as folio_numbers,
                count(DISTINCT f) as co_occurrence_count
            ORDER BY co_occurrence_count DESC
            """
            
            result = session.run(query, person_id=person_id)
            co_occurrences = []
            
            for record in result:
                co_occurrences.append({
                    "person_id": record["person_id"],
                    "person_name": record["person_name"],
                    "folio_ids": [f for f in record["folio_ids"] if f],
                    "folio_numbers": [f for f in record["folio_numbers"] if f],
                    "co_occurrence_count": record["co_occurrence_count"]
                })
            
            return co_occurrences

    def get_persons_by_address(self, address: str) -> List[Dict[str, Any]]:
        """
        Find persons associated with an address

        Args:
            address: Address to search for (partial match supported)

        Returns:
            List of persons with their relationship to the address
        """
        with self.driver.session() as session:
            query = """
            MATCH (addr:Address)
            WHERE toLower(addr.value) CONTAINS toLower($address)
            MATCH (p:Person)-[r:LIVES_AT|ASSOCIATED_WITH]-(addr)
            OPTIONAL MATCH (p)-[:INVOLVES]-(f:Folio)
            RETURN DISTINCT p.id as person_id,
                   p.name as person_name,
                   p.source as source,
                   p.curp as curp,
                   p.alias as alias,
                   type(r) as relationship,
                   addr.value as address_value,
                   collect(DISTINCT f.id) as folio_ids,
                   collect(DISTINCT f.folio_number) as folio_numbers,
                   count(DISTINCT f) as folio_count
            ORDER BY folio_count DESC, p.name
            """

            result = session.run(query, address=address)
            persons = []

            for record in result:
                persons.append({
                    "person_id": record["person_id"],
                    "person_name": record["person_name"],
                    "source": record["source"],
                    "curp": record["curp"],
                    "alias": record["alias"],
                    "relationship": record["relationship"],
                    "address": record["address_value"],
                    "folio_ids": [f for f in record["folio_ids"] if f],
                    "folio_numbers": [f for f in record["folio_numbers"] if f],
                    "folio_count": record["folio_count"]
                })

            return persons

    def get_persons_by_phone(self, phone: str) -> List[Dict[str, Any]]:
        """
        Find persons associated with a phone number

        Args:
            phone: Phone number to search for (partial match supported)

        Returns:
            List of persons with their relationship to the phone number
        """
        with self.driver.session() as session:
            # Clean phone number: remove spaces, dashes, parentheses
            clean_phone = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

            query = """
            MATCH (phone:Phone)
            WHERE toLower(replace(replace(replace(phone.value, ' ', ''), '-', ''), '(', '')) CONTAINS toLower($phone)
            MATCH (p:Person)-[r:USES|ASSOCIATED_WITH]-(phone)
            OPTIONAL MATCH (p)-[:INVOLVES]-(f:Folio)
            RETURN DISTINCT p.id as person_id,
                   p.name as person_name,
                   p.source as source,
                   p.curp as curp,
                   p.alias as alias,
                   type(r) as relationship,
                   phone.value as phone_number,
                   collect(DISTINCT f.id) as folio_ids,
                   collect(DISTINCT f.folio_number) as folio_numbers,
                   count(DISTINCT f) as folio_count
            ORDER BY folio_count DESC, p.name
            """

            result = session.run(query, phone=clean_phone)
            persons = []

            for record in result:
                persons.append({
                    "person_id": record["person_id"],
                    "person_name": record["person_name"],
                    "source": record["source"],
                    "curp": record["curp"],
                    "alias": record["alias"],
                    "relationship": record["relationship"],
                    "phone": record["phone_number"],
                    "folio_ids": [f for f in record["folio_ids"] if f],
                    "folio_numbers": [f for f in record["folio_numbers"] if f],
                    "folio_count": record["folio_count"]
                })

            return persons

    def get_vehicle_owners(self, plate: str) -> List[Dict[str, Any]]:
        """
        Find owners of a vehicle by plate number

        Args:
            plate: Vehicle plate to search for (partial match supported)

        Returns:
            List of persons who own or are associated with the vehicle
        """
        with self.driver.session() as session:
            # Clean plate: remove spaces and dashes
            clean_plate = plate.replace(" ", "").replace("-", "")

            query = """
            MATCH (v:Vehicle)
            WHERE toLower(replace(replace(v.value, ' ', ''), '-', '')) CONTAINS toLower($plate)
            MATCH (p:Person)-[r:OWNS|ASSOCIATED_WITH]-(v)
            OPTIONAL MATCH (p)-[:INVOLVES]-(f:Folio)
            RETURN DISTINCT p.id as person_id,
                   p.name as person_name,
                   p.source as source,
                   p.curp as curp,
                   p.alias as alias,
                   type(r) as relationship,
                   v.value as vehicle_plate,
                   v.brand as vehicle_brand,
                   v.model as vehicle_model,
                   v.color as vehicle_color,
                   collect(DISTINCT f.id) as folio_ids,
                   collect(DISTINCT f.folio_number) as folio_numbers,
                   count(DISTINCT f) as folio_count
            ORDER BY folio_count DESC, p.name
            """

            result = session.run(query, plate=clean_plate)
            owners = []

            for record in result:
                vehicle_info = {
                    "plate": record["vehicle_plate"],
                }
                if record["vehicle_brand"]:
                    vehicle_info["brand"] = record["vehicle_brand"]
                if record["vehicle_model"]:
                    vehicle_info["model"] = record["vehicle_model"]
                if record["vehicle_color"]:
                    vehicle_info["color"] = record["vehicle_color"]

                owners.append({
                    "person_id": record["person_id"],
                    "person_name": record["person_name"],
                    "source": record["source"],
                    "curp": record["curp"],
                    "alias": record["alias"],
                    "relationship": record["relationship"],
                    "vehicle": vehicle_info,
                    "folio_ids": [f for f in record["folio_ids"] if f],
                    "folio_numbers": [f for f in record["folio_numbers"] if f],
                    "folio_count": record["folio_count"]
                })

            return owners

    def get_persons_by_crime(self, crime: str) -> List[Dict[str, Any]]:
        """
        Find persons associated with a specific crime/delito

        Args:
            crime: Crime/delito to search for (partial match supported)

        Returns:
            List of persons involved in folios with this crime
        """
        with self.driver.session() as session:
            query = """
            MATCH (d:Delito)
            WHERE toLower(d.value) CONTAINS toLower($crime)
            MATCH (f:Folio)-[:HAS_DELITO]->(d)
            MATCH (f)-[:INVOLVES]->(p:Person)
            RETURN DISTINCT p.id as person_id,
                   p.name as person_name,
                   p.source as source,
                   p.curp as curp,
                   p.alias as alias,
                   d.value as crime_type,
                   collect(DISTINCT f.id) as folio_ids,
                   collect(DISTINCT f.folio_number) as folio_numbers,
                   count(DISTINCT f) as folio_count
            ORDER BY folio_count DESC, p.name
            """

            result = session.run(query, crime=crime)
            persons = []

            for record in result:
                persons.append({
                    "person_id": record["person_id"],
                    "person_name": record["person_name"],
                    "source": record["source"],
                    "curp": record["curp"],
                    "alias": record["alias"],
                    "crime_type": record["crime_type"],
                    "folio_ids": [f for f in record["folio_ids"] if f],
                    "folio_numbers": [f for f in record["folio_numbers"] if f],
                    "folio_count": record["folio_count"]
                })

            return persons

    def list_all_persons(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        List all persons in the database, deduplicating by HAS_IDENTITY relationships

        Args:
            limit: Maximum number of results
            offset: Skip first N results

        Returns:
            List of persons with metadata (deduplicated by identity clusters)
        """
        with self.driver.session() as session:
            query = """
            MATCH (p:Person)
            WHERE p.id IS NOT NULL

            // Get all persons this one is connected to via HAS_IDENTITY
            OPTIONAL MATCH (p)-[:HAS_IDENTITY*0..5]-(connected:Person)
            WHERE connected.id IS NOT NULL

            // Collect connected persons first
            WITH p, collect(DISTINCT connected) as connected_persons

            // Create cluster of all connected persons (including p)
            WITH p,
                 CASE
                   WHEN size(connected_persons) = 0 THEN [p]
                   ELSE [p] + connected_persons
                 END as person_cluster

            // Find the oldest person in cluster as the representative
            WITH p, person_cluster,
                 reduce(oldest = head(person_cluster), person IN person_cluster |
                   CASE WHEN person.created_at < oldest.created_at
                     THEN person
                     ELSE oldest
                   END
                 ) as representative

            // Only process each cluster once (when p is the representative)
            WHERE p.id = representative.id

            // Get folios and faces for ALL persons in the cluster
            UNWIND person_cluster as cluster_member
            OPTIONAL MATCH (cluster_member)<-[:INVOLVES]-(f:Folio)
            OPTIONAL MATCH (cluster_member)<-[:MATCH_CANDIDATE]-(face:Face)

            // Aggregate cluster data
            WITH representative,
                 collect(DISTINCT f.id) as folio_ids,
                 count(DISTINCT face) as face_count

            RETURN representative.id as person_id,
                   representative.name as person_name,
                   representative.curp as curp,
                   representative.alias as alias,
                   representative.source as source,
                   representative.created_at as created_at,
                   size([f IN folio_ids WHERE f IS NOT NULL]) as folio_count,
                   face_count
            ORDER BY representative.created_at DESC
            SKIP $offset
            LIMIT $limit
            """

            result = session.run(query, limit=limit, offset=offset)
            persons = []

            for record in result:
                persons.append({
                    "person_id": record["person_id"],
                    "person_name": record["person_name"],
                    "curp": record["curp"],
                    "alias": record["alias"],
                    "source": record["source"],
                    "created_at": record["created_at"],
                    "folio_count": record["folio_count"],
                    "face_count": record["face_count"]
                })

            return persons

    def list_all_crimes(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        List all crimes/delitos in the database

        Args:
            limit: Maximum number of results
            offset: Skip first N results

        Returns:
            List of crimes with associated folio counts
        """
        with self.driver.session() as session:
            query = """
            MATCH (d:Delito)
            OPTIONAL MATCH (f:Folio)-[:HAS_DELITO]->(d)
            OPTIONAL MATCH (f)-[:INVOLVES]->(p:Person)
            RETURN d.value as crime_type,
                   d.created_at as created_at,
                   collect(DISTINCT f.id) as folio_ids,
                   collect(DISTINCT p.id) as person_ids,
                   count(DISTINCT f) as folio_count,
                   count(DISTINCT p) as person_count
            ORDER BY folio_count DESC, d.value
            SKIP $offset
            LIMIT $limit
            """

            result = session.run(query, limit=limit, offset=offset)
            crimes = []

            for record in result:
                crimes.append({
                    "crime_type": record["crime_type"],
                    "created_at": record["created_at"],
                    "folio_count": record["folio_count"],
                    "person_count": record["person_count"]
                })

            return crimes

    def list_all_folios(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        List all folios in the database

        Args:
            limit: Maximum number of results
            offset: Skip first N results

        Returns:
            List of folios with metadata
        """
        with self.driver.session() as session:
            query = """
            MATCH (f:Folio)
            OPTIONAL MATCH (f)-[:INVOLVES]->(p:Person)
            OPTIONAL MATCH (f)-[:HAS_DELITO]->(d:Delito)
            RETURN f.id as folio_id,
                   f.folio_number as folio_number,
                   f.created_at as created_at,
                   collect(DISTINCT p.name) as person_names,
                   collect(DISTINCT d.value) as crimes,
                   count(DISTINCT p) as person_count
            ORDER BY f.created_at DESC
            SKIP $offset
            LIMIT $limit
            """

            result = session.run(query, limit=limit, offset=offset)
            folios = []

            for record in result:
                folios.append({
                    "folio_id": record["folio_id"],
                    "folio_number": record["folio_number"],
                    "created_at": record["created_at"],
                    "person_count": record["person_count"],
                    "person_names": [n for n in record["person_names"] if n],
                    "crimes": [c for c in record["crimes"] if c]
                })

            return folios

    def list_all_locations(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        List all locations in the database

        Args:
            limit: Maximum number of results
            offset: Skip first N results

        Returns:
            List of locations with associated counts
        """
        with self.driver.session() as session:
            query = """
            MATCH (l:Location)
            OPTIONAL MATCH (l)<-[r]-(p:Person)
            RETURN l.value as location,
                   l.created_at as created_at,
                   count(DISTINCT p) as person_count,
                   collect(DISTINCT type(r)) as relationship_types
            ORDER BY person_count DESC, l.value
            SKIP $offset
            LIMIT $limit
            """

            result = session.run(query, limit=limit, offset=offset)
            locations = []

            for record in result:
                locations.append({
                    "location": record["location"],
                    "created_at": record["created_at"],
                    "person_count": record["person_count"],
                    "relationship_types": [r for r in record["relationship_types"] if r]
                })

            return locations

    def get_database_stats(self) -> Dict[str, Any]:
        """
        Get database statistics

        Returns:
            Dictionary with counts of each entity type
        """
        with self.driver.session() as session:
            # Use separate OPTIONAL MATCH for each node type to handle missing types
            query = """
            OPTIONAL MATCH (p:Person)
            OPTIONAL MATCH (f:Folio)
            OPTIONAL MATCH (d:Delito)
            OPTIONAL MATCH (l:Location)
            OPTIONAL MATCH (face:Face)
            OPTIONAL MATCH (a:Analysis)
            RETURN count(DISTINCT p) as person_count,
                   count(DISTINCT f) as folio_count,
                   count(DISTINCT d) as crime_count,
                   count(DISTINCT l) as location_count,
                   count(DISTINCT face) as face_count,
                   count(DISTINCT a) as analysis_count
            """

            result = session.run(query)
            record = result.single()

            if record:
                return {
                    "persons": record["person_count"],
                    "folios": record["folio_count"],
                    "crimes": record["crime_count"],
                    "locations": record["location_count"],
                    "faces": record["face_count"],
                    "analyses": record["analysis_count"]
                }

            return {
                "persons": 0,
                "folios": 0,
                "crimes": 0,
                "locations": 0,
                "faces": 0,
                "analyses": 0
            }

    # ========================================================================
    # Object Detection Methods
    # ========================================================================

    def create_object_node(
        self,
        object_id: str,
        object_type: str,
        object_type_es: str,
        category: str,
        confidence: float,
        photo_url: str,
        bbox: Optional[List[float]] = None,
        tags: Optional[List[str]] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create an Object node in Neo4j

        Args:
            object_id: Unique object ID
            object_type: Object type (English, from YOLO)
            object_type_es: Object type (Spanish translation)
            category: Investigation category (Spanish)
            confidence: Detection confidence (0.0-1.0)
            photo_url: MinIO URL for the object photo
            bbox: Bounding box [x1, y1, x2, y2]
            tags: Spanish tags for filtering
            description: Optional description
            metadata: Additional metadata

        Returns:
            Object ID
        """
        with self.driver.session() as session:
            metadata_json = json.dumps(metadata) if metadata else "{}"
            bbox_json = json.dumps(bbox) if bbox else None
            tags = tags or []

            query = """
            CREATE (o:Object {
                id: $object_id,
                object_type: $object_type,
                object_type_es: $object_type_es,
                category: $category,
                confidence: $confidence,
                photo_url: $photo_url,
                bbox: $bbox_json,
                tags: $tags,
                description: $description,
                created_at: $created_at,
                metadata: $metadata_json
            })
            RETURN o.id as id
            """

            result = session.run(
                query,
                object_id=object_id,
                object_type=object_type,
                object_type_es=object_type_es,
                category=category,
                confidence=confidence,
                photo_url=photo_url,
                bbox_json=bbox_json,
                tags=tags,
                description=description,
                created_at=datetime.utcnow().isoformat(),
                metadata_json=metadata_json
            )

            node_id = result.single()["id"]
            logger.info("Object node created", object_id=object_id, object_type_es=object_type_es, category=category)
            return node_id

    def link_object_to_analysis(self, object_id: str, analysis_id: str) -> None:
        """
        Link an Object to an Analysis

        Args:
            object_id: Object node ID
            analysis_id: Analysis node ID
        """
        with self.driver.session() as session:
            query = """
            MATCH (o:Object {id: $object_id})
            MATCH (a:Analysis {id: $analysis_id})
            MERGE (o)-[:FOUND_IN_ANALYSIS {
                created_at: $created_at
            }]->(a)
            """

            session.run(
                query,
                object_id=object_id,
                analysis_id=analysis_id,
                created_at=datetime.utcnow().isoformat()
            )

            logger.info("Object linked to Analysis", object_id=object_id, analysis_id=analysis_id)

    def link_object_to_folio(self, object_id: str, folio_id: str) -> None:
        """
        Link an Object to a Folio

        Args:
            object_id: Object node ID
            folio_id: Folio node ID
        """
        with self.driver.session() as session:
            query = """
            MATCH (o:Object {id: $object_id})
            MATCH (f:Folio {id: $folio_id})
            MERGE (o)-[:RELATED_TO_FOLIO {
                created_at: $created_at
            }]->(f)
            """

            session.run(
                query,
                object_id=object_id,
                folio_id=folio_id,
                created_at=datetime.utcnow().isoformat()
            )

            logger.info("Object linked to Folio", object_id=object_id, folio_id=folio_id)

    def get_objects_by_category(self, category: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get objects by category

        Args:
            category: Category name in Spanish (e.g., "armas", "vehículos", "electrónicos")
            limit: Maximum number of results
            offset: Skip first N results

        Returns:
            List of objects with metadata
        """
        with self.driver.session() as session:
            query = """
            MATCH (o:Object {category: $category})
            OPTIONAL MATCH (o)-[:FOUND_IN_ANALYSIS]->(a:Analysis)
            OPTIONAL MATCH (o)-[:RELATED_TO_FOLIO]->(f:Folio)
            RETURN o.id as object_id,
                   o.object_type_es as object_type,
                   o.category as category,
                   o.confidence as confidence,
                   o.photo_url as photo_url,
                   o.description as description,
                   o.tags as tags,
                   o.created_at as created_at,
                   collect(DISTINCT a.id) as analysis_ids,
                   collect(DISTINCT f.folio_number) as folio_numbers
            ORDER BY o.created_at DESC
            SKIP $offset
            LIMIT $limit
            """

            result = session.run(query, category=category, limit=limit, offset=offset)
            objects = []

            for record in result:
                objects.append({
                    "object_id": record["object_id"],
                    "object_type": record["object_type"],
                    "category": record["category"],
                    "confidence": record["confidence"],
                    "photo_url": record["photo_url"],
                    "description": record["description"],
                    "tags": record["tags"] or [],
                    "created_at": record["created_at"],
                    "analysis_ids": [a for a in record["analysis_ids"] if a],
                    "folio_numbers": [f for f in record["folio_numbers"] if f]
                })

            return objects

    def get_objects_by_tag(self, tag: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get objects by tag

        Args:
            tag: Tag to search for (Spanish)
            limit: Maximum number of results
            offset: Skip first N results

        Returns:
            List of objects with metadata
        """
        with self.driver.session() as session:
            query = """
            MATCH (o:Object)
            WHERE $tag IN o.tags
            OPTIONAL MATCH (o)-[:FOUND_IN_ANALYSIS]->(a:Analysis)
            OPTIONAL MATCH (o)-[:RELATED_TO_FOLIO]->(f:Folio)
            RETURN o.id as object_id,
                   o.object_type_es as object_type,
                   o.category as category,
                   o.confidence as confidence,
                   o.photo_url as photo_url,
                   o.description as description,
                   o.tags as tags,
                   o.created_at as created_at,
                   collect(DISTINCT a.id) as analysis_ids,
                   collect(DISTINCT f.folio_number) as folio_numbers
            ORDER BY o.created_at DESC
            SKIP $offset
            LIMIT $limit
            """

            result = session.run(query, tag=tag, limit=limit, offset=offset)
            objects = []

            for record in result:
                objects.append({
                    "object_id": record["object_id"],
                    "object_type": record["object_type"],
                    "category": record["category"],
                    "confidence": record["confidence"],
                    "photo_url": record["photo_url"],
                    "description": record["description"],
                    "tags": record["tags"] or [],
                    "created_at": record["created_at"],
                    "analysis_ids": [a for a in record["analysis_ids"] if a],
                    "folio_numbers": [f for f in record["folio_numbers"] if f]
                })

            return objects

    def list_all_objects(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        List all objects in the database

        Args:
            limit: Maximum number of results
            offset: Skip first N results

        Returns:
            List of objects with metadata
        """
        with self.driver.session() as session:
            query = """
            MATCH (o:Object)
            OPTIONAL MATCH (o)-[:FOUND_IN_ANALYSIS]->(a:Analysis)
            OPTIONAL MATCH (o)-[:RELATED_TO_FOLIO]->(f:Folio)
            RETURN o.id as object_id,
                   o.object_type_es as object_type,
                   o.category as category,
                   o.confidence as confidence,
                   o.photo_url as photo_url,
                   o.description as description,
                   o.tags as tags,
                   o.created_at as created_at,
                   count(DISTINCT a) as analysis_count,
                   count(DISTINCT f) as folio_count
            ORDER BY o.created_at DESC
            SKIP $offset
            LIMIT $limit
            """

            result = session.run(query, limit=limit, offset=offset)
            objects = []

            for record in result:
                objects.append({
                    "object_id": record["object_id"],
                    "object_type": record["object_type"],
                    "category": record["category"],
                    "confidence": record["confidence"],
                    "photo_url": record["photo_url"],
                    "description": record["description"],
                    "tags": record["tags"] or [],
                    "created_at": record["created_at"],
                    "analysis_count": record["analysis_count"],
                    "folio_count": record["folio_count"]
                })

            return objects

    def get_object_categories_stats(self) -> List[Dict[str, Any]]:
        """
        Get statistics for each object category

        Returns:
            List of categories with object counts
        """
        with self.driver.session() as session:
            query = """
            MATCH (o:Object)
            RETURN o.category as category,
                   count(o) as object_count,
                   collect(DISTINCT o.object_type_es)[0..5] as sample_types
            ORDER BY object_count DESC
            """

            result = session.run(query)
            stats = []

            for record in result:
                stats.append({
                    "category": record["category"],
                    "object_count": record["object_count"],
                    "sample_types": [t for t in record["sample_types"] if t]
                })

            return stats

    def close(self):
        """Close database connection"""
        self.driver.close()
