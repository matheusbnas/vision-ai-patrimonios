"""
Módulo de Visão Computacional para Detecção de Patrimônios
Utiliza YOLO (Ultralytics) para identificar objetos nas imagens das câmeras
"""

import os
import tempfile
from pathlib import Path
from typing import Optional
from collections import Counter

import cv2
import numpy as np
from PIL import Image
import streamlit as st

from config import YOLO_MODEL, CONFIDENCE_THRESHOLD, PATRIMONY_CLASSES, INTEREST_CLASSES


class PatrimonyDetector:
    """
    Detector de patrimônios usando YOLO
    Responsável por processar imagens e identificar objetos de interesse
    """

    def __init__(self):
        self.model = None
        self.model_loaded = False

    @st.cache_resource
    def _load_model(_self):
        """Carrega o modelo YOLO (cacheado)"""
        try:
            from ultralytics import YOLO
            model = YOLO(YOLO_MODEL)
            return model
        except Exception as e:
            st.error(f"Erro ao carregar modelo YOLO: {e}")
            return None

    def ensure_model(self) -> bool:
        """Garante que o modelo está carregado"""
        if not self.model_loaded:
            self.model = self._load_model()
            self.model_loaded = self.model is not None
        return self.model_loaded

    def detect(self, image: np.ndarray, confidence: float = None) -> dict:
        """
        Executa detecção em uma imagem

        Args:
            image: Imagem em array numpy (RGB)
            confidence: Threshold de confiança (opcional)

        Returns:
            dict: Resultados da detecção
        """
        if not self.ensure_model():
            return {"objects": [], "annotated_image": image, "counts": {}}

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
                    patrimony_type = INTEREST_CLASSES.get(
                        class_name, "Outro"
                    )

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

        return {
            "objects": detections,
            "annotated_image": annotated_image,
            "counts": dict(class_counts),
            "total_objects": len(detections),
        }

    def detect_from_file(self, image_path: str, confidence: float = None) -> dict:
        """
        Executa detecção a partir de um arquivo de imagem

        Args:
            image_path: Caminho para o arquivo de imagem
            confidence: Threshold de confiança

        Returns:
            dict: Resultados da detecção
        """
        image = cv2.imread(image_path)
        if image is None:
            return {"objects": [], "annotated_image": None, "counts": {}, "error": "Não foi possível ler a imagem"}
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        return self.detect(image, confidence)

    def detect_from_upload(self, uploaded_file, confidence: float = None) -> dict:
        """
        Executa detecção em arquivo enviado pelo usuário

        Args:
            uploaded_file: Arquivo enviado (UploadedFile do Streamlit)
            confidence: Threshold de confiança

        Returns:
            dict: Resultados da detecção
        """
        # Ler imagem do upload
        file_bytes = np.frombuffer(uploaded_file.read(), np.uint8)
        image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if image is None:
            return {"objects": [], "annotated_image": None, "counts": {}, "error": "Formato de imagem inválido"}
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        return self.detect(image, confidence)

    def detect_from_camera(self, camera_id: int = 0, confidence: float = None) -> dict:
        """
        Captura frame da webcam e executa detecção

        Args:
            camera_id: ID da câmera (0 para webcam padrão)
            confidence: Threshold de confiança

        Returns:
            dict: Resultados da detecção
        """
        cap = cv2.VideoCapture(camera_id)
        if not cap.isOpened():
            return {"objects": [], "annotated_image": None, "counts": {}, "error": "Não foi possível acessar a câmera"}

        ret, frame = cap.read()
        cap.release()

        if not ret:
            return {"objects": [], "annotated_image": None, "counts": {}, "error": "Não foi possível capturar frame"}

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return self.detect(frame_rgb, confidence)

    def generate_report(self, detection_result: dict) -> str:
        """
        Gera relatório textual da detecção

        Args:
            detection_result: Resultado da detecção

        Returns:
            str: Relatório formatado
        """
        lines = ["## 📋 Relatório de Detecção de Patrimônios\n"]
        lines.append(f"**Total de objetos detectados:** {detection_result.get('total_objects', 0)}\n")

        counts = detection_result.get("counts", {})
        if counts:
            lines.append("\n### Itens Detectados:\n")
            sorted_items = sorted(counts.items(), key=lambda x: -x[1])
            for class_name, count in sorted_items:
                p_type = INTEREST_CLASSES.get(class_name, "Não classificado")
                icon = self._get_icon(class_name)
                lines.append(f"- {icon} **{class_name}** ({p_type}): {count} unidade(s)")

        objects = detection_result.get("objects", [])
        if objects:
            lines.append("\n\n### Detalhes:\n")
            for i, obj in enumerate(objects, 1):
                lines.append(
                    f"{i}. {obj['class_name']} | "
                    f"Tipo: {obj['patrimony_type']} | "
                    f"Confiança: {obj['confidence']:.1%}"
                )

        return "\n".join(lines)

    @staticmethod
    def _get_icon(class_name: str) -> str:
        """Retorna emoji para classe detectada"""
        icons = {
            "pessoa": "🚶",
            "carro": "🚗",
            "moto": "🏍️",
            "ônibus": "🚌",
            "caminhão": "🚛",
            "bicicleta": "🚲",
            "vaso": "🏺",
            "vaso_de_planta": "🪴",
            "cadeira": "🪑",
            "cachorro": "🐕",
            "gato": "🐈",
            "pássaro": "🐦",
            "livro": "📚",
            "celular": "📱",
            "monitor_tv": "📺",
            "relógio": "⌚",
            "garrafa": "🍾",
            "copo": "🥤",
        }
        return icons.get(class_name, "📦")
