"""
Face detection and recognition service using InsightFace
"""
import cv2
import numpy as np
import insightface
import platform
import os
import shutil
from typing import List, Optional, Tuple
from config import settings
import structlog

logger = structlog.get_logger()


class FaceDetectionService:
    """Service for face detection and recognition"""
    
    def __init__(self):
        self.app = None
        self.initialized = False
        self._initialize_model()
    
    def _fix_nested_extraction(self, model_dir: str, model_name: str) -> bool:
        """
        Fix nested directory structure created by zip extraction.
        
        Some zip files contain a folder with the same name as the model,
        creating: model_dir/model_name/*.onnx instead of model_dir/*.onnx
        
        Args:
            model_dir: Expected model directory path
            model_name: Model name (to check for nested folder)
            
        Returns:
            True if fix was applied, False if not needed
        """
        nested_dir = os.path.join(model_dir, model_name)
        
        # Check if nested directory exists and has .onnx files
        if not os.path.exists(nested_dir):
            return False
        
        nested_onnx_files = [f for f in os.listdir(nested_dir) if f.endswith('.onnx')]
        if not nested_onnx_files:
            return False
        
        logger.info(
            "Detected nested extraction structure, flattening...",
            nested_dir=nested_dir,
            files_count=len(nested_onnx_files)
        )
        
        # Move .onnx files from nested directory to model directory
        try:
            for filename in nested_onnx_files:
                src = os.path.join(nested_dir, filename)
                dst = os.path.join(model_dir, filename)
                if not os.path.exists(dst):  # Don't overwrite existing files
                    shutil.move(src, dst)
                    logger.debug("Moved model file", src=src, dst=dst)
            
            # Try to remove nested directory if empty
            try:
                if not os.listdir(nested_dir):
                    os.rmdir(nested_dir)
            except:
                pass  # Ignore if not empty or can't remove
            
            logger.info("Successfully flattened nested extraction structure")
            return True
            
        except Exception as e:
            logger.error("Failed to fix nested extraction", error=str(e))
            return False
    
    def _initialize_model(self):
        """
        Initialize InsightFace model - let InsightFace handle download/extraction,
        only intervene if it fails due to nested directory structure.
        """
        model_name = settings.insightface_model_name
        model_dir = os.path.expanduser(f"~/.insightface/models/{model_name}")
        
        try:
            logger.info("Initializing InsightFace model...", model=model_name)
            
            # Detect platform and set providers accordingly
            is_macos = platform.system() == "Darwin"
            is_linux = platform.system() == "Linux"
            
            # On macOS, only use CPU. On Linux, try CUDA first, then CPU
            if is_macos:
                providers = ['CPUExecutionProvider']
                ctx_id = -1  # CPU
                logger.info("Detected macOS - using CPU only")
            elif is_linux:
                providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
                ctx_id = 0 if settings.cuda_visible_devices else -1
                logger.info("Detected Linux - trying CUDA first")
            else:
                providers = ['CPUExecutionProvider']
                ctx_id = -1
                logger.info("Unknown platform - using CPU only")
            
            # Let InsightFace handle download/extraction automatically
            logger.info("Creating FaceAnalysis instance (will auto-download if needed)...")
            try:
                self.app = insightface.app.FaceAnalysis(
                    name=model_name,
                    providers=providers
                )
                self.app.prepare(ctx_id=ctx_id, det_size=(640, 640))
                
            except AssertionError as e:
                # InsightFace failed to find detection model
                # This often happens due to nested extraction structure
                logger.warning(
                    "Initial initialization failed, checking for nested extraction issue...",
                    error=str(e)
                )
                
                # Check and fix nested directory structure if present
                if self._fix_nested_extraction(model_dir, model_name):
                    # Retry after fixing nested structure
                    logger.info("Retrying initialization after fixing nested extraction structure...")
                    self.app = insightface.app.FaceAnalysis(
                        name=model_name,
                        providers=providers
                    )
                    self.app.prepare(ctx_id=ctx_id, det_size=(640, 640))
                    logger.info("Successfully initialized after fixing nested extraction")
                else:
                    # Nested fix didn't help, or structure was fine
                    # Try removing and re-downloading
                    logger.warning("Nested fix didn't resolve issue, attempting clean re-download...")
                    if os.path.exists(model_dir):
                        shutil.rmtree(model_dir)
                    
                    # Retry with fresh download
                    self.app = insightface.app.FaceAnalysis(
                        name=model_name,
                        providers=providers
                    )
                    self.app.prepare(ctx_id=ctx_id, det_size=(640, 640))
                    
                    # If still nested after re-download, fix it
                    self._fix_nested_extraction(model_dir, model_name)
                    # Re-initialize one more time
                    self.app = insightface.app.FaceAnalysis(
                        name=model_name,
                        providers=providers
                    )
                    self.app.prepare(ctx_id=ctx_id, det_size=(640, 640))
            
            # Verify model was initialized correctly
            if not hasattr(self.app, 'models') or 'detection' not in self.app.models:
                raise AssertionError("Model initialization incomplete - detection model not found")
            
            self.initialized = True
            logger.info(
                "InsightFace model initialized successfully",
                providers=providers,
                ctx_id=ctx_id,
                model=model_name,
                models_loaded=list(self.app.models.keys())
            )
            
        except AssertionError as e:
            error_msg = str(e)
            logger.error(
                "Failed to initialize InsightFace - model files issue",
                error=error_msg,
                error_type="AssertionError",
                exc_info=True
            )
            self.initialized = False
            logger.warning("Face detection will be disabled - analysis will continue without face detection")
        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            logger.error(
                "Failed to initialize InsightFace",
                error=error_msg,
                error_type=error_type,
                exc_info=True
            )
            self.initialized = False
            logger.warning("Face detection will be disabled - analysis will continue without face detection")
    
    def detect_faces(
        self,
        image_path: str,
        min_confidence: float = 0.6,
        min_face_size: int = 40
    ) -> List[dict]:
        """
        Detect faces in an image with quality filtering

        Args:
            image_path: Path to image file
            min_confidence: Minimum detection confidence (0.0-1.0, default 0.6)
            min_face_size: Minimum face width/height in pixels (default 40)

        Returns:
            List of face detection results with bbox, confidence, embedding, age, gender
        """
        if not self.initialized or self.app is None:
            logger.warning("Face detection service not initialized - skipping face detection")
            return []

        try:
            # Read image
            img = cv2.imread(image_path)
            if img is None:
                raise ValueError(f"Could not read image from {image_path}")

            # Convert BGR to RGB
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            # Detect faces
            faces = self.app.get(img_rgb)

            results = []
            filtered_count = 0

            for idx, face in enumerate(faces):
                det_confidence = float(face.det_score)

                # Extract bounding box
                bbox = face.bbox.astype(int).tolist()  # [x1, y1, x2, y2]
                # Convert to [x, y, width, height]
                bbox_normalized = [bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1]]

                face_width = bbox_normalized[2]
                face_height = bbox_normalized[3]

                # Quality filtering
                if det_confidence < min_confidence:
                    logger.info(
                        "Face filtered out - low confidence",
                        face_id=f"face_{idx}",
                        confidence=det_confidence,
                        threshold=min_confidence
                    )
                    filtered_count += 1
                    continue

                if face_width < min_face_size or face_height < min_face_size:
                    logger.info(
                        "Face filtered out - too small",
                        face_id=f"face_{idx}",
                        width=face_width,
                        height=face_height,
                        min_size=min_face_size
                    )
                    filtered_count += 1
                    continue

                # Get embedding (normalized vector)
                embedding = face.normed_embedding.tolist()

                # Build base result
                result = {
                    "face_id": f"face_{idx}",
                    "bbox": bbox_normalized,
                    "confidence": det_confidence,  # Detection confidence (face presence)
                    "embedding": embedding
                }

                # Optionally include demographic attributes (age/gender)
                # NOTE: These are often inaccurate and disabled by default
                if settings.face_include_demographics:
                    # Age and gender estimation are approximate and may be inaccurate.
                    # These estimates can be affected by:
                    # - Image quality, lighting, resolution
                    # - Hair style, facial hair, makeup
                    # - Pose, expression, occlusions
                    # - Model training data bias
                    age = int(face.age) if hasattr(face, 'age') and face.age else None
                    gender = None
                    if hasattr(face, 'gender') and face.gender is not None:
                        gender = "male" if face.gender == 1 else "female"

                    # Log warning if age seems unrealistic
                    if age is not None and (age < 10 or age > 80):
                        logger.warning(
                            "Age estimation may be inaccurate",
                            age=age,
                            face_id=f"face_{idx}",
                            confidence=det_confidence
                        )

                    result["age"] = age
                    result["gender"] = gender

                results.append(result)

            logger.info(
                "Face detection completed",
                image_path=image_path,
                faces_found=len(results),
                faces_filtered=filtered_count,
                total_detected=len(faces)
            )
            return results
            
        except Exception as e:
            logger.error("Face detection failed", image_path=image_path, error=str(e))
            raise
    
    def get_face_embedding(self, image_path: str, bbox: List[float]) -> Optional[List[float]]:
        """
        Extract face embedding from a specific bounding box
        
        Args:
            image_path: Path to image file
            bbox: Bounding box [x, y, width, height]
            
        Returns:
            Face embedding vector or None
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return None
            
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            
            # Convert bbox to [x1, y1, x2, y2]
            x1, y1, w, h = bbox
            x2, y2 = x1 + w, y1 + h
            
            # Crop face region
            face_img = img_rgb[y1:y2, x1:x2]
            
            if face_img.size == 0:
                return None
            
            # Get embedding
            faces = self.app.get(face_img)
            if len(faces) > 0:
                return faces[0].normed_embedding.tolist()
            
            return None
            
        except Exception as e:
            logger.error("Failed to extract face embedding", error=str(e))
            return None
