"""Rotas de análise de vandalismo e modelos Hugging Face"""

import base64
import logging
import time
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, File, UploadFile, HTTPException, Form

from app.schemas.schemas import (
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


_VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".webm", ".3gp", ".m4v")
# Vídeo com menos movimento que isto (diferença média entre frames) é
# praticamente uma imagem parada — mesma confiabilidade baixa
MIN_VIDEO_MOTION = 1.0
# Menor lado aceito — abaixo disso não há como ver pessoa nem cena
MIN_SIDE_PX = 64


def _read_video_frames(path: str, n: int = 5, max_side: int = 960) -> list[np.ndarray]:
    """Alguns frames espalhados pelo vídeo, em resolução boa pro porteiro (YOLO)."""
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) if cap.isOpened() else 0
    frames = []
    for idx in np.linspace(0, max(total - 1, 0), min(n, max(total, 1)), dtype=int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, f = cap.read()
        if not ok:
            continue
        h, w = f.shape[:2]
        s = min(max_side / max(h, w), 1.0)
        if s < 1:
            f = cv2.resize(f, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
    cap.release()
    return frames


@router.post("/hf-predict")
async def hf_predict(
    file: UploadFile = File(...),
    model_type: str = Form("vandalism"),
):
    """
    Classifica imagem/vídeo com o KzRyan/Burglary_and_Vandalism — depois de
    passar pelo porteiro de domínio (scene_gate): gráfico, documento, print
    de tela, desenho ou cena sem pessoas NÃO são classificados, porque o
    modelo sempre responde uma das 3 classes, mesmo para o que não é cena
    de câmera.

    Resposta: `domain` (veredito do porteiro), `classified`, `predictions`
    (só se classificado), `reliability` ("baixa" p/ imagem ou vídeo parado,
    "media" p/ vídeo com movimento) e `interpretation`.
    """
    if not detection_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")
    if model_type != "vandalism":
        raise HTTPException(status_code=400, detail=f"Tipo de modelo inválido: {model_type}")

    from starlette.concurrency import run_in_threadpool
    from app.models import scene_gate

    start = time.time()
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Arquivo vazio")

    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()
    is_video = content_type.startswith("video/") or filename.endswith(_VIDEO_EXTS)

    tmp_path = None
    try:
        if is_video:
            import os
            import tempfile
            suffix = os.path.splitext(filename)[1] or ".mp4"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(contents)
                tmp_path = tmp.name
            frames = await run_in_threadpool(_read_video_frames, tmp_path)
            if not frames:
                raise HTTPException(status_code=400, detail="Não foi possível ler o vídeo (formato não suportado ou arquivo corrompido)")
        else:
            image = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise HTTPException(status_code=400, detail="Arquivo não é uma imagem válida (use JPG, PNG, WEBP, BMP...)")
            frames = [cv2.cvtColor(image, cv2.COLOR_BGR2RGB)]
        if min(frames[0].shape[:2]) < MIN_SIDE_PX:
            raise HTTPException(status_code=400, detail=f"Imagem muito pequena para análise (mínimo {MIN_SIDE_PX}px de lado)")

        # ─── 1. Porteiro de domínio ────────────────────────────────
        domain = await run_in_threadpool(scene_gate.check_frames, frames)
        motion = scene_gate.motion_level(frames) if is_video else 0.0
        base = {
            "success": True,
            "media_type": "video" if is_video else "image",
            "domain": domain,
            "model_used": "KzRyan/Burglary_and_Vandalism",
        }
        if domain["verdict"] != "cena":
            return {**base, "classified": False, "predictions": None, "reliability": None,
                    "interpretation": domain["reason"],
                    "processing_time_ms": round((time.time() - start) * 1000, 2)}

        # ─── 2. Classificação ──────────────────────────────────────
        model = detection_service.hf_vandalism
        if not model.model_loaded:
            await run_in_threadpool(model.load_model)
        if not model.model_loaded:
            raise HTTPException(status_code=503, detail="Modelo HF não carregado")

        if is_video:
            result = await run_in_threadpool(model.predict_video, tmp_path)
        else:
            result = await run_in_threadpool(model.predict_image, frames[0])
        if "error" in result:
            raise HTTPException(status_code=500, detail=f"Erro na inferência: {result['error']}")

        still = (not is_video) or motion < MIN_VIDEO_MOTION
        reliability = "baixa" if still else "media"
        top = max(result, key=result.get)
        if still:
            interpretation = (
                "Resultado apenas indicativo: o modelo foi treinado com VÍDEO (movimento entre "
                "frames) e aqui recebeu uma imagem parada. Não use como evidência — confirme "
                "por um vídeo ou pelo operador.")
        elif top == "normal":
            interpretation = "O modelo não identificou roubo ou vandalismo neste vídeo."
        else:
            nome = {"burglary": "roubo/furto", "vandalism": "vandalismo"}[top]
            interpretation = (f"O modelo indica possível {nome} ({result[top] * 100:.0f}%). "
                              "É um indício para validação humana, não uma confirmação.")

        return {**base, "classified": True, "predictions": result, "reliability": reliability,
                "motion": motion if is_video else None, "top_class": top,
                "interpretation": interpretation,
                "processing_time_ms": round((time.time() - start) * 1000, 2)}
    finally:
        if tmp_path:
            import os
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@router.get("/hf-models")
async def hf_models_info():
    """Informações sobre os modelos Hugging Face carregados"""
    if not detection_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")

    return {
        "success": True,
        "models": [
            detection_service.hf_vandalism.get_info(),
        ],
    }
