"""
Qdrant vector database service for storing and searching face embeddings
"""
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from typing import List, Dict, Any, Optional, Tuple
from config import settings
import structlog
import uuid

logger = structlog.get_logger()


class QdrantService:
    """Service for storing and searching face embeddings and object embeddings in Qdrant"""

    COLLECTION_NAME = "face_embeddings"
    VECTOR_SIZE = 512  # InsightFace embedding size

    OBJECT_COLLECTION_NAME = "object_embeddings"
    OBJECT_VECTOR_SIZE = 512  # CLIP base model embedding size
    
    def __init__(self):
        """Initialize Qdrant client and ensure collections exist"""
        try:
            self.client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
                timeout=30,
                check_compatibility=False,
            )

            # Check if collections exist, create if not
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]

            # Create face embeddings collection
            if self.COLLECTION_NAME not in collection_names:
                logger.info("Creating Qdrant collection", collection=self.COLLECTION_NAME)
                self.client.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=self.VECTOR_SIZE,
                        distance=Distance.COSINE
                    )
                )
                logger.info("Qdrant face collection created", collection=self.COLLECTION_NAME)
            else:
                logger.info("Qdrant face collection exists", collection=self.COLLECTION_NAME)

            # Create object embeddings collection
            if self.OBJECT_COLLECTION_NAME not in collection_names:
                logger.info("Creating Qdrant object collection", collection=self.OBJECT_COLLECTION_NAME)
                from qdrant_client.models import OptimizersConfigDiff
                self.client.create_collection(
                    collection_name=self.OBJECT_COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=self.OBJECT_VECTOR_SIZE,
                        distance=Distance.COSINE
                    ),
                    optimizers_config=OptimizersConfigDiff(
                        indexing_threshold=1  # Index when 1+ points (0 means never index)
                    )
                )
                logger.info("Qdrant object collection created", collection=self.OBJECT_COLLECTION_NAME)
            else:
                # Update existing collection to index immediately
                logger.info("Qdrant object collection exists", collection=self.OBJECT_COLLECTION_NAME)
                try:
                    from qdrant_client.models import OptimizersConfigDiff
                    self.client.update_collection(
                        collection_name=self.OBJECT_COLLECTION_NAME,
                        optimizers_config=OptimizersConfigDiff(
                            indexing_threshold=1  # Index when 1+ points (0 means never index)
                        )
                    )
                    logger.info("Updated object collection to index immediately")
                except Exception as e:
                    logger.warning("Failed to update collection optimizer config", error=str(e))

        except Exception as e:
            logger.error("Failed to initialize Qdrant client", error=str(e), exc_info=True)
            raise
    
    def store_face_embedding(
        self,
        embedding: List[float],
        face_id: str,
        photo_id: str,
        analysis_id: str,
        person_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Store a face embedding in Qdrant
        
        Args:
            embedding: Face embedding vector (512 numbers)
            face_id: Unique face identifier
            photo_id: Photo identifier
            analysis_id: Analysis identifier
            person_id: Optional Person ID if already linked
            metadata: Additional metadata
            
        Returns:
            Point ID in Qdrant
        """
        point_id = str(uuid.uuid4())
        
        payload = {
            "face_id": face_id,
            "photo_id": photo_id,
            "analysis_id": analysis_id,
            "person_id": person_id,
            **(metadata or {})
        }
        
        point = PointStruct(
            id=point_id,
            vector=embedding,
            payload=payload
        )
        
        self.client.upsert(
            collection_name=self.COLLECTION_NAME,
            points=[point]
        )
        
        logger.info(
            "Face embedding stored in Qdrant",
            point_id=point_id,
            face_id=face_id,
            person_id=person_id
        )
        
        return point_id
    
    def search_similar_faces(
        self,
        query_embedding: List[float],
        threshold: float = 0.7,
        limit: int = 10,
        exclude_person_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar faces in Qdrant
        
        Args:
            query_embedding: Face embedding to search for
            threshold: Minimum similarity score (0.0-1.0)
            limit: Maximum number of results
            exclude_person_id: Optional person ID to exclude from results
            
        Returns:
            List of matches with score, face_id, person_id, etc.
        """
        # Build filter if needed
        query_filter = None
        if exclude_person_id:
            query_filter = Filter(
                must_not=[
                    FieldCondition(
                        key="person_id",
                        match=MatchValue(value=exclude_person_id)
                    )
                ]
            )
        
        # Use query_points with direct vector list (simplest approach)
        # query_points accepts the vector directly without Query wrapper
        query_kwargs = {
            "collection_name": self.COLLECTION_NAME,
            "query": query_embedding,  # Direct list of floats
            "limit": limit
        }
        
        # Add score_threshold if supported
        if threshold > 0:
            query_kwargs["score_threshold"] = threshold
        
        # Add filter if provided
        if query_filter:
            query_kwargs["query_filter"] = query_filter
        
        try:
            results_response = self.client.query_points(**query_kwargs)
        except TypeError as e:
            # If query_filter parameter name is wrong, try 'filter' instead
            if "query_filter" in str(e) or "unexpected keyword" in str(e).lower():
                logger.debug("query_filter parameter not recognized, trying 'filter'")
                query_kwargs.pop("query_filter", None)
                if query_filter:
                    query_kwargs["filter"] = query_filter
                results_response = self.client.query_points(**query_kwargs)
            else:
                raise
        
        # Extract points from response
        results = results_response.points
        
        matches = []
        for result in results:
            # query_points returns ScoredPoint objects with id, score, and payload
            matches.append({
                "point_id": result.id,
                "score": result.score,  # Cosine similarity (0.0-1.0)
                "face_id": result.payload.get("face_id") if isinstance(result.payload, dict) else None,
                "photo_id": result.payload.get("photo_id") if isinstance(result.payload, dict) else None,
                "analysis_id": result.payload.get("analysis_id") if isinstance(result.payload, dict) else None,
                "person_id": result.payload.get("person_id") if isinstance(result.payload, dict) else None,
                "metadata": result.payload if isinstance(result.payload, dict) else {}
            })
        
        logger.info(
            "Face search completed",
            matches_found=len(matches),
            threshold=threshold
        )
        
        return matches
    
    def update_person_id(self, point_id: str, person_id: str) -> None:
        """
        Update the person_id for a face embedding
        
        Args:
            point_id: Qdrant point ID
            person_id: Person ID to link
        """
        self.client.set_payload(
            collection_name=self.COLLECTION_NAME,
            payload={"person_id": person_id},
            points=[point_id]
        )
        
        logger.info("Updated person_id for face embedding", point_id=point_id, person_id=person_id)
    
    def get_faces_by_person(self, person_id: str) -> List[Dict[str, Any]]:
        """
        Get all face embeddings for a specific person
        
        Args:
            person_id: Person ID
            
        Returns:
            List of face embeddings with metadata
        """
        results = self.client.scroll(
            collection_name=self.COLLECTION_NAME,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="person_id",
                        match=MatchValue(value=person_id)
                    )
                ]
            ),
            limit=1000  # Adjust as needed
        )
        
        faces = []
        for point in results[0]:  # results is (points, next_page_offset)
            faces.append({
                "point_id": point.id,
                "face_id": point.payload.get("face_id"),
                "photo_id": point.payload.get("photo_id"),
                "analysis_id": point.payload.get("analysis_id"),
                "embedding": point.vector,
                "metadata": point.payload
            })
        
        return faces

    # ========================================================================
    # Object Embedding Methods
    # ========================================================================

    def store_object_embedding(
        self,
        embedding: List[float],
        object_id: str,
        object_type: str,
        object_type_es: str,
        category: str,
        photo_id: str,
        photo_url: Optional[str],
        analysis_id: str,
        folio_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Store an object embedding in Qdrant

        Args:
            embedding: Object embedding vector (512 numbers from CLIP)
            object_id: Unique object identifier
            object_type: Object type (English)
            object_type_es: Object type (Spanish)
            category: Investigation category (Spanish)
            photo_id: Photo identifier
            photo_url: MinIO URL for the object photo
            analysis_id: Analysis identifier
            folio_id: Optional Folio ID if linked
            tags: Optional tags (Spanish)
            metadata: Additional metadata

        Returns:
            Point ID in Qdrant
        """
        point_id = str(uuid.uuid4())

        payload = {
            "object_id": object_id,
            "object_type": object_type,
            "object_type_es": object_type_es,
            "category": category,
            "photo_id": photo_id,
            "photo_url": photo_url,
            "analysis_id": analysis_id,
            "folio_id": folio_id,
            "tags": tags or [],
            **(metadata or {})
        }

        point = PointStruct(
            id=point_id,
            vector=embedding,
            payload=payload
        )

        self.client.upsert(
            collection_name=self.OBJECT_COLLECTION_NAME,
            points=[point]
        )

        logger.info(
            "Object embedding stored in Qdrant",
            point_id=point_id,
            object_id=object_id,
            object_type_es=object_type_es,
            category=category
        )

        return point_id

    def search_similar_objects(
        self,
        query_embedding: List[float],
        threshold: float = 0.25,
        limit: int = 10,
        category_filter: Optional[str] = None,
        tag_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar objects in Qdrant

        Args:
            query_embedding: Object embedding to search for (from image or text)
            threshold: Minimum similarity score (0.0-1.0)
            limit: Maximum number of results
            category_filter: Optional category to filter by (Spanish)
            tag_filter: Optional tag to filter by (Spanish)

        Returns:
            List of matches with score, object_id, object_type, etc.
        """
        # Build filter if needed
        query_filter = None
        if category_filter or tag_filter:
            must_conditions = []
            if category_filter:
                must_conditions.append(
                    FieldCondition(
                        key="category",
                        match=MatchValue(value=category_filter)
                    )
                )
            if tag_filter:
                must_conditions.append(
                    FieldCondition(
                        key="tags",
                        match=MatchValue(value=tag_filter)
                    )
                )
            query_filter = Filter(must=must_conditions)

        query_kwargs = {
            "collection_name": self.OBJECT_COLLECTION_NAME,
            "query": query_embedding,
            "limit": limit
        }

        if threshold > 0:
            query_kwargs["score_threshold"] = threshold

        if query_filter:
            query_kwargs["query_filter"] = query_filter

        try:
            results_response = self.client.query_points(**query_kwargs)
        except TypeError as e:
            if "query_filter" in str(e) or "unexpected keyword" in str(e).lower():
                logger.debug("query_filter parameter not recognized, trying 'filter'")
                query_kwargs.pop("query_filter", None)
                if query_filter:
                    query_kwargs["filter"] = query_filter
                results_response = self.client.query_points(**query_kwargs)
            else:
                raise

        results = results_response.points

        # Build filters description
        filters_parts = []
        if category_filter:
            filters_parts.append(f"category={category_filter}")
        if tag_filter:
            filters_parts.append(f"tag={tag_filter}")
        filters_str = ", ".join(filters_parts) if filters_parts else "none"

        # Build results table
        results_lines = []
        matches = []
        for idx, result in enumerate(results):
            payload = result.payload if isinstance(result.payload, dict) else {}
            object_type_es = payload.get("object_type_es", "?")
            object_id = payload.get("object_id", "?")
            category = payload.get("category", "?")
            folio_id = payload.get("folio_id", "-")
            score = result.score

            # Pad fields for aligned table output
            type_padded = object_type_es.ljust(18)
            cat_padded = category.ljust(14)
            folio_padded = str(folio_id or "-").ljust(10)

            results_lines.append(
                f"|  #{idx+1:<3} {type_padded} score: {score:.4f}   category: {cat_padded} folio: {folio_padded}"
            )

            matches.append({
                "point_id": result.id,
                "score": score,
                "object_id": payload.get("object_id"),
                "object_type": payload.get("object_type"),
                "object_type_es": object_type_es,
                "category": payload.get("category"),
                "photo_id": payload.get("photo_id"),
                "analysis_id": payload.get("analysis_id"),
                "folio_id": payload.get("folio_id"),
                "tags": payload.get("tags", []),
                "metadata": payload
            })

        results_table = "\n".join(results_lines) if results_lines else "|  (no matches)"

        logger.info(
            "\n"
            "+--------------------------------------------------------------\n"
            "|  [3/3] QDRANT VECTOR SEARCH\n"
            "+--------------------------------------------------------------\n"
            f"|  Collection:  {self.OBJECT_COLLECTION_NAME}\n"
            f"|  Threshold:   {threshold}\n"
            f"|  Limit:       {limit}\n"
            f"|  Filters:     {filters_str}\n"
            f"|  Results:     {len(matches)} match(es)\n"
            "+--------------------------------------------------------------\n"
            f"{results_table}\n"
            "+--------------------------------------------------------------"
        )

        return matches

    def get_objects_by_category(self, category: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get all objects in a specific category

        Args:
            category: Category name (Spanish)
            limit: Maximum number of results

        Returns:
            List of objects with metadata
        """
        results = self.client.scroll(
            collection_name=self.OBJECT_COLLECTION_NAME,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="category",
                        match=MatchValue(value=category)
                    )
                ]
            ),
            limit=limit
        )

        objects = []
        for point in results[0]:
            objects.append({
                "point_id": point.id,
                "object_id": point.payload.get("object_id"),
                "object_type_es": point.payload.get("object_type_es"),
                "category": point.payload.get("category"),
                "photo_id": point.payload.get("photo_id"),
                "analysis_id": point.payload.get("analysis_id"),
                "folio_id": point.payload.get("folio_id"),
                "tags": point.payload.get("tags", []),
                "metadata": point.payload
            })

        return objects
