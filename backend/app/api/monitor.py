"""
Rotas de monitoramento ao vivo com detecção em tempo real.
Captura frames do stream Tixxi, processa com YOLO + HF e retorna análise.
"""

import base64
import logging
import time
from io import BytesIO
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.services.camera_service import CameraService
from app.services.detection_service import DetectionService
from app.models.change_detector import ChangeDetector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/monitor", tags=["Monitoramento ao Vivo"])

camera_service: CameraService = None
detection_service: DetectionService = None
change_detector = ChangeDetector()


def init_routes(cam_svc: CameraService, det_svc: DetectionService):
    global camera_service, detection_service
    camera_service = cam_svc
    detection_service = det_svc


def capture_frame(stream_url: str, timeout_sec: float = 10.0) -> Optional[np.ndarray]:
    """
    Captura um frame de um stream MJPEG ou RTSP usando OpenCV.
    
    Args:
        stream_url: URL do stream (MJPEG via HTTP ou RTSP)
        timeout_sec: Tempo máximo para capturar o frame
        
    Returns:
        np.ndarray: Frame em RGB ou None se falhar
    """
    try:
        cap = cv2.VideoCapture(stream_url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        start = time.time()
        frame = None
        while time.time() - start < timeout_sec:
            ret, frame = cap.read()
            if ret and frame is not None:
                break
            time.sleep(0.1)
        
        cap.release()
        
        if frame is None:
            return None
        
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    except Exception as e:
        logger.warning(f"Erro ao capturar frame do stream: {e}")
        return None


@router.get("/live/{camera_code}")
async def monitor_live(
    camera_code: str,
    confidence: Optional[float] = Query(None),
    include_image: bool = Query(True),
):
    """
    Monitora uma câmera ao vivo.
    
    Tenta capturar frame do stream para processar com YOLO.
    Se falhar (stream HTML/JS), retorna apenas a URL para o frontend
    exibir em iframe + análise baseada no último frame bem-sucedido.
    
    Retorna:
    - stream_url: URL para exibir no iframe
    - Detecção YOLO (se captura OK)
    - Score de risco de vandalismo (se captura OK)
    - Predição HF (se captura OK)
    """
    if not detection_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")
    
    start_time = time.time()
    
    # 1. Obtém dados da câmera
    camera = camera_service.get_camera_by_code(camera_code)
    if not camera:
        raise HTTPException(status_code=404, detail=f"Câmera {camera_code} não encontrada")
    
    camera_name = camera.get("name", f"Câmera {camera_code}")
    stream_url = camera.get("stream_url") or camera_service.get_stream_url(camera_code)
    
    # 2. Monta resposta base
    response = {
        "success": True,
        "camera_code": camera_code,
        "camera_name": camera_name,
        "stream_url": stream_url or "",
        "timestamp": time.time(),
        "yolo_detection": {"objects": [], "counts": {}, "total_objects": 0},
        "hf_prediction": None,
        "image_base64": None,
        "frame_captured": False,
    }
    
    # 3. Tenta capturar frame (timeout curto — 3s)
    if stream_url:
        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(capture_frame, stream_url, 5.0)
                frame = future.result(timeout=6)
        except Exception:
            frame = None
        
        if frame is not None:
            response["frame_captured"] = True
            
            # Pipeline de detecção
            result = detection_service.detect_full(frame, camera_id=camera_code, confidence=confidence)
            
            response["yolo_detection"] = {
                "objects": result.get("yolo_detection", {}).get("objects", []),
                "counts": result.get("yolo_detection", {}).get("counts", {}),
                "total_objects": result.get("yolo_detection", {}).get("total_objects", 0),
            }
            response["hf_prediction"] = result.get("hf_prediction")
            
            # Imagem anotada
            if include_image:
                annotated = result.get("yolo_detection", {}).get("annotated_image", frame)
                if annotated is not None:
                    _, buffer = cv2.imencode(".jpg", cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR),
                                             [cv2.IMWRITE_JPEG_QUALITY, 85])
                    response["image_base64"] = base64.b64encode(buffer).decode("utf-8")
    
    elapsed = (time.time() - start_time) * 1000
    response["processing_time_ms"] = round(elapsed, 2)
    
    return response


@router.get("/multi")
async def monitor_multi(
    codes: str = Query(..., description="Códigos das câmeras separados por vírgula"),
    confidence: Optional[float] = Query(None),
):
    """
    Monitora múltiplas câmeras em quadrante.
    Ex: /api/monitor/multi?codes=001175,000194,001963,003352
    
    Retorna análise de todas as câmeras em uma única chamada.
    """
    if not detection_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")
    
    camera_codes = [c.strip() for c in codes.split(",") if c.strip()]
    if not camera_codes:
        raise HTTPException(status_code=400, detail="Nenhum código de câmera informado")
    
    results = []
    for code in camera_codes[:4]:  # Máximo 4 câmeras por vez
        cam_result = {
            "camera_code": code,
            "success": False,
            "yolo_detection": {"objects": [], "counts": {}, "total_objects": 0},
            "hf_prediction": None,
            "frame_captured": False,
        }
        
        try:
            camera = camera_service.get_camera_by_code(code)
            cam_result["camera_name"] = camera.get("name", f"Câmera {code}") if camera else f"Câmera {code}"
            
            stream_url = camera.get("stream_url") if camera else None
            if not stream_url and camera:
                stream_url = camera_service.get_stream_url(code)
            cam_result["stream_url"] = stream_url or ""
            
            if stream_url:
                try:
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(capture_frame, stream_url, 5.0)
                        frame = future.result(timeout=6)
                except Exception:
                    frame = None
                
                if frame is not None:
                    cam_result["frame_captured"] = True
                    result = detection_service.detect_full(frame, camera_id=code, confidence=confidence)
                    cam_result["yolo_detection"] = {
                        "objects": result.get("yolo_detection", {}).get("objects", []),
                        "counts": result.get("yolo_detection", {}).get("counts", {}),
                        "total_objects": result.get("yolo_detection", {}).get("total_objects", 0),
                    }
                    cam_result["hf_prediction"] = result.get("hf_prediction")
            
            cam_result["success"] = True
            
        except Exception as e:
            logger.error(f"Erro ao processar câmera {code}: {e}")
            cam_result["error"] = str(e)
        
        results.append(cam_result)
    
    return {
        "success": True,
        "timestamp": time.time(),
        "cameras": results,
        "total": len(results),
    }


@router.get("/demo")
async def monitor_demo(
    cenario: str = Query("depredacao", description="Cenário: furto, depredacao, multidao, veiculo_suspeito"),
    camera_code: str = Query("001175", description="Código da câmera para exibir no resultado"),
):
    """
    Modo demonstração: gera uma cena sintética de vandalismo e executa
    todo o pipeline de detecção (YOLO + Vandalismo + HF).
    
    Retorna imagem anotada com bounding boxes + análise completa.
    Útil para testar e visualizar o funcionamento do sistema.
    """
    from app.models.demo_scene import gerar_cena_demo
    
    # Gera cena sintética
    frame = gerar_cena_demo(cenario)
    
    # Executa pipeline completo
    result = detection_service.detect_full(frame, camera_id=camera_code, confidence=0.25)
    
    # Anotação
    import base64
    annotated = result.get("yolo_detection", {}).get("annotated_image", frame)
    _, buffer = cv2.imencode(".jpg", cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR),
                             [cv2.IMWRITE_JPEG_QUALITY, 90])
    image_b64 = base64.b64encode(buffer).decode("utf-8")
    
    camera = camera_service.get_camera_by_code(camera_code)
    camera_name = camera.get("name", f"Câmera {camera_code}") if camera else f"Câmera {camera_code}"
    
    return {
        "success": True,
        "camera_code": camera_code,
        "camera_name": camera_name,
        "cenario": cenario,
        "descricao": gerar_cena_demo.__doc__.strip() if hasattr(gerar_cena_demo, "__doc__") else "",
        "frame_captured": True,
        "image_base64": image_b64,
        "yolo_detection": {
            "objects": result.get("yolo_detection", {}).get("objects", []),
            "counts": result.get("yolo_detection", {}).get("counts", {}),
            "total_objects": result.get("yolo_detection", {}).get("total_objects", 0),
        },
        "hf_prediction": result.get("hf_prediction"),
        "processing_time_ms": result.get("processing_time_ms", 0),
    }


@router.get("/streams")
async def get_streams(
    codes: str = Query(..., description="Códigos separados por vírgula"),
):
    """
    Rápido: retorna apenas as URLs de stream para exibir nos iframes.
    Sem captura de frame, sem YOLO — apenas as URLs.
    """
    if not camera_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")

    camera_codes = [c.strip() for c in codes.split(",") if c.strip()]
    result = []

    for code in camera_codes[:4]:
        camera = camera_service.get_camera_by_code(code)
        name = camera.get("name", f"Câmera {code}") if camera else f"Câmera {code}"
        stream_url = camera.get("stream_url") if camera else None
        if not stream_url:
            stream_url = camera_service.get_stream_url(code)

        result.append({
            "camera_code": code,
            "camera_name": name,
            "stream_url": stream_url or "",
        })

    return {"success": True, "cameras": result}


# ─── Detecção de Mudanças no Monumento (SSIM + HF) ─────────────

@router.post("/change/{camera_code}/reference")
async def set_reference(
    camera_code: str,
    usar_demo: bool = Query(False, description="Forçar demo se captura falhar"),
):
    """
    CAPTURA frame da câmera e define como REFERÊNCIA do monumento.
    
    Extrai automaticamente o ROI (região da estátua) e armazena.
    Comparações futuras usarão esta imagem como base para detectar
    pichação, danos, peças removidas, etc.
    """
    if not detection_service or not camera_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")

    # Carrega HF model em background
    if not detection_service.hf_vandalism.model_loaded:
        try:
            detection_service.hf_vandalism.load_model()
        except Exception:
            pass

    # Tenta capturar frame real da câmera
    frame = None
    camera = camera_service.get_camera_by_code(camera_code)
    if camera:
        stream_url = camera.get("stream_url") or camera_service.get_stream_url(camera_code)
        if stream_url:
            try:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(capture_frame, stream_url, 5.0)
                    frame = future.result(timeout=6)
            except Exception:
                pass

    if frame is None:
        # Fallback: gera frame com desenho do monumento pra demo
        logger.warning(f"Não foi possível capturar frame da câmera {camera_code}, usando demo")
        frame = _create_monument_frame()

    result = change_detector.set_reference(camera_code, frame, detection_service)

    # Codifica frame de referência pra exibição
    _, buffer = cv2.imencode(".jpg", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR),
                             [cv2.IMWRITE_JPEG_QUALITY, 85])
    result["reference_image_base64"] = base64.b64encode(buffer).decode("utf-8")

    return result


@router.get("/change/{camera_code}")
async def detect_changes(
    camera_code: str,
    usar_demo: bool = Query(False, description="Forçar demo se captura falhar"),
):
    """
    VERIFICA se houve mudança no monumento.
    
    1. Captura frame atual da câmera
    2. Extrai ROI da estátua
    3. Compara com referência via SSIM
    4. Se mudança detectada, executa HF model no ROI
    
    Retorna:
    - similarity_score: (1=idêntico)
    - change_percentage: % do ROI alterado
    - highlight_image: imagem com diferenças em vermelho
    - hf_prediction: probabilidades do HF model
    - alert: alerta se mudança significativa ou roubo/vandalismo
    """
    if not detection_service or not camera_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")

    # Se não tem referência, cria automaticamente
    if camera_code not in change_detector.monitored:
        # Tenta capturar frame pra referência
        ref_frame = None
        camera = camera_service.get_camera_by_code(camera_code)
        if camera:
            stream_url = camera.get("stream_url") or camera_service.get_stream_url(camera_code)
            if stream_url:
                try:
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(capture_frame, stream_url, 5.0)
                        ref_frame = future.result(timeout=6)
                except Exception:
                    pass
        if ref_frame is None:
            ref_frame = _create_monument_frame()
        change_detector.set_reference(camera_code, ref_frame, detection_service)

    # Captura frame atual pra comparação
    current_frame = None
    camera = camera_service.get_camera_by_code(camera_code)
    if camera:
        stream_url = camera.get("stream_url") or camera_service.get_stream_url(camera_code)
        if stream_url:
            try:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(capture_frame, stream_url, 5.0)
                    current_frame = future.result(timeout=6)
            except Exception:
                pass

    if current_frame is None:
        current_frame = _create_monument_frame()

    result = change_detector.check(camera_code, current_frame, detection_service)
    if not result.get("success"):
        return result

    return {
        "success": True,
        "camera_code": camera_code,
        "timestamp": result["timestamp"],
        "similarity_score": result["similarity_score"],
        "change_percentage": result["change_percentage"],
        "change_regions": result["change_regions"],
        "significant_changes": result["significant_changes"],
        "ssim_alert_level": result["ssim_alert_level"],
        "hf_prediction": result["hf_prediction"],
        "alert": result["alert"],
        "alert_level": result["alert_level"],
        "highlight_image_base64": result["highlight_image_base64"],
    }


@router.get("/change/{camera_code}/history")
async def change_history(camera_code: str):
    """Histórico de verificações de mudanças no monumento"""
    return {
        "success": True,
        "camera_code": camera_code,
        "history": change_detector.get_history(camera_code),
    }


# ─── Utilitário ─────────────────────────────────────────────────

def _create_monument_frame(width: int = 640, height: int = 480) -> np.ndarray:
    """Cria frame sintético de monumento para fallback"""
    img = np.ones((height, width, 3), dtype=np.uint8) * 200
    cv2.rectangle(img, (0, 0), (width, height // 3), (200, 210, 220), -1)
    cv2.rectangle(img, (0, height * 2 // 3), (width, height), (160, 160, 150), -1)
    # Monumento no centro
    cx, cy = width // 2, height // 2
    cv2.rectangle(img, (cx - 60, cy - 60), (cx + 60, cy + 60), (140, 130, 120), -1)
    cv2.circle(img, (cx, cy - 90), 35, (160, 150, 140), -1)
    return img

