"""
OCR Distorted Text — Router
M5: POST /ocr/distorted
"""
from typing import List, Optional

from fastapi import APIRouter, File, UploadFile, Form

from .models import OcrResult
from .service import ocr_service

router = APIRouter(prefix="/ocr", tags=["OCR - Texto Distorsionado"])


@router.post("/distorted", response_model=OcrResult)
async def ocr_distorted(
    file: UploadFile = File(..., description="Imagen a analizar"),
    preprocessing: Optional[str] = Form(
        "deskew,denoise,contrast",
        description="Pasos de preprocesamiento separados por coma: deskew, denoise, contrast, sharpen, threshold"
    ),
):
    """
    Detecta texto distorsionado en una imagen usando un pipeline de preprocesamiento
    (deskew, denoise, contrast, sharpen, threshold) + Tesseract OCR.
    """
    image_bytes = await file.read()

    steps = [s.strip().lower() for s in preprocessing.split(",") if s.strip()]

    result = ocr_service.detect_text(image_bytes, steps)
    return result
