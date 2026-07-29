"""
API de consulta de alertas — pensada para outros sistemas já em produção
consultarem periodicamente os alertas gerados pelo monitoramento
(preditivo/YOLO ou por mudança física/SSIM).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query

from app.services import alert_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/alerts", tags=["Alertas"])


@router.get("")
async def list_alerts(
    since: Optional[float] = Query(None, description="Timestamp unix — só alertas a partir daqui"),
    camera_code: Optional[str] = Query(None, description="Filtra por câmera"),
    level: Optional[str] = Query(None, description="Filtra por nível: MODERADO, ALTO ou CRÍTICO"),
    limit: int = Query(100, ge=1, le=500, description="Máximo de alertas retornados"),
):
    """Lista os alertas mais recentes, com filtros opcionais."""
    alerts = alert_service.get_alerts(since=since, camera_code=camera_code, level=level, limit=limit)
    return {
        "success": True,
        "total": len(alerts),
        "alerts": alerts,
    }
