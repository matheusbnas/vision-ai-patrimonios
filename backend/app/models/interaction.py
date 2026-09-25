"""
Interação de pessoas com a estátua, via YOLO-pose (keypoints COCO).

A ideia é separar o comportamento normal de turista (sentar ao lado,
abraçar, segurar a mão do Drummond pra foto) do que é suspeito:

  - mão dentro da ÁREA SENSÍVEL (óculos/cabeça, violão...) — alvo típico
    de furto. Num print só é MODERADO (pode ser pose pra foto); se
    continuar nos prints seguidos por INTERACTION_ESCALATE_SECONDS, ALTO;
  - pés acima da base, dentro do contorno — pessoa EM CIMA da estátua
    ou do pedestal: ALTO.

Limitação: o monitoramento analisa prints a cada 10-60s, não vídeo. Um
gesto rápido entre dois prints passa despercebido — por isso a
change_detector escala para CRÍTICO uma mudança física no contorno logo
depois de uma interação (INTERACTION_MEMORY_SECONDS), pegando a peça
faltando mesmo sem ter flagrado o gesto.
"""

import logging
import threading
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.config import (
    POSE_MODEL,
    POSE_KEYPOINT_CONF,
    CLIMB_FOOT_MIN_HEIGHT,
    INTERACTION_ESCALATE_SECONDS,
    STATUE_SELF_IOU,
)
from app.services import risk_tracker

logger = logging.getLogger(__name__)

# Índices dos keypoints COCO-17
WRISTS = (9, 10)
ANKLES = (15, 16)

# Última interação por câmera (timestamp) — lida pela change_detector
_last_interaction: dict[str, float] = {}
_lock = threading.Lock()


def last_interaction(camera_code: str) -> Optional[float]:
    with _lock:
        return _last_interaction.get(camera_code)


def _inside(pt, box, margin: float = 0.0) -> bool:
    x, y = pt
    x1, y1, x2, y2 = box
    mx, my = (x2 - x1) * margin, (y2 - y1) * margin
    return x1 - mx <= x <= x2 + mx and y1 - my <= y <= y2 + my


def _overlap_frac(a, b) -> float:
    """Fração da caixa `a` que está dentro da caixa `b`."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    area_a = max((a[2] - a[0]) * (a[3] - a[1]), 1)
    return (ix2 - ix1) * (iy2 - iy1) / area_a


def iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def is_statue_itself(bbox, statue_px) -> bool:
    """Detecção de 'pessoa' que é a própria estátua (figura humana).

    IoU alto com o contorno, ou caixa inteira dentro do contorno ocupando
    boa parte dele (estátuas pequenas no quadro, onde a caixa do YOLO sai
    mais justa que o contorno calibrado e o IoU fica baixo).
    """
    if not statue_px:
        return False
    if iou(bbox, statue_px) >= STATUE_SELF_IOU:
        return True
    area_box = max((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]), 1)
    area_statue = max((statue_px[2] - statue_px[0]) * (statue_px[3] - statue_px[1]), 1)
    return _overlap_frac(bbox, statue_px) >= 0.9 and area_box / area_statue >= 0.3


class InteractionAnalyzer:
    def __init__(self):
        self.model = None
        self.model_loaded = False
        self._load_failed = False
        # Modelos ultralytics não são thread-safe — a análise contínua
        # (live_analysis) e as rotas/background usam o mesmo analisador
        self._infer_lock = threading.Lock()

    def load_model(self) -> bool:
        if self.model_loaded or self._load_failed:
            return self.model_loaded
        try:
            from ultralytics import YOLO
            self.model = YOLO(str(Path(POSE_MODEL)))  # ultralytics baixa se não existir
            self.model_loaded = True
            logger.info(f"Modelo YOLO-pose carregado: {POSE_MODEL}")
        except Exception as e:
            # Não tenta de novo a cada print (download bloqueado etc.)
            self._load_failed = True
            logger.error(f"YOLO-pose indisponível — análise de interação desativada: {e}")
        return self.model_loaded

    def analyze(self, image: np.ndarray, camera_code: str,
                statue_px: tuple, sensitive_px: Optional[tuple],
                annotated: Optional[np.ndarray] = None,
                statue_boxes: Optional[list] = None) -> Optional[dict]:
        """
        Roda pose num recorte ao redor da estátua (pessoas pequenas no
        quadro ganham resolução) e devolve o alerta de interação, se houver.
        Desenha no `annotated` (se dado) os pontos que dispararam a regra.
        """
        tracker_key = f"{camera_code}::interacao"
        if not self.load_model():
            return None

        h, w = image.shape[:2]
        sx1, sy1, sx2, sy2 = statue_px
        pad_x, pad_y = (sx2 - sx1) * 0.6, (sy2 - sy1) * 0.4
        cx1, cy1 = max(int(sx1 - pad_x), 0), max(int(sy1 - pad_y), 0)
        cx2, cy2 = min(int(sx2 + pad_x), w), min(int(sy2 + pad_y), h)
        crop = image[cy1:cy2, cx1:cx2]
        if crop.size == 0:
            return None

        try:
            with self._infer_lock:
                results = self.model(crop, conf=0.3, verbose=False)
        except Exception as e:
            logger.warning(f"Erro YOLO-pose: {e}")
            return None

        climb_floor = sy2 - (sy2 - sy1) * CLIMB_FOOT_MIN_HEIGHT
        events: set[str] = set()
        hits: list[tuple] = []  # (x, y, cor) pra desenhar

        res = results[0] if results else None
        kps = getattr(res, "keypoints", None)
        if kps is not None and kps.data is not None and len(kps.data) > 0:
            boxes = res.boxes.xyxy.cpu().numpy() if res.boxes is not None else []
            for i, person in enumerate(kps.data.cpu().numpy()):  # (17, 3): x, y, conf
                pts = [(x + cx1, y + cy1, c) for x, y, c in person]
                if i < len(boxes):
                    bx = boxes[i]
                    pbox = (bx[0] + cx1, bx[1] + cy1, bx[2] + cx1, bx[3] + cy1)
                    # Só quem está junto da estátua interessa — e a própria
                    # estátua (figura humana) também sai pelo pose
                    if (_overlap_frac(pbox, statue_px) < 0.1 or is_statue_itself(pbox, statue_px)
                            or any(iou(pbox, sb) >= 0.5 for sb in (statue_boxes or []))):
                        continue

                if sensitive_px:
                    for k in WRISTS:
                        x, y, c = pts[k]
                        if c >= POSE_KEYPOINT_CONF and _inside((x, y), sensitive_px, margin=0.1):
                            events.add("mao_area_sensivel")
                            hits.append((x, y, (255, 0, 255)))

                for k in ANKLES:
                    x, y, c = pts[k]
                    if c >= POSE_KEYPOINT_CONF and sx1 <= x <= sx2 and sy1 <= y < climb_floor:
                        events.add("em_cima_da_estatua")
                        hits.append((x, y, (255, 0, 0)))

        dwell = risk_tracker.update(tracker_key, events)
        if not events:
            return None

        with _lock:
            _last_interaction[camera_code] = time.time()

        if annotated is not None:
            for x, y, color in hits:
                cv2.circle(annotated, (int(x), int(y)), 9, color, 3)

        if "em_cima_da_estatua" in events:
            level = "ALTO"
            msg = "🚨 ALTO: Pessoa em cima da estátua/pedestal"
        else:
            secs = dwell.get("mao_area_sensivel", 0.0)
            if secs >= INTERACTION_ESCALATE_SECONDS:
                level = "ALTO"
                msg = (f"🚨 ALTO: Mão na área sensível da estátua há {int(secs)}s "
                       f"— possível tentativa de retirada de peça")
            else:
                level = "MODERADO"
                msg = "⚠️ MODERADO: Pessoa com a mão na área sensível da estátua (cabeça/óculos/peça)"

        return {
            "level": level,
            "message": msg,
            "events": sorted(events),
            "dwell_seconds": round(max(dwell.values()), 1) if dwell else 0.0,
        }


# Instância única compartilhada por todos os detectores (um só modelo de
# pose na memória, mesmo com um detector por câmera na análise contínua)
shared_analyzer = InteractionAnalyzer()
