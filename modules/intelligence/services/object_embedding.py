"""
Object embedding service using CLIP for semantic similarity.

Text search strategy (in priority order):
1. Known COCO Spanish term → translate to English → CLIP prompt template → original CLIP text encoder
2. Unknown Spanish text → multilingual CLIP model (sentence-transformers) → prompt template
3. Fallback → original CLIP text encoder with prompt template

Image embeddings always use the original CLIP ViT-B/32 model (unchanged).
The multilingual text model maps into the same vector space, so no re-indexing is needed.
"""
import structlog
from typing import List, Optional, Tuple
import numpy as np
from PIL import Image
import torch

logger = structlog.get_logger()


class ObjectEmbeddingService:
    """Service for generating object embeddings using CLIP"""

    def __init__(self, model_name: str = "openai/clip-vit-base-patch32"):
        """
        Initialize CLIP embedding service with optional multilingual text support.

        Args:
            model_name: HuggingFace CLIP model name
                       Options: openai/clip-vit-base-patch32 (default, balanced)
                               openai/clip-vit-large-patch14 (more accurate, slower)
        """
        self.model_name = model_name
        self.model = None
        self.processor = None
        self.device = None
        self.initialized = False
        self.embedding_dim = 512  # CLIP base model
        self.multilingual_model = None

        # Build Spanish→English reverse lookup from COCO classes
        self._spanish_to_english = {}
        try:
            from modules.intelligence.services.object_detection import COCO_SPANISH
            self._spanish_to_english = {v.lower(): k for k, v in COCO_SPANISH.items()}
            logger.info("Loaded COCO Spanish→English mapping", terms=len(self._spanish_to_english))
        except Exception as e:
            logger.warning("Could not load COCO translations", error=str(e))

        # Initialize original CLIP model (used for images and translated English text)
        try:
            from transformers import CLIPProcessor, CLIPModel

            logger.info("Initializing CLIP embedding service", model=model_name)

            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            if self.device == "cuda":
                logger.info("Using GPU for CLIP embeddings")
            else:
                logger.info("Using CPU for CLIP embeddings (consider GPU for better performance)")

            self.processor = CLIPProcessor.from_pretrained(model_name)
            self.model = CLIPModel.from_pretrained(model_name).to(self.device)
            self.model.eval()

            self.embedding_dim = self.model.config.projection_dim

            self.initialized = True
            logger.info(
                "CLIP initialized successfully",
                device=self.device,
                embedding_dim=self.embedding_dim
            )

        except Exception as e:
            logger.error("Failed to initialize CLIP", error=str(e))
            self.initialized = False

        # Initialize multilingual text model (for Spanish queries not in COCO dictionary)
        try:
            from sentence_transformers import SentenceTransformer

            multilingual_model_name = "sentence-transformers/clip-ViT-B-32-multilingual-v1"
            logger.info("Loading multilingual CLIP text model", model=multilingual_model_name)
            self.multilingual_model = SentenceTransformer(multilingual_model_name)
            logger.info("Multilingual CLIP text model loaded successfully")

        except ImportError:
            logger.warning(
                "sentence-transformers not installed, multilingual text search unavailable. "
                "Install with: pip install sentence-transformers"
            )
        except Exception as e:
            logger.warning("Failed to load multilingual CLIP model, falling back to standard CLIP", error=str(e))

    def _translate_known_term(self, text: str) -> Optional[str]:
        """
        Try to translate a known COCO Spanish term to English.

        Args:
            text: Spanish text query

        Returns:
            English translation if found, None otherwise
        """
        text_lower = text.lower().strip()
        if text_lower in self._spanish_to_english:
            return self._spanish_to_english[text_lower]
        return None

    def _enhance_query(self, text: str) -> Tuple[str, str]:
        """
        Enhance a text query for better CLIP matching.

        Strategy:
        1. If text is a known COCO Spanish term → translate to English + CLIP prompt
        2. Otherwise → use original text with CLIP prompt

        Args:
            text: Original query text (typically Spanish)

        Returns:
            Tuple of (enhanced_text, method) where method is "translation" or "multilingual" or "prompt_only"
        """
        english_term = self._translate_known_term(text)

        if english_term:
            enhanced = f"a photo of a {english_term}"
            return enhanced, "translation"

        # No known translation — will use multilingual model or fallback
        enhanced = f"a photo of {text}"
        if self.multilingual_model:
            return enhanced, "multilingual"
        return enhanced, "prompt_only"

    def _encode_with_clip(self, text: str) -> Optional[np.ndarray]:
        """
        Encode text using the original CLIP text encoder.

        Args:
            text: Text to encode (should be English for best results)

        Returns:
            Normalized embedding as numpy array, or None on failure
        """
        if not self.initialized:
            return None

        try:
            inputs = self.processor(text=[text], return_tensors="pt", padding=True).to(self.device)

            with torch.no_grad():
                outputs = self.model.get_text_features(**inputs)

            if isinstance(outputs, torch.Tensor):
                text_features = outputs
            else:
                if hasattr(outputs, 'text_embeds'):
                    text_features = outputs.text_embeds
                elif hasattr(outputs, 'pooler_output'):
                    text_features = outputs.pooler_output
                elif isinstance(outputs, (list, tuple)) and len(outputs) > 0:
                    text_features = outputs[0]
                else:
                    text_features = torch.tensor(outputs) if not torch.is_tensor(outputs) else outputs

            embedding = text_features / text_features.norm(dim=-1, keepdim=True)
            return embedding.cpu().numpy().flatten()

        except Exception as e:
            logger.error("CLIP text encoding failed", error=str(e), text=text)
            return None

    def _encode_with_multilingual(self, text: str) -> Optional[np.ndarray]:
        """
        Encode text using the multilingual sentence-transformers CLIP model.
        Produces embeddings in the same vector space as CLIP ViT-B/32 image embeddings.

        Args:
            text: Text to encode (supports Spanish and 50+ other languages)

        Returns:
            Normalized embedding as numpy array, or None on failure
        """
        if not self.multilingual_model:
            return None

        try:
            embedding = self.multilingual_model.encode(text)
            # Normalize
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm
            return embedding.flatten()

        except Exception as e:
            logger.error("Multilingual text encoding failed", error=str(e), text=text)
            return None

    def generate_image_embedding(self, image_path: str, bbox: Optional[List[float]] = None) -> Optional[np.ndarray]:
        """
        Generate embedding for an image or cropped region.

        Args:
            image_path: Path to image file
            bbox: Optional bounding box [x1, y1, x2, y2] to crop before embedding

        Returns:
            Embedding vector as numpy array (shape: [embedding_dim])
        """
        if not self.initialized:
            logger.error("CLIP service not initialized")
            return None

        try:
            image = Image.open(image_path).convert("RGB")

            if bbox:
                x1, y1, x2, y2 = bbox
                image = image.crop((x1, y1, x2, y2))

            inputs = self.processor(images=image, return_tensors="pt").to(self.device)

            with torch.no_grad():
                outputs = self.model.get_image_features(**inputs)

            if isinstance(outputs, torch.Tensor):
                image_features = outputs
            else:
                if hasattr(outputs, 'image_embeds'):
                    image_features = outputs.image_embeds
                elif hasattr(outputs, 'pooler_output'):
                    image_features = outputs.pooler_output
                elif isinstance(outputs, (list, tuple)) and len(outputs) > 0:
                    image_features = outputs[0]
                else:
                    image_features = torch.tensor(outputs) if not torch.is_tensor(outputs) else outputs

            embedding = image_features / image_features.norm(dim=-1, keepdim=True)
            embedding_np = embedding.cpu().numpy().flatten()

            embedding_norm = np.linalg.norm(embedding_np)
            embedding_mean = np.mean(embedding_np)
            embedding_std = np.std(embedding_np)

            logger.info(
                "Image embedding generated",
                image=image_path.split('/')[-1] if '/' in image_path else image_path,
                embedding_dim=len(embedding_np),
                norm=f"{embedding_norm:.4f}",
                mean=f"{embedding_mean:.4f}",
                std=f"{embedding_std:.4f}",
                bbox="full_image" if bbox is None else "cropped"
            )

            return embedding_np

        except Exception as e:
            logger.error("Failed to generate image embedding", error=str(e), image=image_path)
            return None

    def generate_text_embedding(self, text: str) -> Optional[np.ndarray]:
        """
        Generate embedding for text query with smart enhancement.

        Strategy:
        1. Known COCO Spanish term → translate to English → CLIP prompt → original CLIP encoder
        2. Unknown Spanish text → CLIP prompt → multilingual model
        3. Fallback → CLIP prompt → original CLIP encoder

        Args:
            text: Text query (e.g., "mesa", "pistola negra", "celular iPhone")

        Returns:
            Embedding vector as numpy array (shape: [embedding_dim])
        """
        if not self.initialized:
            logger.error("CLIP service not initialized")
            return None

        try:
            enhanced_text, method = self._enhance_query(text)

            # Determine which encoder will be used
            if method == "translation":
                encoder_name = "CLIP ViT-B/32 (English)"
                method_desc = "COCO Spanish -> English translation"
            elif method == "multilingual":
                encoder_name = "Multilingual CLIP (sentence-transformers)"
                method_desc = "Multilingual model (native Spanish)"
            else:
                encoder_name = "CLIP ViT-B/32 (fallback)"
                method_desc = "Prompt engineering only"

            english_term = self._translate_known_term(text)
            translation_line = f"  Translation: \"{text}\" -> \"{english_term}\"" if english_term else f"  Translation: not in COCO dictionary"

            logger.info(
                "\n"
                "+--------------------------------------------------------------\n"
                "|  [1/3] QUERY ENHANCEMENT\n"
                "+--------------------------------------------------------------\n"
                f"|  Original:    \"{text}\"\n"
                f"|  {translation_line}\n"
                f"|  Enhanced:    \"{enhanced_text}\"\n"
                f"|  Method:      {method_desc}\n"
                f"|  Encoder:     {encoder_name}\n"
                "+--------------------------------------------------------------"
            )

            embedding_np = None

            if method == "translation":
                embedding_np = self._encode_with_clip(enhanced_text)
            elif method == "multilingual":
                embedding_np = self._encode_with_multilingual(enhanced_text)
                if embedding_np is None:
                    logger.warning("Multilingual encoding failed, falling back to CLIP", text=text)
                    embedding_np = self._encode_with_clip(enhanced_text)
            else:
                embedding_np = self._encode_with_clip(enhanced_text)

            if embedding_np is not None:
                embedding_norm = np.linalg.norm(embedding_np)

                logger.info(
                    "\n"
                    "+--------------------------------------------------------------\n"
                    "|  [2/3] EMBEDDING GENERATED\n"
                    "+--------------------------------------------------------------\n"
                    f"|  Dimensions:  {len(embedding_np)}\n"
                    f"|  Norm:        {embedding_norm:.4f}\n"
                    f"|  Method:      {method}\n"
                    "+--------------------------------------------------------------"
                )
            else:
                logger.error(
                    "  [2/3] EMBEDDING FAILED — could not encode query",
                    text=text,
                    method=method
                )

            return embedding_np

        except Exception as e:
            logger.error("Failed to generate text embedding", error=str(e), text=text)
            return None

    def compute_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Similarity score (0.0-1.0)
        """
        try:
            emb1 = embedding1 / np.linalg.norm(embedding1)
            emb2 = embedding2 / np.linalg.norm(embedding2)
            similarity = np.dot(emb1, emb2)
            return float(similarity)

        except Exception as e:
            logger.error("Failed to compute similarity", error=str(e))
            return 0.0

    def get_embedding_dim(self) -> int:
        """Get embedding dimension (e.g., 512 for CLIP base)"""
        return self.embedding_dim
