"""
IC9 — Modus Operandi Detection Service
Semantic similarity search over crime narratives using sentence-transformers + Qdrant.
"""
import uuid
from typing import Any, Dict, List, Optional

from config import settings, logger

# ── Lazy-loaded dependencies ──
_model = None
_qdrant_client = None
_st_available: Optional[bool] = None
_qdrant_available: Optional[bool] = None

COLLECTION_NAME = "narrativas_modus"
VECTOR_SIZE = 384  # paraphrase-multilingual-MiniLM-L12-v2 output dimension
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def _check_sentence_transformers() -> bool:
    global _st_available
    if _st_available is None:
        try:
            import sentence_transformers  # noqa: F401
            _st_available = True
        except ImportError:
            _st_available = False
    return _st_available


def _check_qdrant() -> bool:
    global _qdrant_available
    if _qdrant_available is None:
        try:
            from qdrant_client import QdrantClient  # noqa: F401
            _qdrant_available = True
        except ImportError:
            _qdrant_available = False
    return _qdrant_available


class ModusOperandiService:
    """Indexes crime narratives and finds similar modus operandi via vector search."""

    COLLECTION_NAME = COLLECTION_NAME

    def __init__(self):
        self.model = None
        self.client = None
        self._initialized = False

    # ── Lazy init ──────────────────────────────────────────────

    def _ensure_model(self):
        """Lazy-load the sentence-transformers model on first use."""
        global _model
        if self.model is not None:
            return
        if not _check_sentence_transformers():
            raise RuntimeError("sentence-transformers no instalado")
        if _model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading sentence-transformers model: {MODEL_NAME}")
            _model = SentenceTransformer(MODEL_NAME)
            logger.info("Sentence-transformers model loaded")
        self.model = _model

    def _ensure_qdrant(self):
        """Lazy-connect to Qdrant and ensure collection exists."""
        global _qdrant_client
        if self.client is not None:
            return
        if not _check_qdrant():
            raise RuntimeError("qdrant-client no instalado")
        if _qdrant_client is None:
            from qdrant_client import QdrantClient
            _qdrant_client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
                timeout=30,
                check_compatibility=False,
            )
        self.client = _qdrant_client
        self._ensure_collection()

    def _ensure_collection(self):
        """Create collection if it does not exist."""
        from qdrant_client.models import Distance, VectorParams

        collections = self.client.get_collections().collections
        names = [c.name for c in collections]
        if self.COLLECTION_NAME not in names:
            logger.info(f"Creating Qdrant collection: {self.COLLECTION_NAME}")
            self.client.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
            logger.info(f"Collection {self.COLLECTION_NAME} created")

    def _embed(self, text: str) -> List[float]:
        """Generate embedding for a text string."""
        self._ensure_model()
        vector = self.model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    # ── Public API ─────────────────────────────────────────────

    def index_narrative(
        self,
        carpeta_id: int,
        narrative_text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Index a crime narrative into Qdrant.

        Returns:
            point_id (UUID string)
        """
        self._ensure_qdrant()
        embedding = self._embed(narrative_text)

        point_id = str(uuid.uuid4())
        text_preview = narrative_text[:200]

        from qdrant_client.models import PointStruct

        payload = {
            "carpeta_id": carpeta_id,
            "text_preview": text_preview,
            **(metadata or {}),
        }

        self.client.upsert(
            collection_name=self.COLLECTION_NAME,
            points=[PointStruct(id=point_id, vector=embedding, payload=payload)],
        )

        logger.info(
            "Narrative indexed in Qdrant",
            point_id=point_id,
            carpeta_id=carpeta_id,
            text_len=len(narrative_text),
        )
        return point_id

    def search_similar(
        self,
        text: str,
        limit: int = 10,
        min_score: float = 0.6,
    ) -> List[Dict[str, Any]]:
        """
        Search for narratives semantically similar to the input text.

        Returns:
            List of {carpeta_id, text_preview, score, metadata}
        """
        self._ensure_qdrant()
        embedding = self._embed(text)

        query_kwargs: Dict[str, Any] = {
            "collection_name": self.COLLECTION_NAME,
            "query": embedding,
            "limit": limit,
        }
        if min_score > 0:
            query_kwargs["score_threshold"] = min_score

        try:
            response = self.client.query_points(**query_kwargs)
        except Exception as e:
            logger.error(f"Qdrant search failed: {e}")
            raise

        results = []
        for pt in response.points:
            payload = pt.payload if isinstance(pt.payload, dict) else {}
            results.append({
                "carpeta_id": payload.get("carpeta_id"),
                "text_preview": payload.get("text_preview", ""),
                "score": pt.score,
                "metadata": payload,
            })

        logger.info(
            "Modus operandi search completed",
            query_len=len(text),
            results=len(results),
            min_score=min_score,
        )
        return results

    def cluster_narratives(self, min_cluster_size: int = 3) -> List[Dict[str, Any]]:
        """
        Cluster all indexed narratives using DBSCAN / HDBSCAN.

        Returns:
            List of {cluster_id, label, narrativas: [{carpeta_id, text_preview}], count}
        """
        self._ensure_qdrant()
        self._ensure_model()

        # Fetch all points with vectors
        all_points = []
        offset = None
        while True:
            scroll_kwargs: Dict[str, Any] = {
                "collection_name": self.COLLECTION_NAME,
                "limit": 500,
                "with_vectors": True,
            }
            if offset is not None:
                scroll_kwargs["offset"] = offset

            points, next_offset = self.client.scroll(**scroll_kwargs)
            all_points.extend(points)
            if next_offset is None or len(points) == 0:
                break
            offset = next_offset

        if len(all_points) < min_cluster_size:
            logger.info(f"Not enough narratives for clustering ({len(all_points)} < {min_cluster_size})")
            return []

        import numpy as np

        vectors = np.array([p.vector for p in all_points])

        # Try HDBSCAN first, fall back to DBSCAN
        labels = None
        try:
            from hdbscan import HDBSCAN
            clusterer = HDBSCAN(min_cluster_size=min_cluster_size, metric="euclidean")
            labels = clusterer.fit_predict(vectors)
        except ImportError:
            pass

        if labels is None:
            try:
                from sklearn.cluster import DBSCAN
                clusterer = DBSCAN(eps=0.5, min_samples=min_cluster_size, metric="cosine")
                labels = clusterer.fit_predict(vectors)
            except ImportError:
                raise RuntimeError("Neither hdbscan nor scikit-learn is installed for clustering")

        # Group by cluster
        from collections import defaultdict, Counter

        clusters_map: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for i, point in enumerate(all_points):
            cluster_id = int(labels[i])
            if cluster_id == -1:  # noise
                continue
            payload = point.payload if isinstance(point.payload, dict) else {}
            clusters_map[cluster_id].append({
                "carpeta_id": payload.get("carpeta_id"),
                "text_preview": payload.get("text_preview", ""),
            })

        # Build result with labels from common words
        result = []
        for cluster_id, narrativas in clusters_map.items():
            # Simple label: most common words across previews
            all_words: List[str] = []
            for n in narrativas:
                words = n["text_preview"].lower().split()
                all_words.extend(w for w in words if len(w) > 3)
            common = Counter(all_words).most_common(5)
            label = " | ".join(w for w, _ in common) if common else f"cluster_{cluster_id}"

            result.append({
                "cluster_id": cluster_id,
                "label": label,
                "narrativas": narrativas,
                "count": len(narrativas),
            })

        result.sort(key=lambda c: c["count"], reverse=True)

        logger.info(
            "Narrative clustering completed",
            total_points=len(all_points),
            clusters_found=len(result),
        )
        return result
