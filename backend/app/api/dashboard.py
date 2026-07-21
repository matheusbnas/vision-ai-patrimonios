"""Rotas do dashboard"""

import logging
from datetime import datetime

from fastapi import APIRouter

from app.config import PATRIMONIOS
from app.schemas.schemas import (
    DashboardResponse,
    DashboardStats,
    PatrimonySummary,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardResponse)
async def get_dashboard_stats():
    """Estatísticas gerais do dashboard"""
    stats = DashboardStats(
        total_patrimonios=len(PATRIMONIOS),
        total_cameras=0,
        cameras_online=0,
        alertas_ativos=0,
        deteccoes_hoje=0,
        patrimonio_mais_visivel=PATRIMONIOS[0]["nome"] if PATRIMONIOS else None,
        nivel_risco_medio=0.0,
    )

    patrimonios = [
        PatrimonySummary(
            id=p["id"],
            nome=p["nome"],
            emoji=p["emoji"],
            bairro=p["bairro"],
            categoria=p["categoria"],
            status="monitorado",
            nivel_risco=0.0,
        )
        for p in PATRIMONIOS
    ]

    return DashboardResponse(
        success=True,
        stats=stats,
        patrimonios=patrimonios,
        alertas_recentes=[],
    )


@router.get("/patrimonios")
async def list_patrimonios():
    """Lista todos os patrimônios monitorados"""
    return {
        "success": True,
        "patrimonios": PATRIMONIOS,
        "total": len(PATRIMONIOS),
    }


@router.get("/patrimonios/{patrimonio_id}")
async def get_patrimonio(patrimonio_id: int):
    """Detalhes de um patrimônio específico"""
    for p in PATRIMONIOS:
        if p["id"] == patrimonio_id:
            return {"success": True, "patrimonio": p}
    return {"success": False, "error": "Patrimônio não encontrado"}
