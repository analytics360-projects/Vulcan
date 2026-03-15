"""Camera Manager models — ONVIF, Milestone, Sense integration."""
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class CameraSourceType(str, Enum):
    ONVIF = "onvif"
    MILESTONE = "milestone"
    SENSE = "sense"
    RTSP_DIRECT = "rtsp_direct"


class CameraStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    ANALYZING = "analyzing"
    ERROR = "error"
    CONNECTING = "connecting"


class AnalysisPriority(str, Enum):
    CRITICAL = "critical"      # 15 FPS, all models
    HIGH = "high"              # 10 FPS, YOLO + Face
    MEDIUM = "medium"          # 5 FPS, YOLO only
    LOW = "low"                # 2 FPS, motion-triggered
    DISABLED = "disabled"      # No analysis


# ── Camera Source Registration ──

class OnvifCredentials(BaseModel):
    host: str
    port: int = 80
    username: str = "admin"
    password: str = ""


class MilestoneConfig(BaseModel):
    server_url: str                     # https://milestone-server
    username: str = ""
    password: str = ""
    api_token: str = ""                 # Alternative auth


class SenseConfig(BaseModel):
    server_url: str                     # https://sense-server
    username: str = ""
    password: str = ""
    api_token: str = ""


class CameraSource(BaseModel):
    id: str = ""
    name: str
    source_type: CameraSourceType
    rtsp_url: str = ""                  # Direct RTSP or resolved from VMS/ONVIF
    location: str = ""                  # Human-readable location
    lat: float = 0.0
    lng: float = 0.0
    subcentro_id: Optional[int] = None
    zone: str = ""                      # Zone/sector name
    priority: AnalysisPriority = AnalysisPriority.MEDIUM
    onvif: Optional[OnvifCredentials] = None
    milestone_camera_guid: str = ""     # GUID from Milestone
    sense_camera_id: str = ""           # ID from Sense Symphony
    ptz_capable: bool = False
    status: CameraStatus = CameraStatus.OFFLINE
    analysis_config: Dict[str, Any] = Field(default_factory=lambda: {
        "detect_persons": True,
        "detect_vehicles": True,
        "detect_weapons": True,
        "detect_faces": True,
        "read_plates": True,
        "track_objects": True,
        "zones": [],                    # ROI zones for crossing detection
        "fps_target": 5,
    })
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CameraAddRequest(BaseModel):
    name: str
    source_type: CameraSourceType
    rtsp_url: str = ""
    location: str = ""
    lat: float = 0.0
    lng: float = 0.0
    subcentro_id: Optional[int] = None
    zone: str = ""
    priority: AnalysisPriority = AnalysisPriority.MEDIUM
    onvif: Optional[OnvifCredentials] = None
    milestone_camera_guid: str = ""
    sense_camera_id: str = ""
    analysis_config: Dict[str, Any] = Field(default_factory=dict)


class CameraUpdateRequest(BaseModel):
    name: Optional[str] = None
    priority: Optional[AnalysisPriority] = None
    analysis_config: Optional[Dict[str, Any]] = None
    location: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    zone: Optional[str] = None


# ── ONVIF Discovery ──

class OnvifDiscoveryRequest(BaseModel):
    subnet: str = ""                    # e.g., "192.168.1.0/24", empty = broadcast
    timeout_seconds: int = 5
    username: str = "admin"
    password: str = ""


class DiscoveredCamera(BaseModel):
    host: str
    port: int
    manufacturer: str = ""
    model: str = ""
    firmware: str = ""
    serial: str = ""
    rtsp_url: str = ""
    profiles: List[str] = []           # Profile S, T, G, M
    ptz_capable: bool = False
    resolution: str = ""               # e.g., "1920x1080"


class OnvifDiscoveryResponse(BaseModel):
    cameras: List[DiscoveredCamera]
    total_found: int
    scan_duration_ms: int


# ── VMS Integration ──

class VMSCameraInfo(BaseModel):
    vms_id: str                         # GUID or ID from VMS
    name: str
    rtsp_url: str
    recording: bool = False
    enabled: bool = True
    hardware_model: str = ""
    location: str = ""
    groups: List[str] = []              # Camera groups in VMS


class VMSSyncRequest(BaseModel):
    source_type: CameraSourceType       # milestone or sense
    server_url: str
    username: str = ""
    password: str = ""
    api_token: str = ""
    auto_add: bool = False              # Auto-register discovered cameras


class VMSSyncResponse(BaseModel):
    cameras: List[VMSCameraInfo]
    total_in_vms: int
    already_registered: int
    newly_added: int


# ── PTZ Control ──

class PTZAction(str, Enum):
    MOVE = "move"
    STOP = "stop"
    PRESET = "preset"
    HOME = "home"
    ZOOM = "zoom"


class PTZCommand(BaseModel):
    camera_id: str
    action: PTZAction
    pan: float = 0.0                    # -1.0 to 1.0 (left to right)
    tilt: float = 0.0                   # -1.0 to 1.0 (down to up)
    zoom: float = 0.0                   # -1.0 to 1.0 (out to in)
    preset_name: str = ""               # For preset action
    speed: float = 0.5                  # 0.0 to 1.0


class PTZPreset(BaseModel):
    name: str
    token: str
    pan: float = 0.0
    tilt: float = 0.0
    zoom: float = 0.0


class PTZResponse(BaseModel):
    success: bool
    message: str = ""
    presets: List[PTZPreset] = []


# ── Camera Status ──

class CameraStatusResponse(BaseModel):
    cameras: List[CameraSource]
    total: int
    online: int
    analyzing: int
    offline: int
    error: int
