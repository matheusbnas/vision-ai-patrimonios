"""
Serviço de detecção que orquestra YOLO + HF + Vandalismo
"""

import time
import logging
from typing import Optional

import numpy as np

from app.models.detector import PatrimonyDetector
from app.models.vandalism import VandalismDetector
from app.models.hf_model import HuggingFaceVandalismModel, DamageDetectionModel

logger = logging.getLogger(__name__)


class DetectionService:
    """
    Serviço central que coordena:
    1. YOLO → Detecção de objetos
    2. VandalismDetector → Análise heurística
    3. HF Model → Classificação via CNN-Transformer
    """

    def __init__(self):
        self.yolo_detector = PatrimonyDetector()
        self.vandalism_detector = VandalismDetector()
        self.hf_vandalism = HuggingFaceVandalismModel()
        self.hf_damage = DamageDetectionModel()

        # Inicializa modelos em background
        self._init_models()

    def _init_models(self):
        """Tenta carregar todos os modelos"""
        try:
            self.yolo_detector.load_model()
        except Exception as e:
            logger.warning(f"YOLO não carregado: {e}")

        try:
            self.hf_vandalism.load_model()
        except Exception as e:
            logger.warning(f"HF Vandalism não carregado: {e}")

        try:
            self.hf_damage.load_model()
        except Exception as e:
            logger.warning(f"HF Damage não carregado: {e}")

    def detect_full(self, image: np.ndarray, camera_id: str = "unknown",
                    confidence: Optional[float] = None) -> dict:
        """
        Pipeline completo de detecção.

        Args:
            image: Imagem numpy (RGB)
            camera_id: ID da câmera
            confidence: Threshold de confiança

        Returns:
            dict: Resultado completo com:
                - yolo_detection: objetos detectados
                - vandalism_analysis: análise de vandalismo
                - hf_prediction: predição do modelo HF (se disponível)
                - annotated_image: imagem anotada (base64)
        """
        start = time.time()

        result = {
            "yolo_detection": {"objects": [], "counts": {}, "total_objects": 0},
            "vandalism_analysis": None,
            "hf_prediction": None,
            "damage_detection": None,
            "processing_time_ms": 0,
        }

        # 1. YOLO Detection
        yolo_result = self.yolo_detector.detect(image, confidence)
        result["yolo_detection"] = {
            "objects": yolo_result.get("objects", []),
            "counts": yolo_result.get("counts", {}),
            "total_objects": yolo_result.get("total_objects", 0),
        }

        # 2. Vandalism Analysis (heurístico)
        if yolo_result.get("objects"):
            result["vandalism_analysis"] = self.vandalism_detector.analyze(
                yolo_result["objects"], camera_id, confidence
            )

        # 3. HF Model Prediction (imagem estática → simula classificação)
        if self.hf_vandalism.model_loaded:
            try:
                result["hf_prediction"] = self.hf_vandalism.predict_image(image)
            except Exception as e:
                logger.warning(f"Erro HF prediction: {e}")

        # 4. Damage Detection (YOLOv5)
        if self.hf_damage.model_loaded:
            try:
                result["damage_detection"] = self.hf_damage.predict(image)
            except Exception as e:
                logger.warning(f"Erro damage detection: {e}")

        elapsed = (time.time() - start) * 1000
        result["processing_time_ms"] = round(elapsed, 2)

        return result

    def get_models_status(self) -> dict:
        """Retorna status de todos os modelos"""
        return {
            "yolo": self.yolo_detector.model_loaded,
            "hf_vandalism": self.hf_vandalism.model_loaded,
            "hf_damage": self.hf_damage.model_loaded,
            "hf_vandalism_info": self.hf_vandalism.get_info(),
            "hf_damage_info": self.hf_damage.get_info(),
        }
