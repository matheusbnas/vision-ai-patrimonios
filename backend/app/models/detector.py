"""
Módulo de Visão Computacional para Detecção de Patrimônios
Utiliza YOLO (Ultralytics) para identificar objetos nas imagens das câmeras.

Além da detecção padrão, aplica um filtro de "quadrante" (ROI central,
mesma zona usada pelo change_detector) para focar no monumento e gerar
um alerta preditivo quando um objeto de risco (RISK_CLASSES) aparece
dentro dessa zona — antes de qualquer dano físico ser registrado.
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
    RISK_CLASSES,
    DWELL_ALERT_SECONDS,
    PERSON_LOITERING_ALERT_SECONDS,
    STATUE_OBJECT_OVERLAP,
)
from app.services import zone_service, risk_tracker
from app.models.interaction import InteractionAnalyzer, _overlap_frac, is_statue_itself

logger = logging.getLogger(__name__)


def _zone_box(width: int, height: int, camera_code: Optional[str] = None) -> tuple:
    """Calcula o retângulo do quadrante (em pixels) para um frame.

    Usa a zona calibrada da câmera (zone_service), se houver;
    senão cai no quadrante padrão.
    """
    zone = zone_service.get_zone(camera_code)
    x1 = int(width * zone["x_start"])
    x2 = int(width * zone["x_end"])
    y1 = int(height * zone["y_start"])
    y2 = int(height * zone["y_end"])
    return x1, y1, x2, y2


def _frac_box(frac: Optional[dict], width: int, height: int) -> Optional[tuple]:
    """Zona em frações (0-1) → retângulo em pixels; None se não calibrada."""
    if not frac:
        return None
    return (int(width * frac["x_start"]), int(height * frac["y_start"]),
            int(width * frac["x_end"]), int(height * frac["y_end"]))


def _center_in_zone(bbox: list, zone: tuple) -> bool:
    x1, y1, x2, y2 = bbox
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    zx1, zy1, zx2, zy2 = zone
    return zx1 <= cx <= zx2 and zy1 <= cy <= zy2


class PatrimonyDetector:
    """
    Detector de patrimônios usando YOLO.
    Responsável por processar imagens, identificar objetos de interesse
    e sinalizar objetos de risco dentro do quadrante do monumento.
    """

    def __init__(self):
        self.model = None
        self.model_loaded = False
        self.interaction = InteractionAnalyzer()

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

    def detect(self, image: np.ndarray, confidence: Optional[float] = None,
               camera_code: Optional[str] = None) -> dict:
        """
        Executa detecção em uma imagem, filtrando objetos de risco
        pelo quadrante (zona) do monumento.

        Args:
            image: Imagem em array numpy (RGB)
            confidence: Threshold de confiança (opcional)
            camera_code: Código da câmera, para usar a zona calibrada (opcional)

        Returns:
            dict: Resultados da detecção, incluindo risk_objects/risk_alert
        """
        start_time = time.time()

        if not self.ensure_model():
            return {
                "objects": [],
                "annotated_image": image,
                "counts": {},
                "total_objects": 0,
                "risk_objects": [],
                "risk_alert": None,
                "loitering_alert": None,
                "interaction_alert": None,
                "processing_time_ms": 0,
            }

        conf = confidence or CONFIDENCE_THRESHOLD
        results = self.model(image, conf=conf)

        detections = []
        class_counts = Counter()
        h, w = image.shape[:2]
        zone = _zone_box(w, h, camera_code)
        statue_cfg = zone_service.get_statue(camera_code)
        statue_px = _frac_box(statue_cfg["statue"], w, h)
        sensitive_px = _frac_box(statue_cfg["sensitive"], w, h)

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
                    bbox = [int(x1), int(y1), int(x2), int(y2)]

                    detection = {
                        "class_id": class_id,
                        "class_name": class_name,
                        "patrimony_type": patrimony_type,
                        "confidence": round(score, 3),
                        "bbox": bbox,
                        "in_zone": _center_in_zone(bbox, zone),
                        # Fração da caixa do objeto dentro do contorno da
                        # estátua (None = câmera sem contorno calibrado)
                        "statue_overlap": round(_overlap_frac(bbox, statue_px), 3) if statue_px else None,
                        # A própria estátua detectada como "pessoa"
                        "is_statue": class_name == "pessoa" and is_statue_itself(bbox, statue_px),
                    }
                    detections.append(detection)
                    class_counts[class_name] += 1

            # Gerar imagem anotada
            annotated_image = result.plot()
            annotated_image = cv2.cvtColor(annotated_image, cv2.COLOR_BGR2RGB)
        else:
            annotated_image = image.copy()

        # ─── Filtro de risco: objetos de RISK_CLASSES junto da estátua ───
        # Com contorno calibrado, o objeto precisa ENCOSTAR na estátua
        # (STATUE_OBJECT_OVERLAP da caixa dentro do contorno) — estar só
        # "atrás" dela na imagem, como um guarda-sol na areia, não conta.
        # Sem contorno, cai no critério antigo (centro dentro da zona).
        def _near_statue(d: dict) -> bool:
            if statue_px:
                return d["statue_overlap"] >= STATUE_OBJECT_OVERLAP
            return d["in_zone"]

        risk_objects = [
            d for d in detections
            if d["class_name"] in RISK_CLASSES and _near_statue(d)
        ]
        risk_alert = None
        tracker_key = camera_code or "unknown"
        if risk_objects:
            present_classes = {d["class_name"] for d in risk_objects}
            dwell = risk_tracker.update(tracker_key, present_classes)
            max_dwell = max(dwell.values()) if dwell else 0.0

            base_levels = {RISK_CLASSES[c] for c in present_classes}
            if max_dwell >= DWELL_ALERT_SECONDS:
                level = "CRÍTICO"
            elif "ALTO" in base_levels:
                level = "ALTO"
            else:
                level = "MODERADO"

            nomes = ", ".join(sorted(present_classes))
            dwell_txt = f" (presente há {int(max_dwell)}s)" if max_dwell >= 10 else ""
            icon = "🚨" if level == "CRÍTICO" else "⚠️"
            risk_alert = {
                "level": level,
                "message": f"{icon} {level}: Objeto suspeito ({nomes}) próximo ao monumento{dwell_txt}",
                "objects": sorted(present_classes),
                "dwell_seconds": round(max_dwell, 1),
            }
        else:
            # Nada de risco presente agora — reseta os timers dessa câmera
            risk_tracker.update(tracker_key, set())

        # ─── Permanência de pessoas na zona (risco preventivo) ───────────
        # Uma pessoa não é descartada da análise: se ela (ou alguém, já que
        # não há reidentificação) fica parada perto do monumento por muito
        # tempo, isso é sinal de risco iminente (furto/vandalismo), mesmo
        # sem nenhum objeto de risco visível — vale a pena alertar antes
        # que o dano aconteça. Usa o mesmo mecanismo de dwell do
        # risk_tracker, mas num namespace separado pra não interferir no
        # timer de RISK_CLASSES.
        # Com contorno calibrado, "perto" = encostada na estátua; sem ele,
        # qualquer pessoa na zona (critério antigo).
        person_present = any(
            d["class_name"] == "pessoa" and not d["is_statue"]
            and ((d["statue_overlap"] or 0) >= 0.1 if statue_px else d["in_zone"])
            for d in detections
        )
        loitering_key = f"{tracker_key}::pessoa"
        person_dwell = risk_tracker.update(
            loitering_key, {"pessoa"} if person_present else set()
        )
        person_dwell_seconds = person_dwell.get("pessoa", 0.0)

        # Informativo (MODERADO, não gera notificação — ver alert_service):
        # em monumento turístico sempre tem alguém por perto, e o YOLO não
        # reidentifica pessoas, então "10 min" costuma ser gente diferente.
        loitering_alert = None
        if person_present and person_dwell_seconds >= PERSON_LOITERING_ALERT_SECONDS:
            minutos = int(person_dwell_seconds // 60)
            loitering_alert = {
                "level": "MODERADO",
                "message": (
                    f"👥 Presença contínua de pessoas junto ao monumento há {minutos} min"
                ),
                "dwell_seconds": round(person_dwell_seconds, 1),
            }

        # ─── Interação com a estátua (pose) ──────────────────────────────
        # Só roda o modelo de pose quando há alguém encostado na estátua.
        interaction_alert = None
        if statue_px:
            someone_at_statue = any(
                d["class_name"] == "pessoa" and not d["is_statue"]
                and (d["statue_overlap"] or 0) >= 0.1
                for d in detections
            )
            if someone_at_statue:
                interaction_alert = self.interaction.analyze(
                    image, tracker_key, statue_px, sensitive_px, annotated=annotated_image
                )
            else:
                risk_tracker.update(f"{tracker_key}::interacao", set())

        # ─── Desenha zona, contorno da estátua e objetos de risco ────────
        zx1, zy1, zx2, zy2 = zone
        cv2.rectangle(annotated_image, (zx1, zy1), (zx2, zy2), (0, 255, 255), 1)
        if statue_px:
            cv2.rectangle(annotated_image, statue_px[:2], statue_px[2:], (0, 200, 255), 2)
        if sensitive_px:
            cv2.rectangle(annotated_image, sensitive_px[:2], sensitive_px[2:], (255, 0, 255), 2)
        for d in risk_objects:
            rx1, ry1, rx2, ry2 = d["bbox"]
            cv2.rectangle(annotated_image, (rx1, ry1), (rx2, ry2), (255, 0, 0), 3)
            cv2.putText(annotated_image, d["class_name"], (rx1, max(ry1 - 8, 0)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

        elapsed = (time.time() - start_time) * 1000

        return {
            "objects": detections,
            "annotated_image": annotated_image,
            "counts": dict(class_counts),
            "total_objects": len(detections),
            "risk_objects": risk_objects,
            "risk_alert": risk_alert,
            "loitering_alert": loitering_alert,
            "interaction_alert": interaction_alert,
            "processing_time_ms": round(elapsed, 2),
        }

    def detect_from_file(self, image_path: str, confidence: Optional[float] = None) -> dict:
        """Executa detecção a partir de um arquivo de imagem"""
        image = cv2.imread(image_path)
        if image is None:
            return {
                "objects": [], "annotated_image": None,
                "counts": {}, "total_objects": 0,
                "risk_objects": [], "risk_alert": None,
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
                "risk_objects": [], "risk_alert": None,
                "processing_time_ms": 0,
                "error": "Formato de imagem inválido",
            }
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        return self.detect(image, confidence)
