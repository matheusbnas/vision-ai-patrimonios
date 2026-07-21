"""
Configurações do Sistema de Visão Computacional - Patrimônios do Rio
CO-RIO - Coordenadoria de Operações e Resiliência
Backend FastAPI
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─── Caminhos ────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
IMAGES_DIR = ASSETS_DIR / "images"
CACHE_DIR = BASE_DIR / "cache"
MODELS_DIR = BASE_DIR / "models_cache"

for d in [ASSETS_DIR, IMAGES_DIR, CACHE_DIR, MODELS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── API de Câmeras ──────────────────────────────────────────────
API_BASE_URL = os.getenv("API_BASE_URL", "http://10.50.3.96:8000")
API_KEY = os.getenv("API_KEY", "")
API_EMAIL = os.getenv("API_EMAIL", "")
API_PASSWORD = os.getenv("API_PASSWORD", "")

# ─── Stream ──────────────────────────────────────────────────────
STREAM_BASE_URL = os.getenv("STREAM_BASE_URL", "http://10.50.3.11:5002")
STREAM_ENDPOINT = "/stream"
STREAM_KEY = os.getenv("STREAM_KEY", "")

# ─── Servidor FastAPI ────────────────────────────────────────────
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")

# ─── YOLO ────────────────────────────────────────────────────────
YOLO_MODEL = os.getenv("YOLO_MODEL", str(BASE_DIR.parent / "yolo11n.pt"))
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.35"))

# ─── Hugging Face ────────────────────────────────────────────────
HF_TOKEN = os.getenv("HF_TOKEN", "")
VANDALISM_MODEL_REPO = os.getenv(
    "VANDALISM_MODEL_REPO", "KzRyan/Burglary_and_Vandalism"
)
VANDALISM_MODEL_FILE = os.getenv(
    "VANDALISM_MODEL_FILE", "HYBRID_CNN_TRANSFORMER_MODEL.pth"
)
DAMAGE_MODEL_REPO = os.getenv(
    "DAMAGE_MODEL_REPO", "dolphinium/damaged-building-detection"
)

# ─── Mapa ────────────────────────────────────────────────────────
DEFAULT_MAP_CENTER = {"lat": -22.9068, "lon": -43.1729}
DEFAULT_MAP_ZOOM = 11

# ─── Classes ─────────────────────────────────────────────────────
PATRIMONY_CLASSES = {
    0: "pessoa", 1: "bicicleta", 2: "carro", 3: "moto", 4: "avião",
    5: "ônibus", 6: "trem", 7: "caminhão", 8: "barco", 9: "semáforo",
    10: "hidrante", 11: "placa_de_parada", 12: "placa_de_trânsito",
    13: "cachorro", 14: "pássaro", 15: "gato", 16: "cavalo",
    17: "ovelha", 18: "vaca", 19: "elefante", 20: "urso",
    21: "zebra", 22: "girafa", 23: "mochila", 24: "guarda-chuva",
    25: "bolsa", 26: "gravata", 27: "mala", 28: "frisbee",
    29: "esquis", 30: "snowboard", 31: "bola_esportiva", 32: "pipa",
    33: "taco_de_beisebol", 34: "luva_de_beisebol", 35: "skate",
    36: "prancha_de_surf", 37: "raquete_de_tênis", 38: "garrafa",
    39: "taça_de_vinho", 40: "copo", 41: "garfo", 42: "faca",
    43: "colher", 44: "tigela", 45: "banana", 46: "maçã",
    47: "sanduíche", 48: "laranja", 49: "brócolis", 50: "cenoura",
    51: "cachorro_quente", 52: "pizza", 53: "rosquinha", 54: "bolo",
    55: "cadeira", 56: "sofá", 57: "vaso_de_planta", 58: "cama",
    59: "mesa_de_jantar", 60: "vaso_sanitário", 61: "monitor_tv",
    62: "notebook", 63: "mouse", 64: "controle_remoto", 65: "teclado",
    66: "celular", 67: "microondas", 68: "forno", 69: "torradeira",
    70: "pia", 71: "geladeira", 72: "livro", 73: "relógio",
    74: "vaso", 75: "tesoura", 76: "ursinho_de_pelúcia",
    77: "secador_de_cabelo", 78: "escova_de_dente",
}

INTEREST_CLASSES = {
    "pessoa": "Patrimônio Humano / Visitante",
    "carro": "Veículo", "moto": "Veículo",
    "ônibus": "Transporte Público", "caminhão": "Veículo de Carga",
    "bicicleta": "Mobilidade Urbana", "skate": "Mobilidade Urbana",
    "vaso": "Patrimônio Histórico / Ornamento",
    "vaso_de_planta": "Área Verde / Paisagismo",
    "cadeira": "Mobiliário Urbano",
    "livro": "Acervo / Documentação",
    "relógio": "Patrimônio Histórico",
    "semáforo": "Sinalização Urbana",
    "placa_de_parada": "Sinalização Urbana",
    "placa_de_trânsito": "Sinalização Urbana",
    "hidrante": "Equipamento Público",
    "cachorro": "Animal / Fauna Urbana",
    "gato": "Animal / Fauna Urbana",
    "pássaro": "Animal / Fauna Urbana",
    "cavalo": "Animal / Fauna Urbana",
}

# ─── Patrimônios Específicos do Rio ──────────────────────────────
# Lista oficial de patrimônios monitorados com seus códigos de câmera
PATRIMONIOS = [
    {
        "id": 1,
        "nome": "Betinho",
        "descricao": "Estátua de Herbert de Souza (Betinho) — Praia de Botafogo",
        "bairro": "Botafogo",
        "categoria": "Personalidade / Direitos Humanos",
        "emoji": "🧓",
        "latitude": -22.9500,
        "longitude": -43.1850,
        "camera_codes": ["003352"],
    },
    {
        "id": 2,
        "nome": "Marielle Franco",
        "descricao": "Memorial Marielle Franco — Terminal Menezes Cortes (Novo Rio)",
        "bairro": "Santo Cristo",
        "categoria": "Personalidade / Direitos Humanos",
        "emoji": "✊🏿",
        "latitude": -22.8975,
        "longitude": -43.2150,
        "camera_codes": ["001963", "001962"],
    },
    {
        "id": 3,
        "nome": "Cacá Diegues",
        "descricao": "Homenagem a Cacá Diegues — Alto da Boa Vista",
        "bairro": "Alto da Boa Vista",
        "categoria": "Personalidade / Cinema",
        "emoji": "🎬",
        "latitude": -22.9565,
        "longitude": -43.2830,
        "camera_codes": ["007950"],
    },
    {
        "id": 4,
        "nome": "Cazuza",
        "descricao": "Estátua de Cazuza — Rua Dias Ferreira, Leblon",
        "bairro": "Leblon",
        "endereco": "Rua Dias Ferreira, 12 - Leblon",
        "categoria": "Personalidade / Música",
        "emoji": "🎤",
        "latitude": -22.9848,
        "longitude": -43.2220,
        "camera_codes": [],
        "obs": "Sem câmera exclusiva voltada para o monumento",
    },
    {
        "id": 5,
        "nome": "Ayrton Senna",
        "descricao": "Estátua de Ayrton Senna — Avenida Atlântica, Copacabana",
        "bairro": "Copacabana",
        "endereco": "Av. Atlântica x R. Rodolfo Dantas - Copacabana",
        "categoria": "Personalidade / Esporte",
        "emoji": "🏎️",
        "latitude": -22.9675,
        "longitude": -43.1784,
        "camera_codes": ["003696"],
        "obs": "Câmera 3696 da Av. Atlântica — não é exclusiva do monumento",
    },
    {
        "id": 6,
        "nome": "Curumim",
        "descricao": "Escultura do Curumim — Av. Borges de Medeiros, Lagoa",
        "bairro": "Lagoa",
        "endereco": "Av. Borges de Medeiros - Lagoa",
        "categoria": "Patrimônio Artístico",
        "emoji": "🧒",
        "latitude": -22.9710,
        "longitude": -43.2110,
        "camera_codes": [],
        "obs": "Sem câmera exclusiva voltada para o monumento",
    },
    {
        "id": 7,
        "nome": "Clarice Lispector",
        "descricao": "Estátua de Clarice Lispector — Caminho dos Pescadores, Leme",
        "bairro": "Leme",
        "endereco": "Caminho dos Pescadores Ted Boy Marino - Leme",
        "categoria": "Personalidade / Literatura",
        "emoji": "📖",
        "latitude": -22.9627,
        "longitude": -43.1655,
        "camera_codes": ["000646"],
        "obs": "Sem câmera exclusiva, mas é possível visualizar pela câmera 646 (Av. Atlântica x Ponta do Leme)",
    },
    {
        "id": 8,
        "nome": "Relógio da Glória",
        "descricao": "Relógio da Glória — Parque do Flamengo / Av. Edson Passos",
        "bairro": "Alto da Boa Vista",
        "endereco": "Av. Edson Passos - Alto da Boa Vista",
        "categoria": "Patrimônio Histórico",
        "emoji": "🕰️",
        "latitude": -22.9150,
        "longitude": -43.1720,
        "camera_codes": [],
        "obs": "Sem câmera exclusiva voltada para o monumento",
    },
    {
        "id": 9,
        "nome": "Princesa Isabel",
        "descricao": "Monumento Princesa Isabel — Avenida Princesa Isabel, Copacabana",
        "bairro": "Copacabana",
        "endereco": "Av. Princesa Isabel - Copacabana",
        "categoria": "Personalidade / História",
        "emoji": "👑",
        "latitude": -22.9651,
        "longitude": -43.1736,
        "camera_codes": ["001175"],
    },
    {
        "id": 10,
        "nome": "Tom Jobim",
        "descricao": "Monumento Tom Jobim — Av. Francisco Bhering, Ipanema",
        "bairro": "Ipanema",
        "endereco": "Av. Francisco Bhering, S/N - Ipanema",
        "categoria": "Personalidade / Música",
        "emoji": "🎵",
        "latitude": -22.9879,
        "longitude": -43.1943,
        "camera_codes": ["000194"],
    },
]
