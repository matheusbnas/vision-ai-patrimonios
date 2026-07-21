"""Rotas de análise de vandalismo e modelos Hugging Face"""

import base64
import logging
import time
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, File, UploadFile, HTTPException, Form

from app.schemas.schemas import (
    VandalismResponse,
    VandalismAnalysis,
    RiskFactor,
    VandalismAlert,
    HFInferenceRequest,
    HFInferenceResult,
    HFModelInfo,
)
from app.services.detection_service import DetectionService
from app.services.camera_service import CameraService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/vandalism", tags=["Vandalismo"])

detection_service: DetectionService = None


def init_routes(service: DetectionService):
    global detection_service
    detection_service = service


@router.post("/analyze", response_model=VandalismResponse)
async def analyze_vandalism(
    file: UploadFile = File(...),
    camera_id: Optional[str] = Form("unknown"),
    confidence: Optional[float] = Form(None),
):
    """Analisa uma imagem em busca de sinais de vandalismo"""
    if not detection_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")

    contents = await file.read()
    image = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Imagem inválida")

    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    # Detecta objetos primeiro
    yolo_result = detection_service.yolo_detector.detect(image, confidence)
    objects = yolo_result.get("objects", [])

    # Analisa vandalismo
    analysis = detection_service.vandalism_detector.analyze(
        objects, camera_id, confidence
    )

    return VandalismResponse(
        success=True,
        analysis=VandalismAnalysis(
            risk_score=analysis.get("risk_score", 0),
            risk_level=analysis.get("risk_level", "BAIXO"),
            risk_factors=[
                RiskFactor(**rf) for rf in analysis.get("risk_factors", [])
            ],
            alerts=[
                VandalismAlert(**alert) for alert in analysis.get("alerts", [])
            ],
            person_count=analysis.get("person_count", 0),
            vehicle_count=analysis.get("vehicle_count", 0),
            total_objects=analysis.get("total_objects", 0),
            has_vandal_tools=analysis.get("has_vandal_tools", False),
            vandal_tools=analysis.get("vandal_tools", []),
        ),
    )


@router.post("/hf-predict")
async def hf_predict(
    file: UploadFile = File(...),
    model_type: str = Form("vandalism"),
):
    """
    Usa o modelo do Hugging Face para classificar a imagem/vídeo.

    Args:
        file: Arquivo de imagem ou vídeo
        model_type: "vandalism" para KzRyan/Burglary_and_Vandalism,
                    "damage" para dolphinium/damaged-building-detection
    """
    if not detection_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")

    start = time.time()
    contents = await file.read()

    if model_type == "vandalism":
        model = detection_service.hf_vandalism
        if not model.model_loaded:
            raise HTTPException(status_code=503, detail="Modelo HF não carregado")

        # Tenta detectar se é vídeo ou imagem pela extensão
        filename = file.filename or ""
        is_video = any(ext in filename.lower() for ext in [".mp4", ".avi", ".mov", ".mkv"])

        if is_video:
            # Salva temporariamente o vídeo
            import tempfile
            import os
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp:
                tmp.write(contents)
                tmp_path = tmp.name
            try:
                result = model.predict_video(tmp_path)
            finally:
                os.unlink(tmp_path)
        else:
            image = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise HTTPException(status_code=400, detail="Imagem inválida")
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            result = model.predict_image(image)

        elapsed = (time.time() - start) * 1000

        return HFInferenceResult(
            success=True,
            predictions=result,
            model_used="KzRyan/Burglary_and_Vandalism",
            processing_time_ms=round(elapsed, 2),
        )

    elif model_type == "damage":
        model = detection_service.hf_damage
        if not model.model_loaded:
            raise HTTPException(status_code=503, detail="Modelo de danos não carregado")

        image = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(status_code=400, detail="Imagem inválida")
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        result = model.predict(image)
        elapsed = (time.time() - start) * 1000

        return HFInferenceResult(
            success=True,
            predictions=result,
            model_used="dolphinium/damaged-building-detection",
            processing_time_ms=round(elapsed, 2),
        )

    raise HTTPException(status_code=400, detail=f"Tipo de modelo inválido: {model_type}")


@router.get("/hf-models")
async def hf_models_info():
    """Informações sobre os modelos Hugging Face carregados"""
    if not detection_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")

    return {
        "success": True,
        "models": [
            detection_service.hf_vandalism.get_info(),
            detection_service.hf_damage.get_info(),
        ],
    }
