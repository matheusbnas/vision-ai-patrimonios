"""
Peças da comparação "a estátua mudou?" (change_detector):

  - Silhueta da estátua: YOLO de SEGMENTAÇÃO (yolo26n-seg). A estátua do
    Drummond sai como "pessoa"; a máscara dela é a figura exata — sem o
    banco, a areia, o mar ou o guarda-sol que ficam dentro da caixa.
  - Silhueta de quem está na frente: mesma segmentação. A caixa do YOLO
    corta cabelo, braço e bolsa; a máscara (com folga) cobre a pessoa toda.
  - Alinhamento: a câmera da orla mexe um pouco o enquadramento (posição e
    zoom). Sem alinhar, a estátua "desloca" e toda borda vira diferença.
    Pontos fixos da cena (estátua, banco, calçada) em volta da estátua são
    casados entre a referência e a imagem atual (ORB + RANSAC) e a atual é
    reprojetada no enquadramento da referência antes de comparar.
"""

import logging
import threading
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.config import SEG_MODEL

logger = logging.getLogger(__name__)

SEG_CONF = 0.3
# Casamento de pontos: mínimo de pontos consistentes pra confiar no alinhamento
ALIGN_MIN_INLIERS = 60
# Região usada pra alinhar = caixa da estátua ampliada (fração de cada lado)
ALIGN_CONTEXT = 0.6
# Deslocamento/zoom acima disto = a câmera mudou de posição (não é "tremida")
ALIGN_MAX_SHIFT = 1.0       # fração do tamanho da caixa da estátua
ALIGN_MAX_SCALE = 0.35      # ±35% de zoom

_model = None
_failed = False
_lock = threading.Lock()


def _seg():
    global _model, _failed
    if _model is None and not _failed:
        try:
            from ultralytics import YOLO
            _model = YOLO(str(Path(SEG_MODEL)))  # baixa na primeira vez (~6 MB)
            logger.info(f"Modelo de segmentação carregado: {SEG_MODEL}")
        except Exception as e:
            _failed = True
            logger.error(f"Segmentação indisponível — comparação cai na caixa da estátua: {e}")
    return _model


def people_masks(frame: np.ndarray) -> list[tuple[list, np.ndarray]]:
    """[(caixa, máscara bool do tamanho do frame)] de cada 'pessoa' segmentada."""
    m = _seg()
    if m is None:
        return []
    h, w = frame.shape[:2]
    with _lock:
        r = m(frame, conf=SEG_CONF, classes=[0], retina_masks=True, verbose=False)[0]
    if r.masks is None:
        return []
    out = []
    for box, mk in zip(r.boxes.xyxy.cpu().numpy(), r.masks.data.cpu().numpy()):
        if mk.shape != (h, w):
            mk = cv2.resize(mk, (w, h), interpolation=cv2.INTER_NEAREST)
        out.append(([int(v) for v in box], mk > 0.5))
    return out


def _box_iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def statue_silhouette(frame: np.ndarray, statue_box, masks=None) -> Optional[np.ndarray]:
    """Máscara da estátua = a 'pessoa' segmentada que coincide com a caixa da estátua."""
    masks = masks if masks is not None else people_masks(frame)
    best = max(((_box_iou(b, statue_box), mk) for b, mk in masks), key=lambda t: t[0], default=(0, None))
    return best[1] if best[0] >= 0.5 else None


def mask_iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter / union) if union else 0.0


def align(ref_gray: np.ndarray, cur_gray: np.ndarray, box) -> tuple[Optional[np.ndarray], dict]:
    """
    Matriz afim (2x3) que leva a imagem ATUAL pro enquadramento da
    REFERÊNCIA, estimada na região ao redor da estátua. Devolve (None, info)
    se não der pra confiar (poucos pontos ou a câmera mudou muito).
    """
    h, w = ref_gray.shape[:2]
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    cx1, cy1 = max(int(x1 - bw * ALIGN_CONTEXT), 0), max(int(y1 - bh * ALIGN_CONTEXT), 0)
    cx2, cy2 = min(int(x2 + bw * ALIGN_CONTEXT), w), min(int(y2 + bh * ALIGN_CONTEXT), h)
    mask = np.zeros((h, w), np.uint8)
    mask[cy1:cy2, cx1:cx2] = 255

    orb = cv2.ORB_create(2000)
    k1, d1 = orb.detectAndCompute(ref_gray, mask)
    k2, d2 = orb.detectAndCompute(cur_gray, mask)
    info = {"inliers": 0, "shift": None, "scale": None}
    if d1 is None or d2 is None or len(k1) < ALIGN_MIN_INLIERS or len(k2) < ALIGN_MIN_INLIERS:
        return None, {**info, "reason": "poucos pontos de referência na cena"}
    matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d2, d1)
    if len(matches) < ALIGN_MIN_INLIERS:
        return None, {**info, "reason": "cena muito diferente da referência"}
    src = np.float32([k2[m.queryIdx].pt for m in matches])
    dst = np.float32([k1[m.trainIdx].pt for m in matches])
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    n = int(inl.sum()) if inl is not None else 0
    info["inliers"] = n
    if M is None or n < ALIGN_MIN_INLIERS:
        return None, {**info, "reason": "não foi possível alinhar com a referência"}
    scale = float(np.hypot(M[0, 0], M[1, 0]))
    # Deslocamento do centro da estátua, em fração do tamanho dela
    c = np.array([(x1 + x2) / 2, (y1 + y2) / 2, 1.0])
    moved = M @ c - c[:2]
    shift = float(max(abs(moved[0]) / max(bw, 1), abs(moved[1]) / max(bh, 1)))
    info.update(scale=round(scale, 3), shift=round(shift, 3))
    if abs(scale - 1) > ALIGN_MAX_SCALE or shift > ALIGN_MAX_SHIFT:
        return None, {**info, "reason": "a câmera mudou o enquadramento"}
    return M, info


def masked_ncc(a_gray: np.ndarray, b_gray: np.ndarray, mask: np.ndarray) -> float:
    """Correlação normalizada (-1..1) entre duas imagens, só nos pixels da máscara.
    ~1 = mesma imagem (mesmo com luz diferente); baixo = outra coisa no lugar."""
    if mask.sum() < 50:
        return 1.0
    a = a_gray[mask].astype(np.float32)
    b = b_gray[mask].astype(np.float32)
    a = (a - a.mean()) / (a.std() + 1e-6)
    b = (b - b.mean()) / (b.std() + 1e-6)
    return float((a * b).mean())
