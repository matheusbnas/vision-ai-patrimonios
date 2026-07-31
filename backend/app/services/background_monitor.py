"""
Monitoramento contínuo em background: varre TODAS as câmeras dos
patrimônios (não só as que estão selecionadas no frontend), sequencialmente
— uma câmera por vez, para não sobrecarregar a máquina que roda YOLO/HF.

Assim o sistema fica de olho o tempo todo, mesmo com ninguém olhando a
página de Monitoramento; qualquer risk_alert (YOLO/preditivo) ou alert
(SSIM/mudança física) vira um registro em alert_service, consultável via
GET /api/alerts.
"""

import asyncio
import logging

from app.config import (
    PATRIMONIOS,
    BACKGROUND_MONITOR_ENABLED,
    BACKGROUND_MONITOR_INTERVAL_SECONDS,
)
from app.api import monitor as monitor_api

logger = logging.getLogger(__name__)


def _all_camera_codes() -> list[str]:
    codes: list[str] = []
    for p in PATRIMONIOS:
        for code in p.get("camera_codes", []):
            if code not in codes:
                codes.append(code)
    return codes


def _process_camera(code: str) -> None:
    """Captura + detecta + registra alertas de uma câmera (síncrono, roda em thread)."""
    camera_service = monitor_api.camera_service
    detection_service = monitor_api.detection_service
    change_detector = monitor_api.change_detector

    camera = camera_service.get_camera_by_code(code)
    camera_name = camera.get("name", f"Câmera {code}") if camera else f"Câmera {code}"
    stream_url = (camera.get("stream_url") if camera else None) or camera_service.get_stream_url(code)
    if not stream_url:
        logger.debug(f"[background_monitor] Sem stream_url pra câmera {code}, pulando")
        return

    frame = monitor_api.capture_frame(stream_url, 15.0)
    if frame is None:
        logger.debug(f"[background_monitor] Falha ao capturar frame da câmera {code}")
        return

    monitor_api.save_camera_snapshot(frame, code, camera_name, "monitoramento")

    result = detection_service.detect_full(frame, camera_id=code)
    risk_alert = result.get("risk_alert")
    monitor_api.record_risk_alert(code, camera_name, risk_alert)

    # Garante que toda câmera tenha uma referência SSIM — sem isso, mudança
    # física (pichação, dano, peça removida) nunca gera alerta pra essa câmera.
    if code not in change_detector.monitored:
        change_detector.set_reference(code, frame, detection_service)
        logger.info(f"[background_monitor] Referência SSIM criada automaticamente para câmera {code}")
    else:
        change_result = change_detector.check(code, frame, detection_service)
        if change_result.get("success"):
            monitor_api.record_ssim_alert(code, camera_name, change_result.get("alert"))


async def run_forever() -> None:
    """Loop infinito: varre todas as câmeras, uma por vez, com pausa entre elas."""
    codes = _all_camera_codes()
    if not codes:
        logger.warning("[background_monitor] Nenhuma câmera configurada em PATRIMONIOS, loop não iniciado")
        return

    logger.info(f"[background_monitor] Iniciado — {len(codes)} câmeras, intervalo {BACKGROUND_MONITOR_INTERVAL_SECONDS}s")
    loop = asyncio.get_event_loop()

    while True:
        for code in codes:
            try:
                await loop.run_in_executor(None, _process_camera, code)
            except Exception as e:
                logger.warning(f"[background_monitor] Erro processando câmera {code}: {e}")
            await asyncio.sleep(BACKGROUND_MONITOR_INTERVAL_SECONDS)


def start() -> "asyncio.Task | None":
    """Cria a task de monitoramento contínuo, se habilitado."""
    if not BACKGROUND_MONITOR_ENABLED:
        logger.info("[background_monitor] Desabilitado (BACKGROUND_MONITOR_ENABLED=false)")
        return None
    return asyncio.create_task(run_forever())
