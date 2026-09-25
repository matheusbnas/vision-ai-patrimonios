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

from app.config import NOTIFY_COOLDOWN_SECONDS

logger = logging.getLogger(__name__)

MAX_ALERTS = 500
# O mesmo alerta (câmera + origem + nível) não entra de novo no histórico
# antes disto — a análise contínua avalia 2x/s e registraria o mesmo
# "pessoa em cima da estátua" dezenas de vezes seguidas.
DEDUP_SECONDS = 60

# (camera, source, level) → último alerta registrado
_last_stored: dict[tuple[str, str, str], dict] = {}

_LEVEL_RANK = {"MODERADO": 1, "ALTO": 2, "CRÍTICO": 3}

# Quais alertas viram notificação na tela (som + mensagem). O resto fica
# só no histórico/painel — senão o operador se acostuma a ignorar o som.
#   interaction: qualquer nível (mão na área sensível, pessoa em cima)
#   risk:        objeto de risco encostado na estátua, ALTO+ (faca/tesoura, ou permanência)
#   ssim:        mudança física na estátua, ALTO+
#   loitering:   nunca (informativo)
_NOTIFY_MIN_LEVEL = {"interaction": 1, "risk": 2, "ssim": 2}

# (camera, source) → (timestamp, nível) da última notificação
_last_notified: dict[tuple[str, str], tuple[float, int]] = {}


def _should_notify(camera_code: str, source: str, level: str) -> bool:
    rank = _LEVEL_RANK.get(level, 0)
    if rank < _NOTIFY_MIN_LEVEL.get(source, 99):
        return False
    key = (camera_code, source)
    last = _last_notified.get(key)
    now = time.time()
    # Mesmo tipo de alerta há pouco tempo: não repete — a não ser que o
    # nível tenha subido (ex.: MODERADO → ALTO → CRÍTICO).
    if last and now - last[0] < NOTIFY_COOLDOWN_SECONDS and rank <= last[1]:
        return False
    _last_notified[key] = (now, rank)
    return True

_alerts: list[dict] = []
_lock = threading.Lock()
_id_counter = itertools.count(1)


def add_alert(camera_code: str, camera_name: str, level: str, message: str,
              source: str, objects: Optional[list[str]] = None) -> dict:
    """Registra um novo alerta e retorna o registro criado."""
    key = (camera_code, source, level)
    with _lock:
        prev = _last_stored.get(key)
        if prev and time.time() - prev["timestamp"] < DEDUP_SECONDS:
            return prev
        notify = _should_notify(camera_code, source, level)
    entry = {
        "id": next(_id_counter),
        "timestamp": time.time(),
        "camera_code": camera_code,
        "camera_name": camera_name,
        "level": level,
        "message": message,
        # "risk" (objeto de risco), "interaction" (pose), "loitering"
        # (presença contínua) ou "ssim" (mudança física)
        "source": source,
        "objects": objects or [],
        "notify": notify,  # true = frontend toca som + mostra mensagem
    }
    with _lock:
        _last_stored[key] = entry
        _alerts.append(entry)
        if len(_alerts) > MAX_ALERTS:
            del _alerts[: len(_alerts) - MAX_ALERTS]
    logger.info(f"🚨 Alerta registrado: {camera_code} [{level}] {message}")
    return entry


def get_alerts(since: Optional[float] = None, camera_code: Optional[str] = None,
               level: Optional[str] = None, limit: int = 100,
               after_id: Optional[int] = None, notify_only: bool = False) -> list[dict]:
    """Consulta alertas, mais recentes primeiro, com filtros opcionais."""
    with _lock:
        results = list(_alerts)

    if after_id is not None:
        results = [a for a in results if a["id"] > after_id]
    if notify_only:
        results = [a for a in results if a["notify"]]
    if since is not None:
        results = [a for a in results if a["timestamp"] >= since]
    if camera_code:
        results = [a for a in results if a["camera_code"] == camera_code]
    if level:
        results = [a for a in results if a["level"] == level]

    results.sort(key=lambda a: a["timestamp"], reverse=True)
    return results[:limit]


def last_id() -> int:
    with _lock:
        return _alerts[-1]["id"] if _alerts else 0
