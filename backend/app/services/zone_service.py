"""
Serviço de calibração do quadrante (zona de foco no monumento) por câmera.

Persiste em um JSON simples (data/camera_zones.json) o retângulo
(frações 0-1 da largura/altura) que cada câmera usa para restringir
o SSIM (change_detector) e o filtro de risco do YOLO (detector) à
área onde o monumento realmente aparece naquele enquadramento.

Câmeras sem calibração custom caem no retângulo padrão (ROI_* do config.py).
"""

import json
import logging
import threading
from typing import Optional

from app.config import (
    DATA_DIR,
    ROI_X_START,
    ROI_X_END,
    ROI_Y_START,
    ROI_Y_END,
)

logger = logging.getLogger(__name__)

ZONES_FILE = DATA_DIR / "camera_zones.json"
_lock = threading.Lock()


def _default_zone() -> dict:
    return {
        "x_start": ROI_X_START,
        "x_end": ROI_X_END,
        "y_start": ROI_Y_START,
        "y_end": ROI_Y_END,
    }


def _load() -> dict:
    if not ZONES_FILE.exists():
        return {}
    try:
        with open(ZONES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Erro ao ler {ZONES_FILE}: {e}")
        return {}


def _save(data: dict) -> None:
    with open(ZONES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_zone(camera_code: Optional[str]) -> dict:
    """Retorna a zona calibrada da câmera, ou o padrão se não houver."""
    if not camera_code:
        return _default_zone()
    zones = _load()
    return zones.get(camera_code, _default_zone())


def is_custom(camera_code: str) -> bool:
    return camera_code in _load()


def set_zone(camera_code: str, zone: dict) -> dict:
    """Valida e salva a zona calibrada de uma câmera."""
    x_start, x_end = zone["x_start"], zone["x_end"]
    y_start, y_end = zone["y_start"], zone["y_end"]

    if not (0 <= x_start < x_end <= 1):
        raise ValueError("x_start/x_end inválidos (esperado 0 <= x_start < x_end <= 1)")
    if not (0 <= y_start < y_end <= 1):
        raise ValueError("y_start/y_end inválidos (esperado 0 <= y_start < y_end <= 1)")

    normalized = {
        "x_start": round(x_start, 4),
        "x_end": round(x_end, 4),
        "y_start": round(y_start, 4),
        "y_end": round(y_end, 4),
    }

    with _lock:
        zones = _load()
        zones[camera_code] = normalized
        _save(zones)

    logger.info(f"Zona calibrada para câmera {camera_code}: {normalized}")
    return normalized


def reset_zone(camera_code: str) -> dict:
    """Remove a calibração custom da câmera, voltando ao padrão."""
    with _lock:
        zones = _load()
        if camera_code in zones:
            del zones[camera_code]
            _save(zones)
    return _default_zone()
