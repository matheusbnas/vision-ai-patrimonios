"""
Porteiro de domínio para o classificador de vandalismo (Hugging Face).

O KzRyan/Burglary_and_Vandalism só conhece 3 respostas (normal / roubo /
vandalismo) e SEMPRE distribui 100% entre elas — um gráfico, um print de
site ou a foto de um gato também saem com "80% vandalismo". Antes de
classificar, este módulo responde: isto é uma cena de câmera com pessoas?

  1. Arte gráfica (gráfico, documento digital, print de tela, desenho):
     fundo de cor idêntica em boa parte da imagem e áreas perfeitamente
     lisas. Foto real — mesmo com céu liso — tem ruído/gradiente e quase
     nenhum pixel exatamente igual ao vizinho. Calibrado com gráficos,
     prints, desenhos, fotos variadas e frames das câmeras do COR
     (cor mais frequente: arte ≥ 0,38 × foto ≤ 0,04).
  2. Pessoas na cena (YOLO): roubo e vandalismo são ações de pessoas —
     sem ninguém no quadro, a classificação não se aplica.

Só uma cena real com pessoas segue para o modelo.
"""

import logging
import threading
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.config import YOLO_MODEL

logger = logging.getLogger(__name__)

# Fração da imagem ocupada pela cor exata mais frequente acima da qual é arte gráfica
GRAPHIC_TOP_COLOR = 0.2
# Critério alternativo: poucas cores dominantes + muita área lisa + fundo quase uniforme
GRAPHIC_TOP8 = 0.7
GRAPHIC_FLAT = 0.45
GRAPHIC_TOP_COLOR_TOL = 0.3
PERSON_CONF = 0.35

_yolo = None
_yolo_lock = threading.Lock()


def _model():
    """YOLO próprio do porteiro — o do detection_service é usado pela thread
    de monitoramento em background e o ultralytics não é thread-safe."""
    global _yolo
    if _yolo is None:
        from ultralytics import YOLO
        _yolo = YOLO(str(Path(YOLO_MODEL)))
    return _yolo


def graphic_metrics(rgb: np.ndarray) -> dict:
    h, w = rgb.shape[:2]
    s = 512 / max(h, w)
    # NEAREST preserva cores exatas (interpolação criaria tons intermediários)
    img = cv2.resize(rgb, (max(int(w * s), 1), max(int(h * s), 1)),
                     interpolation=cv2.INTER_NEAREST) if s < 1 else rgb
    n = img.shape[0] * img.shape[1]

    exact = (img[..., 0].astype(np.int64) << 16) | (img[..., 1].astype(np.int64) << 8) | img[..., 2]
    top_color = np.unique(exact, return_counts=True)[1].max() / n

    q = (img // 6).astype(np.int64)  # tolerância ±~3 por canal (JPEG)
    tol = (q[..., 0] << 16) | (q[..., 1] << 8) | q[..., 2]
    top_color_tol = np.unique(tol, return_counts=True)[1].max() / n

    q8 = (img >> 3).astype(np.int64)
    coarse = (q8[..., 0] << 10) | (q8[..., 1] << 5) | q8[..., 2]
    top8 = np.sort(np.bincount(coarse.ravel()))[::-1][:8].sum() / n

    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    k = np.ones((5, 5), np.uint8)
    flat = float(((cv2.dilate(gray, k).astype(int) - cv2.erode(gray, k).astype(int)) <= 2).mean())

    is_graphic = top_color >= GRAPHIC_TOP_COLOR or (
        top8 >= GRAPHIC_TOP8 and flat >= GRAPHIC_FLAT and top_color_tol >= GRAPHIC_TOP_COLOR_TOL)
    return {
        "is_graphic": bool(is_graphic),
        "top_color": round(float(top_color), 3),
        "top_color_tol": round(float(top_color_tol), 3),
        "top8": round(float(top8), 3),
        "flat": round(flat, 3),
    }


def detect_people(rgb: np.ndarray) -> dict:
    with _yolo_lock:
        m = _model()
        r = m(rgb, conf=PERSON_CONF, verbose=False)[0]
    names = [m.names[int(c)] for c in r.boxes.cls]
    boxes = r.boxes.xyxy.cpu().numpy().astype(int).tolist() if len(names) else []
    people = [b for b, name in zip(boxes, names) if name == "person"]
    counts: dict[str, int] = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    return {"people": len(people), "people_boxes": people, "objects": counts}


def check_frames(frames: list[np.ndarray]) -> dict:
    """
    Avalia um ou mais frames (RGB). Para vídeo, passe alguns frames
    espalhados: é arte gráfica pelo frame do meio; tem pessoa se aparecer
    em qualquer um deles.

    Devolve {"verdict": "cena" | "grafico" | "sem_pessoas", "reason", ...}.
    """
    mid = frames[len(frames) // 2]
    g = graphic_metrics(mid)
    if g["is_graphic"]:
        return {
            "verdict": "grafico",
            "reason": ("A imagem parece um gráfico, documento digital, print de tela ou desenho — "
                       "não é uma cena de câmera. O modelo de vandalismo não se aplica."),
            "graphic": g, "people": 0, "objects": {},
        }

    best: Optional[dict] = None
    for f in frames:
        p = detect_people(f)
        if best is None or p["people"] > best["people"]:
            best = p
    if not best or best["people"] == 0:
        return {
            "verdict": "sem_pessoas",
            "reason": ("Nenhuma pessoa detectada na cena. Este modelo reconhece a AÇÃO de roubo ou "
                       "vandalismo, feita por pessoas — sem ninguém no quadro, não se aplica. Dano ou "
                       "pichação já feitos num monumento são detectados no Monitoramento, pela "
                       "comparação com a imagem de referência da câmera."),
            "graphic": g, "people": 0, "objects": best["objects"] if best else {},
        }
    return {
        "verdict": "cena",
        "reason": f"Cena real com {best['people']} pessoa(s) detectada(s).",
        "graphic": g, "people": best["people"], "objects": best["objects"],
        "people_boxes": best["people_boxes"],
    }


def motion_level(frames: list[np.ndarray]) -> float:
    """Diferença média entre frames seguidos (0-255) — vídeo parado ≈ imagem estática."""
    if len(frames) < 2:
        return 0.0
    diffs = []
    for a, b in zip(frames, frames[1:]):
        ga = cv2.cvtColor(cv2.resize(a, (320, 180)), cv2.COLOR_RGB2GRAY).astype(np.float32)
        gb = cv2.cvtColor(cv2.resize(b, (320, 180)), cv2.COLOR_RGB2GRAY).astype(np.float32)
        diffs.append(float(np.abs(ga - gb).mean()))
    return round(float(np.mean(diffs)), 2)
