"""
Rastreia há quanto tempo cada classe de objeto de risco está presente
dentro da zona de um monumento, por câmera.

O YOLO não faz re-identificação de objeto entre frames — a aproximação
prática usada aqui é por presença de CLASSE: se "faca" aparece dentro da
zona da câmera X em varreduras sucessivas, consideramos que é (aproximadamente)
o mesmo objeto ali parado. Se a classe sumir de uma varredura, o timer reseta.
"""

import logging
import threading
import time
from typing import Dict, Set, Tuple

logger = logging.getLogger(__name__)

_first_seen: Dict[Tuple[str, str], float] = {}
_lock = threading.Lock()


def update(camera_code: str, classes_presentes: Set[str]) -> Dict[str, float]:
    """
    Atualiza os timers de permanência para uma câmera.

    Args:
        camera_code: código da câmera
        classes_presentes: conjunto de classes de risco detectadas
            dentro da zona nesta varredura (vazio se nenhuma)

    Returns:
        dict {classe: segundos_de_permanencia} apenas para as classes
        presentes nesta varredura.
    """
    now = time.time()
    dwell: Dict[str, float] = {}

    with _lock:
        # Remove timers de classes que não estão mais presentes (reseta)
        for key in [k for k in _first_seen if k[0] == camera_code and k[1] not in classes_presentes]:
            del _first_seen[key]

        for classe in classes_presentes:
            key = (camera_code, classe)
            if key not in _first_seen:
                _first_seen[key] = now
            dwell[classe] = now - _first_seen[key]

    return dwell


def reset(camera_code: str) -> None:
    """Limpa todos os timers de uma câmera (ex.: quando ela some do ciclo de monitoramento)."""
    with _lock:
        for key in [k for k in _first_seen if k[0] == camera_code]:
            del _first_seen[key]
