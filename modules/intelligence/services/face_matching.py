"""
Face matching service using embeddings and cosine similarity
"""
import numpy as np
from typing import List, Tuple, Optional
import structlog

logger = structlog.get_logger()


class FaceMatchingService:
    """Service for matching faces using embeddings"""
    
    @staticmethod
    def cosine_similarity(embedding1: List[float], embedding2: List[float]) -> float:
        """
        Calculate cosine similarity between two embeddings.
        
        Cosine similarity ranges from -1 to 1:
        - 1.0 = Identical faces (same person)
        - 0.8-0.95 = Very similar (likely same person)
        - 0.6-0.8 = Somewhat similar (maybe same person)
        - < 0.6 = Different faces
        
        Args:
            embedding1: First face embedding (512 numbers)
            embedding2: Second face embedding (512 numbers)
            
        Returns:
            Similarity score between 0.0 and 1.0
        """
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        
        # Cosine similarity = dot product / (magnitude1 * magnitude2)
        dot_product = np.dot(vec1, vec2)
        magnitude1 = np.linalg.norm(vec1)
        magnitude2 = np.linalg.norm(vec2)
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        similarity = dot_product / (magnitude1 * magnitude2)
        return float(similarity)
    
    @staticmethod
    def find_best_match(
        query_embedding: List[float],
        candidate_embeddings: List[Tuple[str, List[float]]],
        threshold: float = 0.6
    ) -> Optional[Tuple[str, float]]:
        """
        Find the best matching face from a list of candidates.
        
        Args:
            query_embedding: The face embedding to match
            candidate_embeddings: List of (face_id, embedding) tuples
            threshold: Minimum similarity score (default: 0.6)
            
        Returns:
            Tuple of (best_match_face_id, similarity_score) or None if no match above threshold
        """
        best_match = None
        best_score = 0.0
        
        for face_id, candidate_embedding in candidate_embeddings:
            similarity = FaceMatchingService.cosine_similarity(
                query_embedding,
                candidate_embedding
            )
            
            if similarity > best_score:
                best_score = similarity
                best_match = face_id
        
        if best_score >= threshold:
            return (best_match, best_score)
        return None
    
    @staticmethod
    def find_all_matches(
        query_embedding: List[float],
        candidate_embeddings: List[Tuple[str, List[float]]],
        threshold: float = 0.6,
        limit: int = 10
    ) -> List[Tuple[str, float]]:
        """
        Find all matching faces above threshold, sorted by similarity.
        
        Args:
            query_embedding: The face embedding to match
            candidate_embeddings: List of (face_id, embedding) tuples
            threshold: Minimum similarity score (default: 0.6)
            limit: Maximum number of results (default: 10)
            
        Returns:
            List of (face_id, similarity_score) tuples, sorted by similarity (highest first)
        """
        matches = []
        
        for face_id, candidate_embedding in candidate_embeddings:
            similarity = FaceMatchingService.cosine_similarity(
                query_embedding,
                candidate_embedding
            )
            
            if similarity >= threshold:
                matches.append((face_id, similarity))
        
        # Sort by similarity (highest first)
        matches.sort(key=lambda x: x[1], reverse=True)
        
        return matches[:limit]
    
    @staticmethod
    def is_same_person(
        embedding1: List[float],
        embedding2: List[float],
        threshold: float = 0.7
    ) -> Tuple[bool, float]:
        """
        Determine if two embeddings belong to the same person.
        
        Args:
            embedding1: First face embedding
            embedding2: Second face embedding
            threshold: Similarity threshold (default: 0.7)
            
        Returns:
            Tuple of (is_same_person: bool, similarity_score: float)
        """
        similarity = FaceMatchingService.cosine_similarity(embedding1, embedding2)
        is_match = similarity >= threshold
        
        return (is_match, similarity)
