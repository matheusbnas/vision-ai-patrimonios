"""
Integração com modelos do Hugging Face para detecção de vandalismo e danos.
Suporta:
  - KzRyan/Burglary_and_Vandalism (CNN-Transformer para classificação de vídeo)
  - dolphinium/damaged-building-detection (YOLOv5 para detecção de danos)
"""

import io
import os
import time
import logging
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import cv2
from PIL import Image

from app.config import (
    HF_TOKEN,
    VANDALISM_MODEL_REPO,
    VANDALISM_MODEL_FILE,
    DAMAGE_MODEL_REPO,
    MODELS_DIR,
)

logger = logging.getLogger(__name__)


class HuggingFaceVandalismModel:
    """
    Wrapper para o modelo KzRyan/Burglary_and_Vandalism.
    Modelo CNN-Transformer Híbrido (ResNet18 + Transformer)
    que classifica vídeos em: normal, burglary, vandalism.

    Pode ser usado como SLM para inferência rápida.
    """

    def __init__(self):
        self.model = None
        self.classes = ["normal", "burglary", "vandalism"]
        self.model_loaded = False
        self.device = self._get_device()

    def _get_device(self):
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    def load_model(self) -> bool:
        """Carrega o modelo CNN-Transformer do Hugging Face Hub"""
        try:
            from huggingface_hub import hf_hub_download
            import torch

            logger.info(f"Baixando modelo de {VANDALISM_MODEL_REPO}...")
            model_path = hf_hub_download(
                repo_id=VANDALISM_MODEL_REPO,
                filename=VANDALISM_MODEL_FILE,
                token=HF_TOKEN if HF_TOKEN else None,
            )

            from app.models.hf_hybrid import build_model

            model_cfg = {
                "num_classes": len(self.classes),
                "backbone": "resnet18",
                "d_model": 128,
                "num_heads": 4,
                "num_layers": 2,
                "dim_ff": 256,
                "dropout": 0.1,
                "in_channels": 3,
            }

            self.model = build_model(model_cfg).to(self.device)
            ckpt = torch.load(model_path, map_location=self.device)
            state_dict = ckpt.get("model_state", ckpt)
            self.model.load_state_dict(state_dict, strict=False)
            self.model.eval()
            self.model_loaded = True
            logger.info(f"Modelo HF carregado com sucesso em {self.device}")
            return True

        except Exception as e:
            logger.error(f"Erro ao carregar modelo HF: {e}")
            return False

    def predict_video(self, video_path: str, num_frames: int = 16) -> dict:
        """
        Classifica um vídeo inteiro.

        Args:
            video_path: Caminho para o arquivo de vídeo
            num_frames: Número de frames para amostrar

        Returns:
            dict: Probabilidades por classe
        """
        if not self.model_loaded:
            return {"error": "Modelo não carregado"}

        try:
            import torch
            import torchvision.transforms as T

            frames = self._extract_frames(video_path, num_frames)
            if frames is None:
                return {"error": "Não foi possível extrair frames do vídeo"}

            transform = T.Compose([
                T.ToPILImage(),
                T.Resize((224, 224)),
                T.ToTensor(),
                T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])

            rgb_frames = []
            for t in range(frames.shape[0]):
                frame_t = transform(frames[t])
                rgb_frames.append(frame_t)

            clip_tensor = torch.stack(rgb_frames, dim=1).unsqueeze(0).to(self.device)

            with torch.no_grad():
                logits = self.model(clip_tensor)
                probs = torch.nn.functional.softmax(logits, dim=1).squeeze(0).cpu().numpy()

            return {
                self.classes[i]: float(probs[i])
                for i in range(len(self.classes))
            }

        except Exception as e:
            logger.error(f"Erro na inferência do vídeo: {e}")
            return {"error": str(e)}

    def predict_image(self, image: np.ndarray) -> dict:
        """
        Para imagem estática, simula classificação tratando como vídeo de 1 frame.

        Args:
            image: Imagem numpy array (RGB)

        Returns:
            dict: Probabilidades por classe
        """
        if not self.model_loaded:
            return {"error": "Modelo não carregado"}

        try:
            import torch
            import torchvision.transforms as T

            transform = T.Compose([
                T.ToPILImage(),
                T.Resize((224, 224)),
                T.ToTensor(),
                T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])

            # Duplica o frame para simular T=16
            frame_t = transform(image)
            frames = frame_t.unsqueeze(1).repeat(1, 16, 1, 1)
            clip_tensor = frames.unsqueeze(0).to(self.device)

            with torch.no_grad():
                logits = self.model(clip_tensor)
                probs = torch.nn.functional.softmax(logits, dim=1).squeeze(0).cpu().numpy()

            return {
                self.classes[i]: float(probs[i])
                for i in range(len(self.classes))
            }

        except Exception as e:
            logger.error(f"Erro na inferência da imagem: {e}")
            return {"error": str(e)}

    def _extract_frames(self, video_path: str, num_frames: int) -> Optional[np.ndarray]:
        """Amostra frames uniformemente de um vídeo"""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total < 1:
            cap.release()
            return None

        n = min(num_frames, total)
        indices = np.linspace(0, total - 1, n, dtype=int)
        frames = []

        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ret, frame = cap.read()
            if not ret:
                frame = frames[-1] if frames else np.zeros((224, 224, 3), dtype=np.uint8)
            else:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame = cv2.resize(frame, (224, 224), interpolation=cv2.INTER_LINEAR)
            frames.append(frame)

        cap.release()

        while len(frames) < num_frames:
            frames.append(frames[-1])

        return np.stack(frames, axis=0)

    def get_info(self) -> dict:
        """Retorna informações sobre o modelo"""
        return {
            "repo_id": VANDALISM_MODEL_REPO,
            "model_loaded": self.model_loaded,
            "classes": self.classes,
            "device": self.device,
            "pipeline_tag": "video-classification",
        }


class DamageDetectionModel:
    """
    Wrapper para dolphinium/damaged-building-detection (YOLOv5).
    Detecta danos estruturais em imagens de construções/monumentos.
    """

    def __init__(self):
        self.model = None
        self.model_loaded = False

    def load_model(self) -> bool:
        """Carrega o modelo YOLOv5 de detecção de danos"""
        try:
            import torch

            # Carrega o modelo YOLOv5 do Hugging Face
            model_path = self._download_model()
            if not model_path:
                return False

            self.model = torch.hub.load(
                "ultralytics/yolov5",
                "custom",
                path=model_path,
                force_reload=False,
            )
            self.model.conf = 0.25
            self.model_loaded = True
            logger.info("Modelo de detecção de danos carregado")
            return True

        except Exception as e:
            logger.error(f"Erro ao carregar modelo de danos: {e}")
            return False

    def _download_model(self) -> Optional[str]:
        """Baixa os pesos do modelo do Hugging Face"""
        try:
            from huggingface_hub import snapshot_download

            local_dir = MODELS_DIR / "damaged-building-detection"
            if not (local_dir / "best.pt").exists():
                logger.info("Baixando modelo de detecção de danos...")
                snapshot_download(
                    repo_id=DAMAGE_MODEL_REPO,
                    local_dir=str(local_dir),
                    token=HF_TOKEN if HF_TOKEN else None,
                )

            # Procura por arquivos .pt ou .pth
            pt_files = list(local_dir.glob("*.pt")) + list(local_dir.glob("*.pth"))
            if pt_files:
                return str(pt_files[0])
            return None

        except Exception as e:
            logger.error(f"Erro ao baixar modelo: {e}")
            return None

    def predict(self, image: np.ndarray) -> dict:
        """
        Detecta danos em uma imagem

        Args:
            image: Imagem numpy array (RGB)

        Returns:
            dict: Resultados da detecção
        """
        if not self.model_loaded:
            return {"error": "Modelo não carregado", "detections": []}

        try:
            results = self.model(image)
            detections = results.pandas().xyxy[0].to_dict("records")

            return {
                "detections": detections,
                "total": len(detections),
                "annotated": results.render()[0] if len(results) > 0 else image,
            }

        except Exception as e:
            logger.error(f"Erro na detecção de danos: {e}")
            return {"error": str(e), "detections": []}

    def get_info(self) -> dict:
        return {
            "repo_id": DAMAGE_MODEL_REPO,
            "model_loaded": self.model_loaded,
            "pipeline_tag": "object-detection",
        }
