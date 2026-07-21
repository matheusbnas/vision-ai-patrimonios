"""
🏛️ API do Sistema de Visão Computacional - Patrimônios do Rio
CO-RIO - Coordenadoria de Operações e Resiliência

FastAPI backend com:
  - YOLO para detecção de objetos
  - Modelo Hugging Face (CNN-Transformer) para classificação de vandalismo
  - Modelo YOLOv5 para detecção de danos estruturais
"""

import os
import sys
from pathlib import Path

# Garante que o diretório raiz do backend está no sys.path
# Isso permite executar tanto "python -m app.main" quanto "python app/main.py"
_backend_root = str(Path(__file__).resolve().parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import HOST, PORT, DEBUG, CORS_ORIGINS, ASSETS_DIR
from app.services.camera_service import CameraService
from app.services.detection_service import DetectionService

# ─── Configuração de Logging ────────────────────────────────────
logging.basicConfig(
    level=logging.INFO if not DEBUG else logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── Serviços Globais ───────────────────────────────────────────
camera_service = CameraService()
detection_service = DetectionService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida da aplicação"""
    logger.info("🚀 Inicializando serviços...")

    # Tenta autenticar na API de câmeras
    logger.info("📡 Conectando à API de câmeras...")
    auth_ok = camera_service.authenticate()
    if auth_ok:
        logger.info("✅ API de câmeras autenticada")
        # Carrega câmeras em background
        cameras = camera_service.get_all_cameras()
        logger.info(f"📹 {len(cameras)} câmeras carregadas")
    else:
        logger.warning("⚠️ API de câmeras não autenticada (use /api/auth/login)")

    # Inicializa modelos de detecção (já feito no __init__)
    models_status = detection_service.get_models_status()
    for name, loaded in models_status.items():
        if isinstance(loaded, bool):
            status = "✅" if loaded else "❌"
            logger.info(f"{status} Modelo {name}: {'carregado' if loaded else 'não carregado'}")

    logger.info("✅ API pronta para receber requisições")
    yield
    logger.info("🛑 API encerrando...")


# ─── Criação da Aplicação ───────────────────────────────────────
app = FastAPI(
    title="Visão Patrimônios - API",
    description="""
    API do Sistema de Visão Computacional para Monitoramento de Patrimônios Públicos do Rio.
    
    ## Funcionalidades
    * 📹 Listagem e gerenciamento de câmeras
    * 🔍 Detecção de objetos com YOLO
    * 🚨 Análise de vandalismo (heurística + Hugging Face)
    * 🏗️ Detecção de danos estruturais
    * 📊 Dashboard com estatísticas
    
    ## Modelos de IA
    * **YOLO11n** — Detecção de objetos (80 classes COCO)
    * **KzRyan/Burglary_and_Vandalism** — CNN-Transformer para classificação de vandalismo
    * **dolphinium/damaged-building-detection** — YOLOv5 para detecção de danos
    """,
    version="2.0.0",
    lifespan=lifespan,
)

# ─── CORS ────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Servir arquivos estáticos ──────────────────────────────────
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

# ─── Injeção de Dependências nas Rotas ──────────────────────────
from app.api import auth, cameras, detection, vandalism, dashboard

auth.init_routes(camera_service)
cameras.init_routes(camera_service)
detection.init_routes(detection_service)
vandalism.init_routes(detection_service)

# ─── Registro de Rotas ──────────────────────────────────────────
app.include_router(auth.router)
app.include_router(cameras.router)
app.include_router(detection.router)
app.include_router(vandalism.router)
app.include_router(dashboard.router)


# ─── Health Check ───────────────────────────────────────────────
@app.get("/health", tags=["Saúde"])
async def health():
    """Health check da API"""
    return {
        "status": "online",
        "version": "2.0.0",
        "models": {
            name: loaded if isinstance(loaded, bool) else True
            for name, loaded in detection_service.get_models_status().items()
            if isinstance(loaded, bool)
        },
    }


# ─── Ponto de Entrada ───────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        reload=DEBUG,
        log_level="info",
    )
