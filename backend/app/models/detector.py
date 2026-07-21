"""
Módulo de Visão Computacional para Detecção de Patrimônios
Utiliza YOLO (Ultralytics) para identificar objetos nas imagens das câmeras
"""

import time
import logging
from collections import Counter
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.config import (
    YOLO_MODEL,
    CONFIDENCE_THRESHOLD,
    PATRIMONY_CLASSES,
    INTEREST_CLASSES,
)

logger = logging.getLogger(__name__)


class PatrimonyDetector:
    """
    Detector de patrimônios usando YOLO
    Responsável por processar imagens e identificar objetos de interesse
    """

    def __init__(self):
        self.model = None
        self.model_loaded = False

    def load_model(self) -> bool:
        """Carrega o modelo YOLO"""
        try:
            from ultralytics import YOLO
            model_path = Path(YOLO_MODEL)
            if not model_path.exists():
                logger.error(f"Modelo YOLO não encontrado: {model_path}")
                return False
            self.model = YOLO(str(model_path))
            self.model_loaded = True
            logger.info(f"Modelo YOLO carregado: {YOLO_MODEL}")
            return True
        except Exception as e:
            logger.error(f"Erro ao carregar modelo YOLO: {e}")
            return False

    def ensure_model(self) -> bool:
        """Garante que o modelo está carregado"""
        if not self.model_loaded:
            return self.load_model()
        return self.model_loaded

    def detect(self, image: np.ndarray, confidence: Optional[float] = None) -> dict:
        """
        Executa detecção em uma imagem

        Args:
            image: Imagem em array numpy (RGB)
            confidence: Threshold de confiança (opcional)

        Returns:
            dict: Resultados da detecção
        """
        start_time = time.time()

        if not self.ensure_model():
            return {
                "objects": [],
                "annotated_image": image,
                "counts": {},
                "total_objects": 0,
                "processing_time_ms": 0,
            }

        conf = confidence or CONFIDENCE_THRESHOLD
        results = self.model(image, conf=conf)

        detections = []
        class_counts = Counter()

        if results and len(results) > 0:
            result = results[0]
            boxes = result.boxes

            if boxes is not None and len(boxes) > 0:
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    class_id = int(box.cls[0].item())
                    score = float(box.conf[0].item())

                    class_name = PATRIMONY_CLASSES.get(class_id, f"classe_{class_id}")
                    patrimony_type = INTEREST_CLASSES.get(class_name, "Outro")

                    detection = {
                        "class_id": class_id,
                        "class_name": class_name,
                        "patrimony_type": patrimony_type,
                        "confidence": round(score, 3),
                        "bbox": [int(x1), int(y1), int(x2), int(y2)],
                    }
                    detections.append(detection)
                    class_counts[class_name] += 1

            # Gerar imagem anotada
            annotated_image = result.plot()
            annotated_image = cv2.cvtColor(annotated_image, cv2.COLOR_BGR2RGB)
        else:
            annotated_image = image

        elapsed = (time.time() - start_time) * 1000

        return {
            "objects": detections,
            "annotated_image": annotated_image,
            "counts": dict(class_counts),
            "total_objects": len(detections),
            "processing_time_ms": round(elapsed, 2),
        }

    def detect_from_file(self, image_path: str, confidence: Optional[float] = None) -> dict:
        """Executa detecção a partir de um arquivo de imagem"""
        image = cv2.imread(image_path)
        if image is None:
            return {
                "objects": [], "annotated_image": None,
                "counts": {}, "total_objects": 0,
                "processing_time_ms": 0,
                "error": "Não foi possível ler a imagem",
            }
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        return self.detect(image, confidence)

    def detect_from_bytes(self, image_bytes: bytes, confidence: Optional[float] = None) -> dict:
        """Executa detecção a partir de bytes de imagem"""
        file_bytes = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if image is None:
            return {
                "objects": [], "annotated_image": None,
                "counts": {}, "total_objects": 0,
                "processing_time_ms": 0,
                "error": "Formato de imagem inválido",
            }
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        return self.detect(image, confidence)
