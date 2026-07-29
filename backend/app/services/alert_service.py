"""
Store de alertas em memória — histórico consultável via API (`/api/alerts`)
para que outros sistemas já em produção possam buscar os alertas gerados
pelo monitoramento (preditivo/YOLO ou por mudança/SSIM).
"""

import itertools
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

MAX_ALERTS = 500

_alerts: list[dict] = []
_lock = threading.Lock()
_id_counter = itertools.count(1)


def add_alert(camera_code: str, camera_name: str, level: str, message: str,
              source: str, objects: Optional[list[str]] = None) -> dict:
    """Registra um novo alerta e retorna o registro criado."""
    entry = {
        "id": next(_id_counter),
        "timestamp": time.time(),
        "camera_code": camera_code,
        "camera_name": camera_name,
        "level": level,
        "message": message,
        "source": source,  # "risk" (YOLO/preditivo) ou "ssim" (mudança física)
        "objects": objects or [],
    }
    with _lock:
        _alerts.append(entry)
        if len(_alerts) > MAX_ALERTS:
            del _alerts[: len(_alerts) - MAX_ALERTS]
    logger.info(f"🚨 Alerta registrado: {camera_code} [{level}] {message}")
    return entry


def get_alerts(since: Optional[float] = None, camera_code: Optional[str] = None,
               level: Optional[str] = None, limit: int = 100) -> list[dict]:
    """Consulta alertas, mais recentes primeiro, com filtros opcionais."""
    with _lock:
        results = list(_alerts)

    if since is not None:
        results = [a for a in results if a["timestamp"] >= since]
    if camera_code:
        results = [a for a in results if a["camera_code"] == camera_code]
    if level:
        results = [a for a in results if a["level"] == level]

    results.sort(key=lambda a: a["timestamp"], reverse=True)
    return results[:limit]
