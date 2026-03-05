"""
Pydantic models for analysis requests and responses
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class AnalysisStatus(str, Enum):
    """Analysis job status"""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PhotoUploadRequest(BaseModel):
    """Request model for photo upload with metadata"""
    folio_id: Optional[str] = Field(None, description="Folio ID if linked to a case")
    subcenter: Optional[str] = Field(None, description="Subcenter name")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    description: Optional[str] = Field(None, description="Description or context of the photo")


class FaceDetectionResult(BaseModel):
    """Face detection result"""
    face_id: str
    bbox: List[float] = Field(description="Bounding box [x, y, width, height]")
    confidence: float = Field(description="Face detection confidence (0.0-1.0)")
    embedding: Optional[List[float]] = Field(None, description="Face embedding vector for recognition")
    age: Optional[int] = Field(None, description="Estimated age (approximate, may be inaccurate)")
    gender: Optional[str] = Field(None, description="Estimated gender: 'male' or 'female' (approximate, may be inaccurate)")


class EntityExtractionResult(BaseModel):
    """Entity extraction result"""
    entity_type: str = Field(description="Type: Person, Vehicle, Weapon, Phone, Address, Alias")
    value: str = Field(description="Extracted value")
    confidence: float
    context: Optional[str] = Field(None, description="Context where entity was found")


class AnalysisResult(BaseModel):
    """Complete analysis result"""
    analysis_id: str
    photo_id: str
    status: AnalysisStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    # Face detection results
    faces_detected: List[FaceDetectionResult] = Field(default_factory=list)
    face_count: int = 0
    
    # Entity extraction results
    entities: List[EntityExtractionResult] = Field(default_factory=list)
    
    # Graph associations (if any matches found)
    graph_associations: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Error information
    error: Optional[str] = None


class AnalysisJobResponse(BaseModel):
    """Response for analysis job creation"""
    job_id: str
    status: AnalysisStatus
    message: str
    photo_id: str


class AnalysisStatusResponse(BaseModel):
    """Response for analysis status check"""
    job_id: str
    status: AnalysisStatus
    result: Optional[AnalysisResult] = None
    progress: Optional[float] = Field(None, ge=0, le=100, description="Progress percentage")
    error: Optional[str] = None
