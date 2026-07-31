"""
Rotas de monitoramento ao vivo com detecção em tempo real.
Captura frames do stream Tixxi, processa com YOLO + HF e retorna análise.
"""

import base64
import logging
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.services.camera_service import CameraService
from app.services.detection_service import DetectionService
from app.services import zone_service, alert_service
from app.models.change_detector import ChangeDetector
from app.config import IMAGES_DIR
from app.schemas.schemas import ZoneInput

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/monitor", tags=["Monitoramento ao Vivo"])

# Teto de segurança pra requisições em lote (/multi, /streams) — não é mais
# 4, já que o pedido é acompanhar todas as câmeras dos patrimônios ao vivo.
MAX_BATCH_CAMERAS = 16

camera_service: CameraService = None
detection_service: DetectionService = None
change_detector = ChangeDetector()


def init_routes(cam_svc: CameraService, det_svc: DetectionService):
    global camera_service, detection_service
    camera_service = cam_svc
    detection_service = det_svc


def _parse_mjpeg_frame(stream_url: str, timeout_sec: float = 5.0) -> Optional[np.ndarray]:
    """
    Lê o stream MJPEG via HTTP e extrai o primeiro frame JPEG.
    Funciona com streams multipart/x-mixed-replace (padrão de câmeras IP).
    
    Usa headers de navegador para evitar bloqueios.
    
    Args:
        stream_url: URL do stream MJPEG
        timeout_sec: Tempo máximo para capturar
        
    Returns:
        np.ndarray: Frame em RGB ou None se falhar
    """
    import io
    import warnings
    import requests as req
    
    # Suprime aviso de SSL verify=False (stream interno)
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Referer": stream_url.split("?")[0],
    }
    
    buffer = b""
    start = time.time()
    
    try:
        with req.get(stream_url, headers=headers, stream=True,
                     timeout=timeout_sec, verify=False) as resp:
            if resp.status_code != 200:
                logger.warning(f"MJPEG HTTP {resp.status_code} para {stream_url[:80]}")
                return None
            
            ct = resp.headers.get("content-type", "")
            
            # Se for image/jpeg direto, é um frame único
            if "image/jpeg" in ct or "image/jpg" in ct:
                img = Image.open(io.BytesIO(resp.content))
                return np.array(img)
            
            for chunk in resp.iter_content(chunk_size=16384):
                if time.time() - start > timeout_sec:
                    break
                if not chunk:
                    continue
                buffer += chunk
                
                # Procura marcadores JPEG no buffer
                start_jpeg = buffer.find(b'\xff\xd8')
                end_jpeg = buffer.find(b'\xff\xd9')
                
                if start_jpeg >= 0 and end_jpeg >= 0 and end_jpeg > start_jpeg:
                    jpeg_data = buffer[start_jpeg:end_jpeg + 2]
                    try:
                        img = Image.open(io.BytesIO(jpeg_data))
                        img.verify()  # valida integridade
                        img = Image.open(io.BytesIO(jpeg_data))
                        return np.array(img)
                    except Exception:
                        # JPEG corrompido, continua procurando
                        buffer = buffer[end_jpeg + 2:]
                        continue
                
                # Se buffer crescer demais, limpa (mantém últimos 64KB)
                if len(buffer) > 1024 * 512:  # 512KB
                    if start_jpeg >= 0:
                        buffer = buffer[start_jpeg:]
                    else:
                        buffer = buffer[-65536:]
    except Exception as e:
        logger.warning(f"MJPEG parser error: {e}")
    
    return None


# Cor de fundo (BGR) da tela de "Reconectando..." exibida pelo player
# quando o stream cai — se a maior parte do frame capturado for essa cor,
# não é vídeo real, é a UI de erro do player renderizada pelo Playwright.
_STREAM_ERROR_BG_BGR = np.array([26, 20, 14])


def _is_stream_error_frame(frame_rgb: np.ndarray) -> bool:
    """Detecta se o frame capturado é a tela de erro/reconectando do player, não vídeo real."""
    bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
    dist = np.linalg.norm(bgr.astype(int) - _STREAM_ERROR_BG_BGR, axis=2)
    return (dist < 15).mean() > 0.5


def capture_frame(stream_url: str, timeout_sec: float = 10.0) -> Optional[np.ndarray]:
    """
    Captura um frame REAL do stream da câmera.
    
    O stream retorna HTML/JS renderizado no navegador (iframe).
    A estratégia principal é usar Playwright (Chromium headless)
    para abrir a página e fazer screenshot do que aparece.
    
    Args:
        stream_url: URL do stream
        timeout_sec: Tempo máximo para capturar o frame
        
    Returns:
        np.ndarray: Frame em RGB ou None se falhar
    """
    import io
    from PIL import Image

    # ─── Tentativa 1: Playwright (Chromium headless) ──────────────
    # O stream é HTML/JS (exibido em iframe no frontend).
    # Playwright renderiza a página e tira screenshot do vídeo/canvas.
    try:
        from playwright.sync_api import sync_playwright
        
        # Tenta até 2x: se falhar com 401, renova stream_url e tenta de novo
        for tentativa in range(2):
            current_url = stream_url
            
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ],
                )
                context = browser.new_context(
                    viewport={"width": 800, "height": 600},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    locale="pt-BR",
                    bypass_csp=True,
                )
                page = context.new_page()
                
                # Monitora erros de rede (401 = token expirado)
                token_expired = False
                def handle_response(resp):
                    nonlocal token_expired
                    if resp.status == 401:
                        token_expired = True
                page.on('response', handle_response)
                
                # Navega até o stream
                logger.info(f"Playwright: tentativa {tentativa+1}, abrindo stream...")
                page.goto(current_url, timeout=timeout_sec * 1000,
                          wait_until="domcontentloaded")
                
                # Aguarda React carregar e procurar video
                page.wait_for_timeout(3000)
                
                # Se detectou 401 e é a primeira tentativa, renova token e tenta de novo
                if token_expired and tentativa == 0:
                    logger.info("Token expirado, renovando stream_url...")
                    browser.close()
                    # Tenta renovar via camera_service
                    try:
                        if camera_service:
                            cam = camera_service.get_camera_by_code(
                                stream_url.split("CODE=")[1].split("&")[0]
                                if "CODE=" in stream_url else ""
                            )
                            if cam and cam.get("stream_url"):
                                stream_url = cam["stream_url"]
                                logger.info("Stream URL renovada!")
                    except Exception:
                        pass
                    continue  # tenta de novo com nova URL
                
                # Tenta dar play no video via JS
                page.evaluate("""() => {
                    const v = document.querySelector("video");
                    if (v) {
                        v.muted = true;
                        v.play().catch(() => {});
                    }
                }""")
                page.wait_for_timeout(3000)
                
                # Screenshot
                screenshot = page.screenshot(type="jpeg", quality=90)
                browser.close()
            
            img = Image.open(io.BytesIO(screenshot))
            frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            if _is_stream_error_frame(frame_rgb):
                logger.warning(f"Playwright: capturou tela de 'Reconectando' (tentativa {tentativa+1}), não é vídeo real")
                continue  # tenta de novo (nova sessão) antes de cair pros outros métodos

            logger.info("✅ Playwright: frame capturado com sucesso!")
            return frame_rgb

    except Exception as e:
        logger.warning(f"Playwright falhou: {e}")
    
    # ─── Tentativa 2: MJPEG HTTP streaming ──────────────────────
    frame = _parse_mjpeg_frame(stream_url, timeout_sec)
    if frame is not None:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    # ─── Tentativa 3: OpenCV (MJPEG/RTSP) ───────────────────────
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
        
        if frame is not None:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    except Exception as e:
        logger.warning(f"OpenCV não conseguiu capturar: {e}")
    
    # ─── Tentativa 4: requests direto ───────────────────────────
    try:
        import requests as req
        resp = req.get(stream_url, timeout=timeout_sec)
        if resp.status_code == 200:
            img = Image.open(io.BytesIO(resp.content))
            return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    except Exception as e:
        logger.warning(f"Requests direto falhou: {e}")
    
    return None


# Labels de captura automática/repetitiva — sobrescrevem sempre o mesmo
# arquivo (1 por câmera+label) em vez de acumular um arquivo novo a cada
# captura. "print" (snapshot manual, botão explícito) fica de fora e
# continua gerando um arquivo por captura, já que é uma ação deliberada
# do usuário e não um loop automático.
_OVERWRITE_LABELS = {"monitoramento", "comparacao", "referencia"}


def save_camera_snapshot(frame: np.ndarray, camera_code: str,
                          camera_name: str = "",
                          label: str = "captura") -> Optional[str]:
    """
    Salva o frame capturado da câmera em assets/images/{camera_code}/.

    Para labels em _OVERWRITE_LABELS (monitoramento/comparacao/referencia),
    usa nome fixo: {camera_name}_{camera_code}_{label}.jpg — cada nova
    captura sobrescreve a anterior, evitando acumular imagens durante o
    monitoramento automático (que roda a cada poucos segundos).
    Para os demais labels (ex.: "print"), mantém o timestamp no nome.

    Args:
        frame: Imagem numpy (RGB)
        camera_code: Código da câmera
        camera_name: Nome do monumento/câmera
        label: Tipo de captura (ex: "referencia", "comparacao", "monitoramento")

    Returns:
        str: Caminho relativo salvo ou None se falhar
    """
    try:
        # Cria pasta específica da câmera
        cam_dir = IMAGES_DIR / camera_code
        cam_dir.mkdir(parents=True, exist_ok=True)

        # Sanitiza nome
        safe_name = (camera_name or f"Camera_{camera_code}")
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in safe_name)
        safe_name = safe_name.strip().replace(" ", "_")

        if label in _OVERWRITE_LABELS:
            filename = f"{safe_name}_{camera_code}_{label}.jpg"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{safe_name}_{camera_code}_{label}_{timestamp}.jpg"

        filepath = cam_dir / filename

        # Salva como JPEG
        cv2.imwrite(str(filepath), cv2.cvtColor(frame, cv2.COLOR_RGB2BGR),
                    [cv2.IMWRITE_JPEG_QUALITY, 92])

        logger.info(f"📸 Snapshot salvo: {filepath}")
        return str(filepath.relative_to(IMAGES_DIR.parent.parent))  # relativo à raiz do projeto
    except Exception as e:
        logger.warning(f"Erro ao salvar snapshot: {e}")
        return None


def record_risk_alert(camera_code: str, camera_name: str, risk_alert: Optional[dict]) -> None:
    """Registra no alert_service um risk_alert (YOLO/preditivo), se houver."""
    if risk_alert:
        alert_service.add_alert(
            camera_code=camera_code,
            camera_name=camera_name,
            level=risk_alert["level"],
            message=risk_alert["message"],
            source="risk",
            objects=risk_alert.get("objects"),
        )


def record_ssim_alert(camera_code: str, camera_name: str, alert: Optional[dict]) -> None:
    """Registra no alert_service um alert de mudança física (SSIM), se houver."""
    if alert:
        alert_service.add_alert(
            camera_code=camera_code,
            camera_name=camera_name,
            level=alert["level"],
            message=alert["message"],
            source="ssim",
        )


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
        "risk_alert": None,
        "hf_prediction": None,
        "image_base64": None,
        "frame_captured": False,
    }
    
    # 3. Tenta capturar frame (timeout curto — 3s)
    if stream_url:
        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(capture_frame, stream_url, 15.0)
                frame = future.result(timeout=20)
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
            response["risk_alert"] = result.get("risk_alert")
            response["hf_prediction"] = result.get("hf_prediction")
            record_risk_alert(camera_code, camera_name, response["risk_alert"])
            response["snapshot_path"] = save_camera_snapshot(frame, camera_code, camera_name, "monitoramento")
            
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
    for code in camera_codes[:MAX_BATCH_CAMERAS]:
        cam_result = {
            "camera_code": code,
            "success": False,
            "yolo_detection": {"objects": [], "counts": {}, "total_objects": 0},
            "risk_alert": None,
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
                        future = pool.submit(capture_frame, stream_url, 15.0)
                        frame = future.result(timeout=20)
                except Exception:
                    frame = None
                
                if frame is not None:
                    cam_result["frame_captured"] = True
                    # 📸 Salva snapshot do frame em assets/images/
                    cam_name = cam_result.get("camera_name", f"Câmera {code}")
                    cam_result["snapshot_path"] = save_camera_snapshot(frame, code, cam_name, "monitoramento")
                    
                    result = detection_service.detect_full(frame, camera_id=code, confidence=confidence)
                    cam_result["yolo_detection"] = {
                        "objects": result.get("yolo_detection", {}).get("objects", []),
                        "counts": result.get("yolo_detection", {}).get("counts", {}),
                        "total_objects": result.get("yolo_detection", {}).get("total_objects", 0),
                    }
                    cam_result["risk_alert"] = result.get("risk_alert")
                    cam_result["hf_prediction"] = result.get("hf_prediction")
                    record_risk_alert(code, cam_name, cam_result["risk_alert"])
            
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
        "risk_alert": result.get("risk_alert"),
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

    for code in camera_codes[:MAX_BATCH_CAMERAS]:
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


# ─── Snapshot Manual ────────────────────────────────────────────

@router.post("/snapshot/{camera_code}")
async def capture_snapshot(
    camera_code: str,
):
    """
    CAPTURA um print do que a câmera está mostrando AGORA
    e salva em assets/images/ com o nome do monumento.
    
    Retorna o caminho do arquivo salvo para visualização.
    """
    if not camera_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")
    
    camera = camera_service.get_camera_by_code(camera_code)
    if not camera:
        raise HTTPException(status_code=404, detail=f"Câmera {camera_code} não encontrada")
    
    camera_name = camera.get("name", f"Câmera {camera_code}")
    stream_url = camera.get("stream_url") or camera_service.get_stream_url(camera_code)
    
    if not stream_url:
        raise HTTPException(status_code=400, detail="Câmera não possui stream URL")
    
    # Captura frame real (sem fallback sintético)
    frame = capture_frame(stream_url, timeout_sec=20.0)
    
    if frame is None:
        return {
            "success": False,
            "error": "Não foi possível capturar frame da câmera. "
                     "Verifique se o stream está acessível.",
            "camera_code": camera_code,
            "camera_name": camera_name,
        }
    
    # Salva snapshot
    snapshot_path = save_camera_snapshot(frame, camera_code, camera_name, "print")
    
    # Codifica como base64 pra exibição imediata
    _, buffer = cv2.imencode(".jpg", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR),
                             [cv2.IMWRITE_JPEG_QUALITY, 92])
    image_base64 = base64.b64encode(buffer).decode("utf-8")
    
    return {
        "success": True,
        "camera_code": camera_code,
        "camera_name": camera_name,
        "snapshot_path": snapshot_path,
        "image_base64": image_base64,
        "timestamp": time.time(),
        "message": f"📸 Print salvo: {snapshot_path}",
    }


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
                    future = pool.submit(capture_frame, stream_url, 15.0)
                    frame = future.result(timeout=20)
            except Exception:
                pass

    frame_real = frame is not None  # guarda se é frame real antes do fallback
    if frame is None:
        # Fallback: gera frame com desenho do monumento pra demo
        logger.warning(f"Não foi possível capturar frame da câmera {camera_code}, usando demo")
        frame = _create_monument_frame()

    # 📸 Salva snapshot da referência em assets/images/ (só se for frame real)
    if frame_real:
        camera_name_clean = camera.get("name", f"Câmera {camera_code}") if camera else f"Câmera {camera_code}"
        save_camera_snapshot(frame, camera_code, camera_name_clean, "referencia")

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
                        future = pool.submit(capture_frame, stream_url, 15.0)
                        ref_frame = future.result(timeout=20)
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
                    future = pool.submit(capture_frame, stream_url, 15.0)
                    current_frame = future.result(timeout=20)
            except Exception:
                pass

    frame_real = current_frame is not None  # guarda se é frame real antes do fallback
    if current_frame is None:
        current_frame = _create_monument_frame()

    # 📸 Salva snapshot da comparação em assets/images/ (só se for frame real)
    if frame_real:
        camera_name_comp = camera.get("name", f"Câmera {camera_code}") if camera else f"Câmera {camera_code}"
        save_camera_snapshot(current_frame, camera_code, camera_name_comp, "comparacao")

    result = change_detector.check(camera_code, current_frame, detection_service)
    if not result.get("success"):
        return result

    camera_name_alert = camera.get("name", f"Câmera {camera_code}") if camera else f"Câmera {camera_code}"
    record_ssim_alert(camera_code, camera_name_alert, result["alert"])

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


# ─── Calibração de Zona (quadrante por câmera) ─────────────────

@router.get("/zone/{camera_code}")
async def get_zone(camera_code: str):
    """Retorna a zona (quadrante) calibrada da câmera, ou o padrão."""
    return {
        "success": True,
        "camera_code": camera_code,
        "zone": zone_service.get_zone(camera_code),
        "is_custom": zone_service.is_custom(camera_code),
    }


@router.put("/zone/{camera_code}")
async def put_zone(camera_code: str, zone: ZoneInput):
    """Salva a zona (quadrante) calibrada da câmera."""
    try:
        saved = zone_service.set_zone(camera_code, zone.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "camera_code": camera_code, "zone": saved}


@router.delete("/zone/{camera_code}")
async def delete_zone(camera_code: str):
    """Remove a calibração custom da câmera, voltando ao quadrante padrão."""
    default = zone_service.reset_zone(camera_code)
    return {"success": True, "camera_code": camera_code, "zone": default}


@router.get("/zone/{camera_code}/frame")
async def get_zone_frame(camera_code: str):
    """
    Captura um frame real da câmera (sem anotação) para servir de base
    ao desenho do quadrante na ferramenta de calibração do frontend.
    """
    if not camera_service:
        raise HTTPException(status_code=500, detail="Serviço não inicializado")

    frame = None
    camera = camera_service.get_camera_by_code(camera_code)
    if camera:
        stream_url = camera.get("stream_url") or camera_service.get_stream_url(camera_code)
        if stream_url:
            try:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(capture_frame, stream_url, 15.0)
                    frame = future.result(timeout=20)
            except Exception:
                pass

    frame_real = frame is not None
    if frame is None:
        logger.warning(f"Não foi possível capturar frame da câmera {camera_code} para calibração, usando demo")
        frame = _create_monument_frame()

    _, buffer = cv2.imencode(".jpg", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR),
                             [cv2.IMWRITE_JPEG_QUALITY, 90])
    return {
        "success": True,
        "camera_code": camera_code,
        "frame_captured": frame_real,
        "image_base64": base64.b64encode(buffer).decode("utf-8"),
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

