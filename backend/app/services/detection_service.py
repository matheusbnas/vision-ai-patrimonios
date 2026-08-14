"""
Serviço de detecção — YOLO (objetos/risco no quadrante) + HF (KzRyan/Burglary_and_Vandalism).
"""

import time
import logging
from typing import Optional

import numpy as np

from app.models.detector import PatrimonyDetector
from app.models.hf_model import HuggingFaceVandalismModel

logger = logging.getLogger(__name__)


class DetectionService:
    """
    Serviço central que coordena:
    1. YOLO (PatrimonyDetector) → Detecção de objetos + alerta de risco no quadrante
    2. HF Model → Classificação via CNN-Transformer (KzRyan/Burglary_and_Vandalism)
    """

    def __init__(self):
        self.yolo_detector = PatrimonyDetector()
        self.hf_vandalism = HuggingFaceVandalismModel()

    def detect_full(self, image: np.ndarray, camera_id: str = "unknown",
                    confidence: Optional[float] = None) -> dict:
        """
        Pipeline de detecção: YOLO + HF Model.

        Args:
            image: Imagem numpy (RGB)

        Returns:
            dict: Resultado com yolo_detection, risk_alert e hf_prediction
        """
        start = time.time()

        result = {
            "yolo_detection": {"objects": [], "counts": {}, "total_objects": 0},
            "risk_alert": None,
            "loitering_alert": None,
            "hf_prediction": None,
            "processing_time_ms": 0,
        }

        # YOLO Detection (carrega sob demanda)
        if not self.yolo_detector.model_loaded:
            try:
                self.yolo_detector.load_model()
            except Exception as e:
                logger.warning(f"YOLO não disponível: {e}")
        if self.yolo_detector.model_loaded:
            try:
                yolo_result = self.yolo_detector.detect(image, confidence, camera_code=camera_id)
                result["yolo_detection"] = {
                    "objects": yolo_result.get("objects", []),
                    "counts": yolo_result.get("counts", {}),
                    "total_objects": yolo_result.get("total_objects", 0),
                    "annotated_image": yolo_result.get("annotated_image"),
                }
                result["risk_alert"] = yolo_result.get("risk_alert")
                result["loitering_alert"] = yolo_result.get("loitering_alert")
            except Exception as e:
                logger.warning(f"Erro YOLO detection: {e}")

        # HF Model Prediction (carrega sob demanda)
        if not self.hf_vandalism.model_loaded:
            try:
                self.hf_vandalism.load_model()
            except Exception as e:
                logger.warning(f"HF Vandalism não disponível: {e}")
        if self.hf_vandalism.model_loaded:
            try:
                result["hf_prediction"] = self.hf_vandalism.predict_image(image)
            except Exception as e:
                logger.warning(f"Erro HF prediction: {e}")

        elapsed = (time.time() - start) * 1000
        result["processing_time_ms"] = round(elapsed, 2)

        return result

    def get_models_status(self) -> dict:
        """Retorna status dos modelos YOLO e HF"""
        return {
            "yolo": self.yolo_detector.model_loaded,
            "hf_vandalism": self.hf_vandalism.model_loaded,
            "hf_vandalism_info": self.hf_vandalism.get_info(),
        }
