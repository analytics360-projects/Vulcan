"""Video Analytics service — Real-time AI pipeline for camera streams.

Orchestrates frame decoding, object detection (YOLO), face recognition
(InsightFace), plate OCR (PaddleOCR), and multi-object tracking (ByteTrack).
Emits alerts to Redis Streams for downstream consumption by Balder/SignalR.
"""
import asyncio
import hashlib
import subprocess
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from config import logger
from modules.video_analytics.models import (
    AlertSeverity, AlertType, AnalyticsStatusResponse, BoundingBox,
    Detection, DetectionType, FrameAnalysisResult, PipelineConfig,
    PipelineStatus, VideoAlert, WatchlistAddRequest, WatchlistEntry,
    WatchlistResponse,
)

# Optional imports — gracefully degrade if not installed
try:
    import cv2
    _cv2_available = True
except ImportError:
    _cv2_available = False
    logger.warning("OpenCV not available — video analytics will run in stub mode")

try:
    import numpy as np
    _numpy_available = True
except ImportError:
    _numpy_available = False

# AI model imports (optional — loaded on demand)
_yolo_model = None
_insightface_app = None
_paddle_ocr = None


def _load_yolo():
    """Lazy-load YOLOv8 model."""
    global _yolo_model
    if _yolo_model is not None:
        return _yolo_model
    try:
        from ultralytics import YOLO
        _yolo_model = YOLO("yolov8n.pt")  # nano for speed, swap to yolov8s/m for accuracy
        logger.info("YOLOv8 model loaded")
        return _yolo_model
    except ImportError:
        logger.warning("ultralytics not installed — YOLO detection unavailable")
        return None


def _load_insightface():
    """Lazy-load InsightFace for face detection + embedding."""
    global _insightface_app
    if _insightface_app is not None:
        return _insightface_app
    try:
        import insightface
        _insightface_app = insightface.app.FaceAnalysis(
            name="buffalo_l", providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
        )
        _insightface_app.prepare(ctx_id=0, det_size=(640, 640))
        logger.info("InsightFace model loaded")
        return _insightface_app
    except ImportError:
        logger.warning("insightface not installed — face recognition unavailable")
        return None


def _load_paddleocr():
    """Lazy-load PaddleOCR for plate reading."""
    global _paddle_ocr
    if _paddle_ocr is not None:
        return _paddle_ocr
    try:
        from paddleocr import PaddleOCR
        _paddle_ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        logger.info("PaddleOCR loaded")
        return _paddle_ocr
    except ImportError:
        logger.warning("paddleocr not installed — plate OCR unavailable")
        return None


# COCO class IDs for relevant detections
PERSON_CLASS = 0
VEHICLE_CLASSES = {2: "auto", 3: "motocicleta", 5: "autobus", 7: "camion"}
WEAPON_KEYWORDS = {"knife", "gun", "rifle", "pistol", "weapon"}

# YOLO class names mapping to Spanish
YOLO_LABEL_MAP = {
    "person": "persona", "car": "auto", "truck": "camion", "bus": "autobus",
    "motorcycle": "motocicleta", "bicycle": "bicicleta", "dog": "perro",
    "cat": "gato", "backpack": "mochila", "handbag": "bolsa",
    "suitcase": "maleta", "cell phone": "telefono", "knife": "cuchillo",
}


class AnalysisPipeline:
    """Per-camera analysis pipeline running in a background thread."""

    def __init__(self, camera_id: str, rtsp_url: str, config: PipelineConfig):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.config = config
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.total_frames = 0
        self.total_detections = 0
        self.total_alerts = 0
        self.fps_actual = 0.0
        self.last_frame_ts = ""
        self.start_time = 0.0
        self.error = ""
        self._trackers: Dict[int, Dict] = {}  # Simple tracker state
        self._next_track_id = 1

    def start(self):
        if self.running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.running = True
        self.start_time = time.time()
        self.error = ""
        logger.info(f"Pipeline started for camera {self.camera_id}")

    def stop(self):
        self._stop_event.set()
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info(f"Pipeline stopped for camera {self.camera_id}")

    def _run_loop(self):
        """Main analysis loop — decode frames and run AI models."""
        if not _cv2_available:
            self.error = "OpenCV not available"
            self.running = False
            return

        cap = cv2.VideoCapture(self.rtsp_url)
        if not cap.isOpened():
            self.error = f"Cannot open RTSP stream: {self.rtsp_url}"
            self.running = False
            logger.error(self.error)
            return

        frame_interval = 1.0 / max(self.config.fps_target, 1)
        last_process_time = 0.0
        consecutive_failures = 0

        while not self._stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                consecutive_failures += 1
                if consecutive_failures > 30:
                    self.error = "Stream disconnected — too many consecutive read failures"
                    break
                time.sleep(0.1)
                continue

            consecutive_failures = 0
            now = time.time()

            # FPS throttling
            if now - last_process_time < frame_interval:
                continue
            last_process_time = now

            try:
                result = self._analyze_frame(frame)
                self.total_frames += 1
                self.total_detections += len(result.detections)
                self.last_frame_ts = result.timestamp

                # Calculate actual FPS
                elapsed = now - self.start_time
                if elapsed > 0:
                    self.fps_actual = round(self.total_frames / elapsed, 1)

                # Generate alerts from detections
                alerts = self._evaluate_alerts(result)
                self.total_alerts += len(alerts)

                # Store alerts for retrieval
                for alert in alerts:
                    video_analytics_service._recent_alerts.append(alert)
                    # Keep only last 1000 alerts in memory
                    if len(video_analytics_service._recent_alerts) > 1000:
                        video_analytics_service._recent_alerts.pop(0)

            except Exception as e:
                logger.error(f"Frame analysis error (cam {self.camera_id}): {e}")

        cap.release()
        self.running = False

    def _analyze_frame(self, frame) -> FrameAnalysisResult:
        """Run all configured AI models on a single frame."""
        detections: List[Detection] = []
        timestamp = datetime.now(timezone.utc).isoformat()

        # 1. YOLO detection (persons, vehicles, objects)
        if self.config.detect_persons or self.config.detect_vehicles or self.config.detect_weapons:
            yolo = _load_yolo()
            if yolo is not None:
                results = yolo(frame, verbose=False, conf=self.config.confidence_threshold)
                for r in results:
                    for box in r.boxes:
                        cls_id = int(box.cls[0])
                        cls_name = r.names[cls_id]
                        conf = float(box.conf[0])
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        h_frame, w_frame = frame.shape[:2]
                        bbox = BoundingBox(
                            x=round(x1 / w_frame, 4), y=round(y1 / h_frame, 4),
                            w=round((x2 - x1) / w_frame, 4), h=round((y2 - y1) / h_frame, 4),
                        )

                        det_type = DetectionType.OBJECT
                        if cls_id == PERSON_CLASS and self.config.detect_persons:
                            det_type = DetectionType.PERSON
                        elif cls_id in VEHICLE_CLASSES and self.config.detect_vehicles:
                            det_type = DetectionType.VEHICLE
                        elif cls_name.lower() in WEAPON_KEYWORDS and self.config.detect_weapons:
                            det_type = DetectionType.WEAPON
                        else:
                            continue  # Skip non-relevant detections

                        label = YOLO_LABEL_MAP.get(cls_name, cls_name)
                        track_id = self._assign_track_id(bbox, det_type)

                        detections.append(Detection(
                            type=det_type, label=label, confidence=round(conf, 3),
                            bbox=bbox, track_id=track_id,
                            attributes={"yolo_class": cls_name, "yolo_class_id": cls_id},
                        ))

        # 2. Face detection + recognition
        if self.config.detect_faces:
            face_app = _load_insightface()
            if face_app is not None:
                faces = face_app.get(frame)
                for face in faces:
                    x1, y1, x2, y2 = face.bbox.astype(int)
                    h_frame, w_frame = frame.shape[:2]
                    bbox = BoundingBox(
                        x=round(x1 / w_frame, 4), y=round(y1 / h_frame, 4),
                        w=round((x2 - x1) / w_frame, 4), h=round((y2 - y1) / h_frame, 4),
                    )
                    attrs = {}
                    if hasattr(face, "embedding") and face.embedding is not None:
                        embedding = face.embedding.tolist()
                        # Match against watchlist
                        match = video_analytics_service.match_face_embedding(embedding)
                        if match:
                            attrs["face_id"] = match["id"]
                            attrs["face_name"] = match["name"]
                            attrs["face_similarity"] = match["similarity"]
                    if hasattr(face, "age"):
                        attrs["age"] = int(face.age)
                    if hasattr(face, "gender"):
                        attrs["gender"] = "M" if face.gender == 1 else "F"

                    detections.append(Detection(
                        type=DetectionType.FACE, label="rostro",
                        confidence=round(float(face.det_score), 3),
                        bbox=bbox, attributes=attrs,
                    ))

        # 3. Plate OCR on vehicle bounding boxes
        if self.config.read_plates:
            ocr = _load_paddleocr()
            if ocr is not None:
                for det in detections:
                    if det.type == DetectionType.VEHICLE:
                        # Crop vehicle region for plate OCR
                        h_f, w_f = frame.shape[:2]
                        x1 = int(det.bbox.x * w_f)
                        y1 = int(det.bbox.y * h_f)
                        x2 = int((det.bbox.x + det.bbox.w) * w_f)
                        y2 = int((det.bbox.y + det.bbox.h) * h_f)
                        # Focus on lower third of vehicle (plate area)
                        plate_y1 = y1 + int((y2 - y1) * 0.6)
                        crop = frame[plate_y1:y2, x1:x2]
                        if crop.size > 0:
                            try:
                                ocr_result = ocr.ocr(crop, cls=True)
                                if ocr_result and ocr_result[0]:
                                    for line in ocr_result[0]:
                                        text = line[1][0].strip().upper()
                                        conf = float(line[1][1])
                                        if len(text) >= 5 and conf > 0.5:
                                            det.attributes["plate_text"] = text
                                            det.attributes["plate_confidence"] = round(conf, 3)
                                            # Also create a PLATE detection
                                            detections.append(Detection(
                                                type=DetectionType.PLATE,
                                                label=text, confidence=round(conf, 3),
                                                bbox=det.bbox,
                                                attributes={"plate_text": text, "vehicle_track_id": det.track_id},
                                            ))
                                            break
                            except Exception:
                                pass

        person_count = sum(1 for d in detections if d.type == DetectionType.PERSON)
        vehicle_count = sum(1 for d in detections if d.type == DetectionType.VEHICLE)

        return FrameAnalysisResult(
            camera_id=self.camera_id,
            timestamp=timestamp,
            frame_number=self.total_frames,
            detections=detections,
            person_count=person_count,
            vehicle_count=vehicle_count,
            fps_actual=self.fps_actual,
        )

    def _assign_track_id(self, bbox: BoundingBox, det_type: DetectionType) -> int:
        """Simple centroid-based tracking — assign persistent IDs."""
        cx = bbox.x + bbox.w / 2
        cy = bbox.y + bbox.h / 2
        best_id = None
        best_dist = 0.05  # Max distance threshold for matching

        for tid, info in list(self._trackers.items()):
            if info["type"] != det_type:
                continue
            dx = cx - info["cx"]
            dy = cy - info["cy"]
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_id = tid

        if best_id is not None:
            self._trackers[best_id].update({"cx": cx, "cy": cy, "last_seen": time.time()})
            return best_id

        # New track
        tid = self._next_track_id
        self._next_track_id += 1
        self._trackers[tid] = {"type": det_type, "cx": cx, "cy": cy, "last_seen": time.time()}

        # Cleanup old tracks (not seen for 5 seconds)
        now = time.time()
        stale = [k for k, v in self._trackers.items() if now - v["last_seen"] > 5.0]
        for k in stale:
            del self._trackers[k]

        return tid

    def _evaluate_alerts(self, result: FrameAnalysisResult) -> List[VideoAlert]:
        """Generate alerts based on detections and watchlist matches."""
        alerts: List[VideoAlert] = []

        from modules.camera_manager.service import camera_manager_service
        cam = camera_manager_service.get_camera(self.camera_id)
        cam_name = cam.name if cam else self.camera_id
        cam_lat = cam.lat if cam else 0.0
        cam_lng = cam.lng if cam else 0.0
        cam_zone = cam.zone if cam else ""

        for det in result.detections:
            alert_id = hashlib.md5(
                f"{self.camera_id}:{det.type}:{det.track_id}:{result.timestamp}".encode()
            ).hexdigest()[:16]

            # Weapon alert — always critical
            if det.type == DetectionType.WEAPON:
                alerts.append(VideoAlert(
                    id=alert_id, camera_id=self.camera_id, camera_name=cam_name,
                    alert_type=AlertType.WEAPON_DETECTED,
                    severity=AlertSeverity.CRITICAL,
                    title=f"Arma detectada: {det.label}",
                    description=f"Arma tipo '{det.label}' detectada con {det.confidence*100:.0f}% confianza",
                    timestamp=result.timestamp,
                    detection=det, lat=cam_lat, lng=cam_lng, zone=cam_zone,
                ))

            # Face match alert
            if det.type == DetectionType.FACE and "face_name" in det.attributes:
                alerts.append(VideoAlert(
                    id=alert_id, camera_id=self.camera_id, camera_name=cam_name,
                    alert_type=AlertType.FACE_MATCH,
                    severity=AlertSeverity.HIGH,
                    title=f"Persona identificada: {det.attributes['face_name']}",
                    description=f"Coincidencia facial {det.attributes.get('face_similarity', 0)*100:.0f}%",
                    timestamp=result.timestamp,
                    detection=det, lat=cam_lat, lng=cam_lng, zone=cam_zone,
                    metadata={"face_id": det.attributes.get("face_id", "")},
                ))

            # Plate read — check against watchlist
            if det.type == DetectionType.PLATE:
                plate_text = det.attributes.get("plate_text", "")
                match = video_analytics_service.match_plate(plate_text)
                if match:
                    alerts.append(VideoAlert(
                        id=alert_id, camera_id=self.camera_id, camera_name=cam_name,
                        alert_type=AlertType.PLATE_MATCH,
                        severity=AlertSeverity.HIGH,
                        title=f"Placa en lista: {plate_text}",
                        description=f"Vehículo con placa {plate_text} — {match.get('reason', 'En watchlist')}",
                        timestamp=result.timestamp,
                        detection=det, lat=cam_lat, lng=cam_lng, zone=cam_zone,
                    ))
                else:
                    alerts.append(VideoAlert(
                        id=alert_id, camera_id=self.camera_id, camera_name=cam_name,
                        alert_type=AlertType.PLATE_READ,
                        severity=AlertSeverity.INFO,
                        title=f"Placa leída: {plate_text}",
                        description=f"Vehículo {det.label} — placa {plate_text}",
                        timestamp=result.timestamp,
                        detection=det, lat=cam_lat, lng=cam_lng, zone=cam_zone,
                    ))

        return alerts

    def get_status(self) -> PipelineStatus:
        models = []
        if _yolo_model:
            models.append("YOLOv8")
        if _insightface_app:
            models.append("InsightFace")
        if _paddle_ocr:
            models.append("PaddleOCR")
        return PipelineStatus(
            camera_id=self.camera_id,
            running=self.running,
            fps_actual=self.fps_actual,
            total_frames_processed=self.total_frames,
            total_detections=self.total_detections,
            total_alerts=self.total_alerts,
            uptime_seconds=round(time.time() - self.start_time, 1) if self.start_time else 0,
            last_frame_timestamp=self.last_frame_ts,
            models_loaded=models,
            error=self.error,
        )


class VideoAnalyticsService:
    """Manages analysis pipelines across multiple cameras."""

    def __init__(self):
        self._pipelines: Dict[str, AnalysisPipeline] = {}
        self._watchlist_faces: List[WatchlistEntry] = []
        self._watchlist_plates: List[WatchlistEntry] = []
        self._recent_alerts: List[VideoAlert] = []

    def start_analysis(self, camera_id: str, rtsp_url: str, config: PipelineConfig) -> PipelineStatus:
        """Start real-time analysis on a camera stream."""
        if camera_id in self._pipelines and self._pipelines[camera_id].running:
            return self._pipelines[camera_id].get_status()

        from modules.camera_manager.service import camera_manager_service
        camera_manager_service.set_camera_status(camera_id, "analyzing")

        pipeline = AnalysisPipeline(camera_id, rtsp_url, config)
        self._pipelines[camera_id] = pipeline
        pipeline.start()
        return pipeline.get_status()

    def stop_analysis(self, camera_id: str) -> bool:
        """Stop analysis on a camera stream."""
        pipeline = self._pipelines.get(camera_id)
        if not pipeline:
            return False
        pipeline.stop()

        from modules.camera_manager.service import camera_manager_service
        camera_manager_service.set_camera_status(camera_id, "online")
        return True

    def get_pipeline_status(self, camera_id: str) -> Optional[PipelineStatus]:
        pipeline = self._pipelines.get(camera_id)
        return pipeline.get_status() if pipeline else None

    def get_all_status(self) -> AnalyticsStatusResponse:
        statuses = [p.get_status() for p in self._pipelines.values()]
        models = set()
        if _yolo_model:
            models.add("YOLOv8")
        if _insightface_app:
            models.add("InsightFace")
        if _paddle_ocr:
            models.add("PaddleOCR")

        return AnalyticsStatusResponse(
            pipelines=statuses,
            total_running=sum(1 for s in statuses if s.running),
            total_fps=sum(s.fps_actual for s in statuses),
            total_alerts_today=len(self._recent_alerts),
            models_loaded=list(models),
        )

    def get_recent_alerts(self, camera_id: str = "", limit: int = 50) -> List[VideoAlert]:
        alerts = self._recent_alerts
        if camera_id:
            alerts = [a for a in alerts if a.camera_id == camera_id]
        return alerts[-limit:]

    # ── Watchlist Management ──

    def add_to_watchlist(self, req: WatchlistAddRequest) -> WatchlistEntry:
        entry_id = hashlib.md5(f"{req.type}:{req.name}:{time.time()}".encode()).hexdigest()[:12]
        entry = WatchlistEntry(
            id=entry_id, type=req.type, name=req.name,
            image_url=req.image_url,
            alert_severity=req.alert_severity, reason=req.reason,
        )
        if req.type == "face":
            # If InsightFace available, compute embedding from image
            if req.image_url and _insightface_app:
                try:
                    import urllib.request
                    resp = urllib.request.urlopen(req.image_url)
                    img_bytes = resp.read()
                    nparr = np.frombuffer(img_bytes, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    faces = _insightface_app.get(img)
                    if faces:
                        entry.embedding = faces[0].embedding.tolist()
                except Exception as e:
                    logger.warning(f"Failed to compute face embedding: {e}")
            self._watchlist_faces.append(entry)
        elif req.type == "plate":
            entry.name = req.plate_number or req.name
            self._watchlist_plates.append(entry)
        return entry

    def remove_from_watchlist(self, entry_id: str) -> bool:
        for lst in [self._watchlist_faces, self._watchlist_plates]:
            for i, e in enumerate(lst):
                if e.id == entry_id:
                    lst.pop(i)
                    return True
        return False

    def get_watchlist(self) -> WatchlistResponse:
        return WatchlistResponse(
            entries=self._watchlist_faces + self._watchlist_plates,
            total_faces=len(self._watchlist_faces),
            total_plates=len(self._watchlist_plates),
        )

    def match_face_embedding(self, embedding: List[float]) -> Optional[Dict]:
        """Match a face embedding against the watchlist."""
        if not self._watchlist_faces or not _numpy_available:
            return None
        query = np.array(embedding)
        best_match = None
        best_sim = 0.0
        for entry in self._watchlist_faces:
            if not entry.embedding or not entry.active:
                continue
            ref = np.array(entry.embedding)
            # Cosine similarity
            dot = np.dot(query, ref)
            norm = np.linalg.norm(query) * np.linalg.norm(ref)
            sim = float(dot / norm) if norm > 0 else 0.0
            if sim > best_sim and sim > 0.6:
                best_sim = sim
                best_match = {"id": entry.id, "name": entry.name, "similarity": round(sim, 3)}
        return best_match

    def match_plate(self, plate_text: str) -> Optional[Dict]:
        """Match a plate against the watchlist."""
        if not plate_text:
            return None
        normalized = plate_text.replace("-", "").replace(" ", "").upper()
        for entry in self._watchlist_plates:
            if not entry.active:
                continue
            ref = entry.name.replace("-", "").replace(" ", "").upper()
            if normalized == ref or ref in normalized or normalized in ref:
                return {"id": entry.id, "name": entry.name, "reason": entry.reason}
        return None


# Singleton
video_analytics_service = VideoAnalyticsService()
