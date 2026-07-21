"""Rotas de detecção YOLO"""

import base64
import logging
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, File, UploadFile, HTTPException, Form

from app.schemas.schemas import DetectionResponse, DetectionResult, DetectedObject
from app.services.detection_service import DetectionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/detect", tags=["Detecção"])

detection_service: DetectionService = None


def init_routes(service: DetectionService):
    global detection_service
    detection_service = service


@router.post("", response_model=DetectionResponse)
async def detect_objects(
    file: UploadFile = File(...),
    confidence: Optional[float] = Form(None),
    camera_id: Optional[str] = Form("upload"),
):
    """Detecta objetos em uma imagem enviada"""
    if not detection_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")

    contents = await file.read()
    image = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Imagem inválida")

    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    result = detection_service.detect_full(image, camera_id, confidence)

    return DetectionResponse(
        success=True,
        result=DetectionResult(
            objects=[
                DetectedObject(**obj)
                for obj in result.get("yolo_detection", {}).get("objects", [])
            ],
            total_objects=result.get("yolo_detection", {}).get("total_objects", 0),
            counts=result.get("yolo_detection", {}).get("counts", {}),
            processing_time_ms=result.get("processing_time_ms", 0),
        ),
    )


@router.post("/full")
async def detect_full(
    file: UploadFile = File(...),
    confidence: Optional[float] = Form(None),
    camera_id: Optional[str] = Form("upload"),
    include_annotated: Optional[bool] = Form(False),
):
    """Pipeline completo: YOLO + Vandalismo + HF"""
    if not detection_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")

    contents = await file.read()
    image = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Imagem inválida")

    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    result = detection_service.detect_full(image, camera_id, confidence)

    # Converte imagem anotada para base64 se solicitado
    if include_annotated and "annotated_image" in result:
        _, buffer = cv2.imencode(".jpg", cv2.cvtColor(result["annotated_image"], cv2.COLOR_RGB2BGR))
        result["annotated_image_base64"] = base64.b64encode(buffer).decode("utf-8")
        del result["annotated_image"]

    return {"success": True, **result}


@router.get("/models")
async def models_status():
    """Status de todos os modelos carregados"""
    if not detection_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")

    return {"success": True, "models": detection_service.get_models_status()}
