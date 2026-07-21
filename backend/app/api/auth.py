"""Rotas de autenticação"""

import logging
from fastapi import APIRouter, HTTPException

from app.schemas.schemas import LoginRequest, LoginResponse
from app.services.camera_service import CameraService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Autenticação"])

# Instância global do serviço (compartilhada)
camera_service: CameraService = None  # Será injetada pelo main


def init_routes(service: CameraService):
    """Inicializa as rotas com o serviço"""
    global camera_service
    camera_service = service


@router.post("/login", response_model=LoginResponse)
async def login():
    """Autentica na API de câmeras"""
    if not camera_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")

    success = camera_service.authenticate()
    if success:
        return LoginResponse(
            success=True,
            access_token=camera_service.token,
            message="Autenticado com sucesso",
        )
    raise HTTPException(
        status_code=401,
        detail="Falha na autenticação. Verifique as credenciais.",
    )


@router.get("/status")
async def auth_status():
    """Verifica status da autenticação"""
    if not camera_service:
        return {"authenticated": False, "message": "Serviço não inicializado"}

    has_token = bool(camera_service.token and camera_service.token_expires_at)
    is_valid = has_token and (time.time() < camera_service.token_expires_at) if has_token else False

    return {
        "authenticated": is_valid,
        "has_token": has_token,
        "message": "Autenticado" if is_valid else "Não autenticado",
    }


import time  # noqa: E402 (import after usage)
