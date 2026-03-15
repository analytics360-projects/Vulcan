"""Video Analytics models — Real-time detection, tracking, alerts."""
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class DetectionType(str, Enum):
    PERSON = "person"
    VEHICLE = "vehicle"
    WEAPON = "weapon"
    FACE = "face"
    PLATE = "plate"
    OBJECT = "object"


class AlertSeverity(str, Enum):
    CRITICAL = "critical"   # Weapon detected, wanted person
    HIGH = "high"           # Unknown face in restricted zone
    MEDIUM = "medium"       # Zone crossing, plate read
    LOW = "low"             # Person count, vehicle count
    INFO = "info"           # General detection


class AlertType(str, Enum):
    WEAPON_DETECTED = "weapon_detected"
    FACE_MATCH = "face_match"
    PLATE_MATCH = "plate_match"
    PLATE_READ = "plate_read"
    ZONE_CROSSING = "zone_crossing"
    INTRUSION = "intrusion"
    CROWD_DETECTED = "crowd_detected"
    LOITERING = "loitering"
    VEHICLE_STOPPED = "vehicle_stopped"
    PERSON_COUNT = "person_count"
    VEHICLE_COUNT = "vehicle_count"


# ── Detection Results ──

class BoundingBox(BaseModel):
    x: float                    # Normalized 0-1
    y: float
    w: float
    h: float


class Detection(BaseModel):
    type: DetectionType
    label: str                  # e.g., "persona", "auto", "pistola"
    confidence: float
    bbox: BoundingBox
    track_id: int = 0           # Persistent tracking ID
    attributes: Dict[str, Any] = Field(default_factory=dict)
    # Attributes can include:
    # - color (for vehicles)
    # - plate_text, plate_confidence (for plates)
    # - face_id, face_name, face_similarity (for face matches)
    # - weapon_type (for weapons)


class FrameAnalysisResult(BaseModel):
    camera_id: str
    timestamp: str              # ISO 8601
    frame_number: int = 0
    detections: List[Detection] = []
    person_count: int = 0
    vehicle_count: int = 0
    fps_actual: float = 0.0


# ── Alerts ──

class VideoAlert(BaseModel):
    id: str = ""
    camera_id: str
    camera_name: str = ""
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    description: str
    timestamp: str
    detection: Optional[Detection] = None
    snapshot_url: str = ""      # URL to frame capture
    lat: float = 0.0
    lng: float = 0.0
    zone: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    acknowledged: bool = False


# ── Analysis Pipeline Config ──

class AnalysisZone(BaseModel):
    """Region of Interest for zone-based detection."""
    name: str
    type: str = "polygon"       # polygon, line, rectangle
    points: List[Dict[str, float]] = []  # [{"x": 0.1, "y": 0.2}, ...]
    triggers: List[str] = []    # ["crossing", "intrusion", "loitering"]
    direction: str = ""         # "in", "out", "both" (for line crossing)


class WatchlistEntry(BaseModel):
    """Person or plate to watch for."""
    id: str
    type: str                   # "face" or "plate"
    name: str                   # Person name or plate number
    embedding: List[float] = [] # Face embedding vector (512d)
    image_url: str = ""
    alert_severity: AlertSeverity = AlertSeverity.HIGH
    reason: str = ""            # Why this person/plate is watched
    active: bool = True


class PipelineConfig(BaseModel):
    camera_id: str
    detect_persons: bool = True
    detect_vehicles: bool = True
    detect_weapons: bool = True
    detect_faces: bool = True
    read_plates: bool = True
    track_objects: bool = True
    fps_target: int = 5
    confidence_threshold: float = 0.5
    face_match_threshold: float = 0.6
    zones: List[AnalysisZone] = []
    motion_trigger_only: bool = False   # Only analyze when motion detected


# ── Pipeline Control ──

class StartAnalysisRequest(BaseModel):
    camera_id: str
    config: Optional[PipelineConfig] = None


class StopAnalysisRequest(BaseModel):
    camera_id: str


class PipelineStatus(BaseModel):
    camera_id: str
    running: bool
    fps_actual: float = 0.0
    total_frames_processed: int = 0
    total_detections: int = 0
    total_alerts: int = 0
    uptime_seconds: float = 0.0
    last_frame_timestamp: str = ""
    models_loaded: List[str] = []
    error: str = ""


class AnalyticsStatusResponse(BaseModel):
    pipelines: List[PipelineStatus]
    total_running: int
    total_fps: float
    total_alerts_today: int
    gpu_utilization: float = 0.0
    models_loaded: List[str] = []


# ── Watchlist ──

class WatchlistAddRequest(BaseModel):
    type: str                   # "face" or "plate"
    name: str
    image_url: str = ""         # For face — will compute embedding
    plate_number: str = ""      # For plate
    reason: str = ""
    alert_severity: AlertSeverity = AlertSeverity.HIGH


class WatchlistResponse(BaseModel):
    entries: List[WatchlistEntry]
    total_faces: int
    total_plates: int


# ── Historical Search ──

class VideoSearchRequest(BaseModel):
    """Search recorded analysis results."""
    camera_ids: List[str] = []
    detection_type: Optional[DetectionType] = None
    plate_text: str = ""
    face_name: str = ""
    fecha_inicio: str = ""
    fecha_fin: str = ""
    zone: str = ""
    min_confidence: float = 0.5
    limit: int = 50


class VideoSearchResult(BaseModel):
    camera_id: str
    camera_name: str
    timestamp: str
    detection: Detection
    snapshot_url: str = ""


class VideoSearchResponse(BaseModel):
    results: List[VideoSearchResult]
    total: int
