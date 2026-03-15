"""
OCR Distorted Text — Service
M5: Preprocessing pipeline (deskew, denoise, contrast, sharpen, threshold)
     + Tesseract OCR (optional)
"""
import io
import time
import math
from typing import List

from PIL import Image, ImageFilter, ImageOps, ImageEnhance
import numpy as np

from config import logger
from .models import OcrTextBlock, OcrResult

# Try to import pytesseract — optional dependency
_tesseract_available = False
try:
    import pytesseract
    # Quick check: will raise if tesseract binary not found
    pytesseract.get_tesseract_version()
    _tesseract_available = True
    logger.info("Tesseract OCR available")
except Exception:
    logger.warning("pytesseract not available — OCR will return stub results. Install tesseract-ocr and pytesseract for full functionality.")


VALID_STEPS = {"deskew", "denoise", "contrast", "sharpen", "threshold"}


class OcrService:
    """Distorted text detection with preprocessing pipeline."""

    @staticmethod
    def preprocess_image(image_bytes: bytes, steps: List[str]) -> tuple[bytes, List[str]]:
        """
        Apply preprocessing steps to an image.
        Returns (processed_bytes, applied_steps).
        """
        img = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if necessary (RGBA, palette, etc.)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        applied = []

        for step in steps:
            if step not in VALID_STEPS:
                continue
            try:
                if step == "deskew":
                    img = OcrService._deskew(img)
                    applied.append("deskew")
                elif step == "denoise":
                    img = img.filter(ImageFilter.MedianFilter(size=3))
                    applied.append("denoise")
                elif step == "contrast":
                    img = ImageOps.autocontrast(img)
                    img = ImageOps.equalize(img.convert("L")).convert("RGB") if img.mode == "RGB" else ImageOps.equalize(img)
                    applied.append("contrast")
                elif step == "sharpen":
                    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
                    applied.append("sharpen")
                elif step == "threshold":
                    gray = img.convert("L")
                    img = OcrService._adaptive_threshold(gray)
                    applied.append("threshold")
            except Exception as e:
                logger.warning(f"Preprocessing step '{step}' failed: {e}")

        buf = io.BytesIO()
        out_format = "PNG"
        img.save(buf, format=out_format)
        return buf.getvalue(), applied

    @staticmethod
    def _deskew(img: Image.Image) -> Image.Image:
        """Simple deskew: detect dominant angle via projection profile and rotate."""
        try:
            gray = np.array(img.convert("L"))
            # Threshold to binary
            threshold = np.mean(gray)
            binary = (gray < threshold).astype(np.uint8)

            # Try angles from -15 to +15 degrees
            best_angle = 0
            best_score = 0
            for angle_deg in np.arange(-15, 15.5, 0.5):
                rotated = OcrService._rotate_array(binary, angle_deg)
                # Score = max variance of row sums (text lines produce sharp peaks)
                row_sums = np.sum(rotated, axis=1)
                score = np.var(row_sums)
                if score > best_score:
                    best_score = score
                    best_angle = angle_deg

            if abs(best_angle) > 0.5:
                img = img.rotate(best_angle, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255) if img.mode == "RGB" else 255)
                logger.info(f"Deskew: rotated {best_angle:.1f} degrees")
            return img
        except Exception as e:
            logger.warning(f"Deskew failed, returning original: {e}")
            return img

    @staticmethod
    def _rotate_array(arr: np.ndarray, angle_deg: float) -> np.ndarray:
        """Rotate a 2D binary array by angle (simple PIL-based)."""
        img_tmp = Image.fromarray((arr * 255).astype(np.uint8))
        rotated = img_tmp.rotate(angle_deg, resample=Image.NEAREST, expand=False)
        return np.array(rotated) > 127

    @staticmethod
    def _adaptive_threshold(gray_img: Image.Image, block_size: int = 31) -> Image.Image:
        """Adaptive threshold using local mean — pure Pillow/numpy."""
        arr = np.array(gray_img).astype(np.float32)
        # Use box blur as local mean approximation
        blurred = gray_img.filter(ImageFilter.BoxBlur(block_size // 2))
        local_mean = np.array(blurred).astype(np.float32)
        binary = ((arr < local_mean - 10) * 255).astype(np.uint8)
        return Image.fromarray(binary, mode="L")

    @staticmethod
    def detect_text(image_bytes: bytes, preprocessing_steps: List[str]) -> OcrResult:
        """
        Main OCR pipeline:
        1. Preprocess image
        2. Run Tesseract OCR (or return stub if unavailable)
        3. Return structured result
        """
        start = time.perf_counter()

        # Filter valid steps
        valid_steps = [s for s in preprocessing_steps if s in VALID_STEPS]

        # Preprocess
        if valid_steps:
            processed_bytes, applied_steps = OcrService.preprocess_image(image_bytes, valid_steps)
        else:
            processed_bytes = image_bytes
            applied_steps = []

        if _tesseract_available:
            result = OcrService._run_tesseract(processed_bytes, applied_steps)
        else:
            result = OcrResult(
                blocks=[],
                full_text="",
                preprocessing_applied=applied_steps,
                tesseract_available=False,
                error="Tesseract OCR no esta instalado. Instale tesseract-ocr y pytesseract para habilitar OCR completo. El preprocesamiento se aplico correctamente."
            )

        result.processing_time_ms = (time.perf_counter() - start) * 1000.0
        return result

    @staticmethod
    def _run_tesseract(image_bytes: bytes, applied_steps: List[str]) -> OcrResult:
        """Run Tesseract OCR and extract text blocks with bounding boxes."""
        try:
            img = Image.open(io.BytesIO(image_bytes))

            # Get detailed data with bounding boxes
            data = pytesseract.image_to_data(img, lang="spa+eng", output_type=pytesseract.Output.DICT)

            blocks: List[OcrTextBlock] = []
            full_texts = []
            img_w, img_h = img.size

            n_items = len(data["text"])
            for i in range(n_items):
                text = data["text"][i].strip()
                conf = float(data["conf"][i]) if data["conf"][i] != "-1" else 0.0
                if not text or conf < 1:
                    continue

                x = data["left"][i]
                y = data["top"][i]
                w = data["width"][i]
                h = data["height"][i]

                blocks.append(OcrTextBlock(
                    text=text,
                    confidence=conf,
                    bbox={
                        "x": round(x / img_w, 4) if img_w else 0,
                        "y": round(y / img_h, 4) if img_h else 0,
                        "w": round(w / img_w, 4) if img_w else 0,
                        "h": round(h / img_h, 4) if img_h else 0,
                    },
                    angle=0.0
                ))
                full_texts.append(text)

            return OcrResult(
                blocks=blocks,
                full_text=" ".join(full_texts),
                preprocessing_applied=applied_steps,
                tesseract_available=True,
            )
        except Exception as e:
            logger.error(f"Tesseract OCR error: {e}")
            return OcrResult(
                blocks=[],
                full_text="",
                preprocessing_applied=applied_steps,
                tesseract_available=True,
                error=f"Error ejecutando Tesseract: {str(e)}"
            )


# Singleton
ocr_service = OcrService()
