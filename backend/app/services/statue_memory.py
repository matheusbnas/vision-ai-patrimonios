"""
Aparência da estátua gravada na CALIBRAÇÃO.

O YOLO (COCO, 80 classes) não tem a classe "estátua": uma figura humana de
bronze sai como "pessoa 93%". Por isso, quando o operador desenha o contorno
da estátua na calibração, a imagem ATUAL da câmera é guardada como a
aparência do monumento. Daí em diante, uma caixa "pessoa" sobre o contorno
só é tratada como a estátua se a imagem DENTRO DAQUELA CAIXA bater com a
mesma região da imagem da calibração — quem para NA FRENTE da estátua ocupa
a mesma posição, mas ali agora há outra imagem, e continua sendo pessoa.

(Comparar a caixa, e não o contorno inteiro: com o contorno inteiro, uma
pessoa cobrindo metade dele ainda "batia" pela outra metade.)

Vale para as duas análises: prints (detector) e vídeo contínuo
(live_analysis). Fica salvo em disco (sobrevive a reinício do backend).
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

WORK_WIDTH = 640                  # a imagem da calibração é guardada nesta largura (cinza)
PATCH_SIZE = (48, 96)             # (largura, altura) do recorte comparado
MATCH_NCC = 0.55                  # semelhança mínima pra ser a estátua
MATCH_OVERLAP = 0.6               # fração da caixa do YOLO dentro do contorno
_DIR = DATA_DIR / "statue_memory"
_DIR.mkdir(parents=True, exist_ok=True)

# código → {"box": frac, "gray": ndarray (WORK_WIDTH de largura), "ts", "version"}
_mem: dict[str, dict] = {}
_lock = threading.Lock()


def _gray(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    g = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if image.ndim == 3 else image
    return cv2.resize(g, (WORK_WIDTH, max(int(h * WORK_WIDTH / w), 1)), interpolation=cv2.INTER_AREA)


def _patch(gray: np.ndarray, box_frac: tuple) -> Optional[np.ndarray]:
    """Recorte (em frações da imagem) redimensionado e normalizado (média 0/desvio 1)."""
    h, w = gray.shape[:2]
    x1, y1, x2, y2 = (int(box_frac[0] * w), int(box_frac[1] * h), int(box_frac[2] * w), int(box_frac[3] * h))
    x1, y1, x2, y2 = max(x1, 0), max(y1, 0), min(x2, w), min(y2, h)
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    p = cv2.resize(gray[y1:y2, x1:x2], PATCH_SIZE, interpolation=cv2.INTER_AREA).astype(np.float32)
    return (p - p.mean()) / (p.std() + 1e-6)


def _box_px(box_frac: dict, w: int, h: int) -> tuple:
    return (int(box_frac["x_start"] * w), int(box_frac["y_start"] * h),
            int(box_frac["x_end"] * w), int(box_frac["y_end"] * h))


def _overlap_frac(a, b) -> float:
    """Fração da caixa `a` dentro da caixa `b`."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    return (ix2 - ix1) * (iy2 - iy1) / max((a[2] - a[0]) * (a[3] - a[1]), 1)


def save(camera_code: str, frame: np.ndarray, statue_frac: dict) -> dict:
    """Grava a imagem da calibração como aparência do monumento."""
    gray = _gray(frame)
    with _lock:
        version = _mem.get(camera_code, {}).get("version", 0) + 1
        _mem[camera_code] = {"box": dict(statue_frac), "gray": gray, "ts": time.time(), "version": version}
    cv2.imwrite(str(_DIR / f"{camera_code}.png"), gray)
    (_DIR / f"{camera_code}.json").write_text(json.dumps({"box": statue_frac, "ts": time.time()}), encoding="utf-8")
    # Imagem de conferência: o recorte que ficou como "a estátua"
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = _box_px(statue_frac, w, h)
    cv2.imwrite(str(_DIR / f"{camera_code}_estatua.jpg"), cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_RGB2BGR))
    logger.info(f"[estátua {camera_code}] aparência gravada a partir da calibração")
    return {"saved": True, "version": version}


def clear(camera_code: str) -> None:
    with _lock:
        _mem.pop(camera_code, None)
    for suffix in (".png", ".json", "_estatua.jpg"):
        try:
            (_DIR / f"{camera_code}{suffix}").unlink()
        except FileNotFoundError:
            pass


def get(camera_code: str) -> Optional[dict]:
    with _lock:
        m = _mem.get(camera_code)
        if m:
            return m
    png, meta = _DIR / f"{camera_code}.png", _DIR / f"{camera_code}.json"
    if not (png.exists() and meta.exists()):
        return None
    try:
        info = json.loads(meta.read_text(encoding="utf-8"))
        gray = cv2.imread(str(png), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            return None
        m = {"box": info["box"], "gray": gray, "ts": info.get("ts", 0), "version": 1}
    except Exception as e:
        logger.warning(f"[estátua {camera_code}] memória ilegível: {e}")
        return None
    with _lock:
        _mem.setdefault(camera_code, m)
    return m


def similarity(camera_code: Optional[str], bbox, image: np.ndarray) -> Optional[float]:
    """Semelhança (NCC, -1..1) entre a caixa na imagem atual e a MESMA região
    na imagem da calibração. None se não há calibração ou a caixa está
    fora do contorno da estátua."""
    m = get(camera_code) if camera_code else None
    if not m:
        return None
    h, w = image.shape[:2]
    if _overlap_frac(bbox, _box_px(m["box"], w, h)) < MATCH_OVERLAP:
        return None
    frac = (bbox[0] / w, bbox[1] / h, bbox[2] / w, bbox[3] / h)
    cur, ref = _patch(_gray(image), frac), _patch(m["gray"], frac)
    if cur is None or ref is None:
        return None
    return float((cur * ref).mean())


def is_statue(camera_code: Optional[str], bbox, image: np.ndarray) -> Optional[bool]:
    """True/False se há calibração pra câmera; None se não há (use outro critério)."""
    if not (camera_code and get(camera_code)):
        return None
    s = similarity(camera_code, bbox, image)
    return s is not None and s >= MATCH_NCC
