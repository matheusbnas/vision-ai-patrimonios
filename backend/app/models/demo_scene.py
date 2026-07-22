"""
Gera cenas de demonstração simulando vandalismo em patrimônios públicos.
Usa OpenCV para desenhar objetos realistas que o YOLO consegue detectar.
"""

import logging
import random
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Objetos que YOLO detecta e são relevantes para vandalismo
VANDALISM_SCENARIOS = {
    "furto": {
        "descricao": "Pessoa com ferramenta perto de monumento",
        "objetos": [
            ("pessoa", 0), ("faca", 0), ("mochila", 0),
        ],
    },
    "depredacao": {
        "descricao": "Grupo com objetos perto de monumento",
        "objetos": [
            ("pessoa", 0), ("pessoa", 0), ("pessoa", 0),
            ("garrafa", 0), ("taco_de_beisebol", 0),
        ],
    },
    "multidao": {
        "descricao": "Aglomeração suspeita no monumento",
        "objetos": [
            ("pessoa", 0), ("pessoa", 0), ("pessoa", 0),
            ("pessoa", 0), ("pessoa", 0), ("pessoa", 0),
            ("mochila", 0), ("garrafa", 0),
        ],
    },
    "veiculo_suspeito": {
        "descricao": "Pessoas + veículo em horário suspeito",
        "objetos": [
            ("pessoa", 0), ("pessoa", 0),
            ("carro", 0), ("mochila", 0),
        ],
    },
}


def gerar_cena_demo(
    cenario: str = "depredacao",
    width: int = 640,
    height: int = 480,
) -> np.ndarray:
    """
    Gera uma imagem sintética simulando uma cena de vandalismo.
    
    A imagem contém:
    - Um fundo de rua/praça
    - Um monumento ao centro
    - Pessoas e objetos posicionados ao redor
    
    Args:
        cenario: Tipo de cena ('furto', 'depredacao', 'multidao', 'veiculo_suspeito')
        width, height: Dimensões da imagem
        
    Returns:
        np.ndarray: Imagem RGB
    """
    img = np.ones((height, width, 3), dtype=np.uint8) * 180
    
    # Céu
    cv2.rectangle(img, (0, 0), (width, height // 3), (200, 210, 220), -1)
    
    # Chão
    cv2.rectangle(img, (0, height * 2 // 3), (width, height), (160, 160, 150), -1)
    
    # Monumento ao centro
    cv2.rectangle(img, (width//2 - 60, height//4), (width//2 + 60, height*2//3),
                  (120, 120, 120), -1)
    cv2.rectangle(img, (width//2 - 80, height//4 - 20), (width//2 + 80, height//4),
                  (100, 100, 100), -1)
    cv2.putText(img, "MONUMENTO", (width//2 - 70, height//2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (60, 60, 60), 2)
    
    dados_cena = VANDALISM_SCENARIOS.get(cenario, VANDALISM_SCENARIOS["depredacao"])
    
    # Posiciona objetos
    rng = random.Random(42)  # seed fixa para reprodutibilidade
    positions = []
    
    for obj_name, _ in dados_cena["objetos"]:
        # Gera posição não sobreposta
        for _ in range(50):
            x = rng.randint(50, width - 50)
            y = rng.randint(height // 3 + 30, height - 50)
            ok = True
            for px, py, pw, ph in positions:
                if abs(x - px) < 50 and abs(y - py) < 50:
                    ok = False
                    break
            if ok:
                positions.append((x, y, 30, 50))
                break
    
    # Desenha pessoas
    for x, y, w, h in positions[:6]:
        # Corpo
        cv2.circle(img, (x, y - 15), 12, (50, 80, 180), -1)  # cabeça
        cv2.rectangle(img, (x - 12, y), (x + 12, y + 35), (80, 120, 200), -1)  # corpo
        # Pernas
        cv2.line(img, (x - 5, y + 35), (x - 8, y + 55), (40, 40, 120), 3)
        cv2.line(img, (x + 5, y + 35), (x + 8, y + 55), (40, 40, 120), 3)
    
    # Desenha objetos suspeitos
    for i, (obj_name, _) in enumerate(dados_cena["objetos"]):
        if i >= len(positions):
            break
        x, y, w, h = positions[i]
        
        if "faca" in obj_name:
            cv2.rectangle(img, (x + 15, y - 5), (x + 18, y + 25), (0, 0, 0), -1)
            cv2.circle(img, (x + 16, y - 8), 3, (0, 0, 0), -1)
        elif "garrafa" in obj_name:
            cv2.rectangle(img, (x - 18, y), (x - 8, y + 20), (0, 120, 0), 3)
            cv2.circle(img, (x - 13, y - 5), 5, (0, 120, 0), 2)
        elif "taco" in obj_name:
            cv2.rectangle(img, (x - 20, y - 10), (x - 5, y + 30), (139, 69, 19), -1)
            cv2.circle(img, (x - 12, y - 12), 4, (100, 50, 10), -1)
        elif "mochila" in obj_name:
            cv2.rectangle(img, (x + 8, y + 5), (x + 20, y + 25), (200, 100, 0), -1)
        elif "carro" in obj_name:
            cv2.rectangle(img, (x - 30, y - 10), (x + 30, y + 15), (0, 100, 200), -1)
            cv2.circle(img, (x - 20, y + 15), 6, (30, 30, 30), -1)
            cv2.circle(img, (x + 20, y + 15), 6, (30, 30, 30), -1)
    
    return img
