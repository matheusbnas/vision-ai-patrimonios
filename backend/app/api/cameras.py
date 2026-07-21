"""Rotas de câmeras"""

import logging
from fastapi import APIRouter, HTTPException, Query

from app.schemas.schemas import CameraListResponse, Camera
from app.services.camera_service import CameraService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cameras", tags=["Câmeras"])

camera_service: CameraService = None


def init_routes(service: CameraService):
    global camera_service
    camera_service = service


@router.get("", response_model=CameraListResponse)
async def list_cameras():
    """Lista todas as câmeras disponíveis"""
    if not camera_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")

    cameras = camera_service.get_all_cameras()
    return CameraListResponse(
        success=True,
        cameras=[Camera.model_validate(cam) for cam in cameras],
        total=len(cameras),
    )


@router.post("/by-codes")
async def get_cameras_by_codes(codes: list[str]):
    """Busca múltiplas câmeras por seus códigos"""
    if not camera_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")

    all_cameras = camera_service.get_all_cameras()
    found = []
    for code in codes:
        code = code.strip()
        cam = camera_service.get_camera_by_code(code)
        if cam:
            # Tenta obter stream_url
            stream_url = cam.get("stream_url")
            if not stream_url:
                stream_url = camera_service.get_stream_url(code)
            cam["stream_url"] = stream_url or ""
            found.append(Camera.model_validate(cam))
        else:
            found.append(Camera.model_validate({
                "code": code,
                "name": f"Câmera {code}",
                "id": 0,
                "latitude": None,
                "longitude": None,
            }))

    return {"success": True, "cameras": found, "total": len(found)}


@router.get("/{camera_code}")
async def get_camera(camera_code: str):
    """Obtém detalhes de uma câmera específica"""
    if not camera_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")

    camera = camera_service.get_camera_by_code(camera_code)
    if not camera:
        raise HTTPException(status_code=404, detail="Câmera não encontrada")

    stream_url = camera_service.get_stream_url(camera_code)
    return {
        "success": True,
        "camera": camera,
        "stream_url": stream_url,
    }


@router.get("/{camera_code}/stream")
async def get_camera_stream(camera_code: str):
    """Obtém URL de stream para uma câmera"""
    if not camera_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")

    url = camera_service.get_stream_url(camera_code)
    if not url:
        raise HTTPException(status_code=404, detail="Stream não disponível")

    return {"success": True, "stream_url": url}


@router.get("/health/check")
async def health_check():
    """Verifica saúde da conexão com a API de câmeras"""
    if not camera_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")

    return camera_service.check_health()
