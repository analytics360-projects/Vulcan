"""
OCR Distorted Text — Models
M5: Texto Distorsionado Post-Aprendizaje
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class OcrTextBlock(BaseModel):
    """A single detected text block with position and confidence."""
    text: str
    confidence: float = Field(ge=0, le=100)
    bbox: dict = Field(default_factory=lambda: {"x": 0, "y": 0, "w": 0, "h": 0})
    angle: float = 0.0


class OcrRequest(BaseModel):
    """Request model for OCR analysis."""
    image_url: Optional[str] = None
    preprocessing: List[str] = Field(
        default_factory=lambda: ["deskew", "denoise", "contrast"],
        description="Preprocessing steps: deskew, denoise, contrast, sharpen, threshold"
    )


class OcrResult(BaseModel):
    """Result of OCR analysis on an image."""
    blocks: List[OcrTextBlock] = Field(default_factory=list)
    full_text: str = ""
    preprocessing_applied: List[str] = Field(default_factory=list)
    processing_time_ms: float = 0.0
    tesseract_available: bool = False
    error: Optional[str] = None
