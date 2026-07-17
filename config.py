# Configurações do Sistema de Visão Computacional - Patrimônios do Rio
# CO-RIO - Coordenadoria de Operações e Resiliência

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# API Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://10.50.3.96:8000")
API_KEY = os.getenv("API_KEY", "co-cbf297ece46ab97c7601b56cf2a8c379")
API_EMAIL = os.getenv("API_EMAIL", "planejamentocor@cor.rio")
API_PASSWORD = os.getenv("API_PASSWORD", "Cor@857486")

# Stream Configuration
STREAM_BASE_URL = os.getenv("STREAM_BASE_URL", "http://10.50.3.11:5002")
STREAM_ENDPOINT = "/stream"
STREAM_KEY = os.getenv("STREAM_KEY", "")  # Chave JWT manual (opcional)

# Paths
BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
IMAGES_DIR = ASSETS_DIR / "images"
CACHE_DIR = BASE_DIR / "cache"

# Ensure directories exist
for d in [ASSETS_DIR, IMAGES_DIR, CACHE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Streamlit config
STREAMLIT_TITLE = "Sistema de Visão Computacional - Patrimônios do Rio"
STREAMLIT_ICON = "🏛️"
PAGE_SIZE = 50

# YOLO Model
YOLO_MODEL = "yolo11n.pt"  # Modelo leve para detecção
CONFIDENCE_THRESHOLD = 0.35

# Mapa
DEFAULT_MAP_CENTER = {"lat": -22.9068, "lon": -43.1729}  # Centro do Rio
DEFAULT_MAP_ZOOM = 11

# Classes de patrimônios que nos interessam (COCO dataset via YOLO)
# Adaptar conforme necessidade real de classificação
PATRIMONY_CLASSES = {
    0: "pessoa",
    1: "bicicleta",
    2: "carro",
    3: "moto",
    4: "avião",
    5: "ônibus",
    6: "trem",
    7: "caminhão",
    8: "barco",
    9: "semáforo",
    10: "hidrante",
    11: "placa_de_parada",
    12: "placa_de_trânsito",
    13: "cachorro",
    14: "pássaro",
    15: "gato",
    16: "cavalo",
    17: "ovelha",
    18: "vaca",
    19: "elefante",
    20: "urso",
    21: "zebra",
    22: "girafa",
    23: "mochila",
    24: "guarda-chuva",
    25: "bolsa",
    26: "gravata",
    27: "mala",
    28: "frisbee",
    29: "esquis",
    30: "snowboard",
    31: "bola_esportiva",
    32: "pipa",
    33: "taco_de_beisebol",
    34: "luva_de_beisebol",
    35: "skate",
    36: "prancha_de_surf",
    37: "raquete_de_tênis",
    38: "garrafa",
    39: "taça_de_vinho",
    40: "copo",
    41: "garfo",
    42: "faca",
    43: "colher",
    44: "tigela",
    45: "banana",
    46: "maçã",
    47: "sanduíche",
    48: "laranja",
    49: "brócolis",
    50: "cenoura",
    51: "cachorro_quente",
    52: "pizza",
    53: "rosquinha",
    54: "bolo",
    55: "cadeira",
    56: "sofá",
    57: "vaso_de_planta",
    58: "cama",
    59: "mesa_de_jantar",
    60: "vaso_sanitário",
    61: "monitor_tv",
    62: "notebook",
    63: "mouse",
    64: "controle_remoto",
    65: "teclado",
    66: "celular",
    67: "microondas",
    68: "forno",
    69: "torradeira",
    70: "pia",
    71: "geladeira",
    72: "livro",
    73: "relógio",
    74: "vaso",
    75: "tesoura",
    76: "ursinho_de_pelúcia",
    77: "secador_de_cabelo",
    78: "escova_de_dente",
}

# Mapeamento para categorias de patrimônio público (usando nomes traduzidos)
INTEREST_CLASSES = {
    "pessoa": "Patrimônio Humano / Visitante",
    "carro": "Veículo",
    "moto": "Veículo",
    "ônibus": "Transporte Público",
    "caminhão": "Veículo de Carga",
    "bicicleta": "Mobilidade Urbana",
    "skate": "Mobilidade Urbana",
    "vaso": "Patrimônio Histórico / Ornamento",
    "vaso_de_planta": "Área Verde / Paisagismo",
    "cadeira": "Mobiliário Urbano",
    "banco": "Mobiliário Urbano",
    "livro": "Acervo / Documentação",
    "relógio": "Patrimônio Histórico",
    "semáforo": "Sinalização Urbana",
    "placa_de_parada": "Sinalização Urbana",
    "placa_de_trânsito": "Sinalização Urbana",
    "hidrante": "Equipamento Público",
    "extintor": "Equipamento de Segurança",
    "lixeira": "Equipamento Público",
    "banco": "Mobiliário Urbano",
    "cachorro": "Animal / Fauna Urbana",
    "gato": "Animal / Fauna Urbana",
    "pássaro": "Animal / Fauna Urbana",
    "cavalo": "Animal / Fauna Urbana",
    "árvore": "Área Verde / Paisagismo",
}

# ─── PATRIMÔNIOS ESPECÍFICOS DO RIO ─────────────────────────────
# Lista dos 10 patrimônios históricos/culturais a serem monitorados
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
    },
    {
        "id": 4,
        "nome": "Cazuza",
        "descricao": "Estátua de Cazuza — Rua Dias Ferreira, Leblon",
        "bairro": "Leblon",
        "categoria": "Personalidade / Música",
        "emoji": "🎤",
        "latitude": -22.9848,
        "longitude": -43.2200,
    },
    {
        "id": 5,
        "nome": "Ayrton Senna",
        "descricao": "Estátua de Ayrton Senna — Avenida Atlântica, Copacabana",
        "bairro": "Copacabana",
        "categoria": "Personalidade / Esporte",
        "emoji": "🏎️",
        "latitude": -22.9850,
        "longitude": -43.1880,
    },
    {
        "id": 6,
        "nome": "Curumim",
        "descricao": "Monumento Curumim — Lagoa Rodrigo de Freitas",
        "bairro": "Lagoa",
        "categoria": "Monumento / Cultura Indígena",
        "emoji": "🪷",
        "latitude": -22.9715,
        "longitude": -43.2110,
    },
    {
        "id": 7,
        "nome": "Clarice Lispector",
        "descricao": "Estátua de Clarice Lispector — Orla do Leme",
        "bairro": "Leme",
        "categoria": "Personalidade / Literatura",
        "emoji": "📖",
        "latitude": -22.9590,
        "longitude": -43.1580,
    },
    {
        "id": 8,
        "nome": "Relógio da Glória",
        "descricao": "Relógio da Glória — Bairro da Glória",
        "bairro": "Glória",
        "categoria": "Patrimônio Histórico / Arquitetura",
        "emoji": "🕰️",
        "latitude": -22.9180,
        "longitude": -43.1740,
    },
    {
        "id": 9,
        "nome": "Princesa Isabel",
        "descricao": "Estátua da Princesa Isabel — Avenida Princesa Isabel",
        "bairro": "Copacabana",
        "categoria": "Personalidade / História",
        "emoji": "👑",
        "latitude": -22.9651473,
        "longitude": -43.1735504,
    },
    {
        "id": 10,
        "nome": "Tom Jobim",
        "descricao": "Estátua de Tom Jobim — Orla de Ipanema",
        "bairro": "Ipanema",
        "categoria": "Personalidade / Música",
        "emoji": "🎵",
        "latitude": -22.987883,
        "longitude": -43.19432,
    },
]

# Dicionário rápido nome -> patrimônio
PATRIMONIOS_DICT = {p["nome"].lower(): p for p in PATRIMONIOS}
