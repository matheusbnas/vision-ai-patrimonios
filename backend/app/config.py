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
DATA_DIR = BASE_DIR / "data"

for d in [ASSETS_DIR, IMAGES_DIR, CACHE_DIR, MODELS_DIR, DATA_DIR]:
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

# ─── Mapa ────────────────────────────────────────────────────────
DEFAULT_MAP_CENTER = {"lat": -22.9068, "lon": -43.1729}
DEFAULT_MAP_ZOOM = 11

# ─── Monitoramento contínuo em background ────────────────────────
# Varre todas as câmeras dos patrimônios sequencialmente (uma por vez,
# não em paralelo — evita sobrecarregar a máquina que roda o YOLO/HF).
BACKGROUND_MONITOR_ENABLED = os.getenv("BACKGROUND_MONITOR_ENABLED", "true").lower() == "true"
BACKGROUND_MONITOR_INTERVAL_SECONDS = int(os.getenv("BACKGROUND_MONITOR_INTERVAL_SECONDS", "20"))

# ─── Quadrante de foco no monumento (ROI) ────────────────────────
# Retângulo central do frame onde o monumento está posicionado.
# Usado tanto pelo diff SSIM (change_detector) quanto pelo filtro
# de zona do YOLO (detector) — mesma "zona do monumento" para os dois.
ROI_X_START = 0.20   # 20% da largura
ROI_X_END = 0.80     # 80% da largura
ROI_Y_START = 0.15   # 15% da altura
ROI_Y_END = 0.75     # 75% da altura

# Classes do YOLO (COCO) que representam objetos de risco ao patrimônio,
# com o nível de alerta BASE de cada uma (antes de considerar tempo de
# permanência — ver DWELL_ALERT_SECONDS / risk_tracker.py).
# faca/tesoura = perigo claro, alerta ALTO já na primeira detecção.
# Os demais são objetos comuns que também servem pra bater/quebrar —
# entram como MODERADO pra não gritar CRÍTICO por alguém só carregando
# uma garrafa d'água perto do monumento.
# Limitação: o COCO não tem classe pra spray de pichação, martelo,
# barra de metal etc. — isso exigiria um modelo customizado/
# open-vocabulary, fora de escopo aqui.
RISK_CLASSES = {
    "faca": "ALTO",
    "tesoura": "ALTO",
    "taco_de_beisebol": "MODERADO",
    "garrafa": "MODERADO",
    "guarda-chuva": "MODERADO",
}

# Tempo (segundos) que um objeto de risco precisa permanecer dentro da
# zona do monumento para o alerta escalar para CRÍTICO, independente do
# nível base da classe.
DWELL_ALERT_SECONDS = 120

# ─── Classes ─────────────────────────────────────────────────────
# Mapeamento 1:1 com a ordem real das 80 classes COCO usadas pelo YOLO
# (ver `model.names` do ultralytics) — traduzido para português.
PATRIMONY_CLASSES = {
    0: "pessoa", 1: "bicicleta", 2: "carro", 3: "moto", 4: "avião",
    5: "ônibus", 6: "trem", 7: "caminhão", 8: "barco", 9: "semáforo",
    10: "hidrante", 11: "placa_de_parada", 12: "parquímetro",
    13: "banco", 14: "pássaro", 15: "gato", 16: "cachorro",
    17: "cavalo", 18: "ovelha", 19: "vaca", 20: "elefante",
    21: "urso", 22: "zebra", 23: "girafa", 24: "mochila",
    25: "guarda-chuva", 26: "bolsa", 27: "gravata", 28: "mala",
    29: "frisbee", 30: "esquis", 31: "snowboard", 32: "bola_esportiva",
    33: "pipa", 34: "taco_de_beisebol", 35: "luva_de_beisebol",
    36: "skate", 37: "prancha_de_surf", 38: "raquete_de_tênis",
    39: "garrafa", 40: "taça_de_vinho", 41: "copo", 42: "garfo",
    43: "faca", 44: "colher", 45: "tigela", 46: "banana",
    47: "maçã", 48: "sanduíche", 49: "laranja", 50: "brócolis",
    51: "cenoura", 52: "cachorro_quente", 53: "pizza", 54: "rosquinha",
    55: "bolo", 56: "cadeira", 57: "sofá", 58: "vaso_de_planta",
    59: "cama", 60: "mesa_de_jantar", 61: "vaso_sanitário", 62: "monitor_tv",
    63: "notebook", 64: "mouse", 65: "controle_remoto", 66: "teclado",
    67: "celular", 68: "microondas", 69: "forno", 70: "torradeira",
    71: "pia", 72: "geladeira", 73: "livro", 74: "relógio",
    75: "vaso", 76: "tesoura", 77: "ursinho_de_pelúcia",
    78: "secador_de_cabelo", 79: "escova_de_dente",
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
    "parquímetro": "Sinalização Urbana",
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
