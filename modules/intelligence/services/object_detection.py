"""
Object detection service using YOLOv8
"""
import structlog
from typing import List, Dict, Any
from pathlib import Path
import numpy as np

logger = structlog.get_logger()


# Spanish translations for COCO classes
COCO_SPANISH = {
    "person": "persona",
    "bicycle": "bicicleta",
    "car": "carro",
    "motorcycle": "motocicleta",
    "airplane": "avión",
    "bus": "autobús",
    "train": "tren",
    "truck": "camión",
    "boat": "bote",
    "traffic light": "semáforo",
    "fire hydrant": "hidrante",
    "stop sign": "señal de alto",
    "parking meter": "parquímetro",
    "bench": "banca",
    "bird": "pájaro",
    "cat": "gato",
    "dog": "perro",
    "horse": "caballo",
    "sheep": "oveja",
    "cow": "vaca",
    "elephant": "elefante",
    "bear": "oso",
    "zebra": "cebra",
    "giraffe": "jirafa",
    "backpack": "mochila",
    "umbrella": "paraguas",
    "handbag": "bolsa",
    "tie": "corbata",
    "suitcase": "maleta",
    "frisbee": "frisbee",
    "skis": "esquís",
    "snowboard": "tabla de nieve",
    "sports ball": "pelota",
    "kite": "cometa",
    "baseball bat": "bat de béisbol",
    "baseball glove": "guante de béisbol",
    "skateboard": "patineta",
    "surfboard": "tabla de surf",
    "tennis racket": "raqueta de tenis",
    "bottle": "botella",
    "wine glass": "copa de vino",
    "cup": "taza",
    "fork": "tenedor",
    "knife": "cuchillo",
    "spoon": "cuchara",
    "bowl": "tazón",
    "banana": "plátano",
    "apple": "manzana",
    "sandwich": "sándwich",
    "orange": "naranja",
    "broccoli": "brócoli",
    "carrot": "zanahoria",
    "hot dog": "hot dog",
    "pizza": "pizza",
    "donut": "dona",
    "cake": "pastel",
    "chair": "silla",
    "couch": "sofá",
    "potted plant": "planta",
    "bed": "cama",
    "dining table": "mesa",
    "toilet": "inodoro",
    "tv": "televisión",
    "laptop": "laptop",
    "mouse": "ratón",
    "remote": "control remoto",
    "keyboard": "teclado",
    "cell phone": "celular",
    "microwave": "microondas",
    "oven": "horno",
    "toaster": "tostadora",
    "sink": "lavabo",
    "refrigerator": "refrigerador",
    "book": "libro",
    "clock": "reloj",
    "vase": "florero",
    "scissors": "tijeras",
    "teddy bear": "oso de peluche",
    "hair drier": "secadora",
    "toothbrush": "cepillo de dientes",
}


# Object categories for investigation context (Spanish)
INVESTIGATION_CATEGORIES = {
    "armas": ["knife", "scissors", "baseball bat"],
    "vehículos": ["car", "motorcycle", "bicycle", "truck", "bus", "boat"],
    "electrónicos": ["cell phone", "laptop", "tv", "remote", "keyboard", "mouse"],
    "documentos": ["book"],
    "contenedores": ["backpack", "handbag", "suitcase", "bottle", "bag"],
    "herramientas": ["scissors", "knife"],
    "mobiliario": ["chair", "couch", "bed", "dining table"],
}


class ObjectDetectionService:
    """Service for detecting objects in images using YOLOv8"""

    def __init__(self, model_name: str = "yolov8n.pt", confidence_threshold: float = 0.5):
        """
        Initialize YOLOv8 object detection service

        Args:
            model_name: YOLOv8 model variant (yolov8n, yolov8s, yolov8m, yolov8l, yolov8x)
                       n=nano (fastest), s=small, m=medium, l=large, x=extra-large (most accurate)
            confidence_threshold: Minimum confidence for detections (0.0-1.0)
        """
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self.model = None
        self.initialized = False

        try:
            from ultralytics import YOLO
            logger.info("Initializing YOLOv8 object detection", model=model_name)
            self.model = YOLO(model_name)
            self.initialized = True
            logger.info("YOLOv8 initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize YOLOv8", error=str(e))
            self.initialized = False

    def detect_objects(
        self,
        image_path: str,
        confidence_threshold: float = None,
        include_bbox: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Detect objects in an image

        Args:
            image_path: Path to image file
            confidence_threshold: Override default confidence threshold
            include_bbox: Include bounding box coordinates

        Returns:
            List of detected objects with:
            - object_type: English label
            - object_type_es: Spanish label
            - category: Investigation category (Spanish)
            - confidence: Detection confidence (0.0-1.0)
            - bbox: Bounding box [x1, y1, x2, y2] (optional)
        """
        if not self.initialized:
            logger.error("Object detection service not initialized")
            return []

        if confidence_threshold is None:
            confidence_threshold = self.confidence_threshold

        try:
            # Run inference
            results = self.model(image_path, conf=confidence_threshold, verbose=False)

            detected_objects = []

            for result in results:
                boxes = result.boxes
                for box in boxes:
                    # Get class ID and name
                    class_id = int(box.cls[0])
                    class_name = result.names[class_id]
                    confidence = float(box.conf[0])

                    # Translate to Spanish
                    spanish_name = COCO_SPANISH.get(class_name, class_name)

                    # Determine investigation category
                    category = self._get_category(class_name)

                    obj_data = {
                        "object_type": class_name,
                        "object_type_es": spanish_name,
                        "category": category,
                        "confidence": confidence,
                    }

                    # Add bounding box if requested
                    if include_bbox:
                        bbox = box.xyxy[0].cpu().numpy().tolist()
                        obj_data["bbox"] = bbox

                    detected_objects.append(obj_data)

            logger.info(
                "Object detection completed",
                image=Path(image_path).name,
                objects_found=len(detected_objects)
            )

            return detected_objects

        except Exception as e:
            logger.error("Object detection failed", error=str(e), image=image_path)
            return []

    def _get_category(self, class_name: str) -> str:
        """
        Map object class to investigation category (Spanish)

        Args:
            class_name: English class name

        Returns:
            Spanish category name or "otros" if not categorized
        """
        for category, classes in INVESTIGATION_CATEGORIES.items():
            if class_name in classes:
                return category
        return "otros"

    def get_all_categories(self) -> List[str]:
        """
        Get list of all investigation categories

        Returns:
            List of category names in Spanish
        """
        return list(INVESTIGATION_CATEGORIES.keys()) + ["otros"]

    def get_category_objects(self, category: str) -> List[str]:
        """
        Get all object types in a category

        Args:
            category: Category name in Spanish

        Returns:
            List of object types (English) in that category
        """
        return INVESTIGATION_CATEGORIES.get(category, [])
