"""
Serviço de detecção — apenas modelo HF (KzRyan/Burglary_and_Vandalism).
"""

import time
import logging
from typing import Optional

import numpy as np

from app.models.hf_model import HuggingFaceVandalismModel

logger = logging.getLogger(__name__)


class DetectionService:
    """
    Serviço central que coordena:
    1. HF Model → Classificação via CNN-Transformer (KzRyan/Burglary_and_Vandalism)
    """

    def __init__(self):
        self.hf_vandalism = HuggingFaceVandalismModel()

    def detect_full(self, image: np.ndarray, camera_id: str = "unknown",
                    confidence: Optional[float] = None) -> dict:
        """
        Pipeline de detecção via HF Model.

        Args:
            image: Imagem numpy (RGB)

        Returns:
            dict: Resultado com hf_prediction
        """
        start = time.time()

        result = {
            "hf_prediction": None,
            "processing_time_ms": 0,
        }

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
        """Retorna status do modelo HF"""
        return {
            "hf_vandalism": self.hf_vandalism.model_loaded,
            "hf_vandalism_info": self.hf_vandalism.get_info(),
        }
