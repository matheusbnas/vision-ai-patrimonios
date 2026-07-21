"""
Módulo de Detecção de Vandalismo em Patrimônios
Usa YOLO + lógica heurística + modelo do Hugging Face
"""

import time
import logging
from collections import defaultdict
from typing import Optional

import numpy as np

from app.config import CONFIDENCE_THRESHOLD

logger = logging.getLogger(__name__)


# ─── Classes COCO com potencial de vandalismo ───────────────────
VANDALISM_OBJECTS = {
    "faca": {"risk": 0.8, "type": "corte", "label": "🔪 Faca"},
    "taco_de_beisebol": {"risk": 0.9, "type": "impacto", "label": "🏏 Taco"},
    "garrafa": {"risk": 0.6, "type": "impacto", "label": "🍾 Garrafa"},
    "tesoura": {"risk": 0.8, "type": "corte", "label": "✂️ Tesoura"},
    "skate": {"risk": 0.5, "type": "impacto", "label": "🛹 Skate"},
    "cadeira": {"risk": 0.4, "type": "arremesso", "label": "🪑 Cadeira"},
    "mochila": {"risk": 0.2, "type": "suspeito", "label": "🎒 Mochila"},
    "bolsa": {"risk": 0.1, "type": "suspeito", "label": "👜 Bolsa"},
}

PERSON_CLASS_ID = 0
VEHICLE_CLASSES = {2: "carro", 3: "moto", 5: "ônibus", 7: "caminhão"}


class VandalismDetector:
    """
    Analisa detecções do YOLO para identificar potencial vandalismo.
    Usa regras heurísticas baseadas em objetos detectados e seus padrões.
    """

    def __init__(self):
        self.history = defaultdict(list)
        self.max_history = 30
        self.alert_cooldown = {}

    def analyze(
        self,
        detections: list[dict],
        camera_id: str = "unknown",
        confidence: Optional[float] = None,
    ) -> dict:
        """
        Analisa detecções em busca de sinais de vandalismo.

        Args:
            detections: Lista de objetos detectados pelo YOLO
            camera_id: Identificador da câmera
            confidence: Threshold de confiança

        Returns:
            dict: Resultado da análise de vandalismo
        """
        conf = confidence or CONFIDENCE_THRESHOLD
        now = time.time()

        valid = [d for d in detections if d.get("confidence", 0) >= conf]

        # Atualiza histórico
        self.history[camera_id].append({
            "time": now,
            "detections": valid,
        })
        if len(self.history[camera_id]) > self.max_history:
            self.history[camera_id].pop(0)

        alerts = []
        risk_score = 0.0
        risk_factors = []

        # 1. Detecta ferramentas/objetos de risco
        person_count = sum(1 for d in valid if d.get("class_id") == PERSON_CLASS_ID)
        vandal_tools = []
        for d in valid:
            cls_name = d.get("class_name", "")
            if cls_name in VANDALISM_OBJECTS:
                info = VANDALISM_OBJECTS[cls_name]
                vandal_tools.append(d)
                tool_risk = info["risk"]
                if person_count > 0:
                    tool_risk *= 1.5
                risk_score += tool_risk
                risk_factors.append({
                    "object": cls_name,
                    "label": info["label"],
                    "type": info["type"],
                    "risk": min(tool_risk, 1.0),
                    "count": 1,
                })

        # Agrupa ferramentas iguais
        if risk_factors:
            grouped = {}
            for rf in risk_factors:
                k = rf["object"]
                if k in grouped:
                    grouped[k]["count"] += 1
                    grouped[k]["risk"] = min(grouped[k]["risk"] + rf["risk"] * 0.5, 1.0)
                else:
                    grouped[k] = rf
            risk_factors = list(grouped.values())

        # 2. Alta concentração de pessoas
        if person_count >= 5:
            crowd_risk = min(0.3 + (person_count - 5) * 0.05, 0.8)
            risk_score += crowd_risk
            risk_factors.append({
                "object": "aglomeracao",
                "label": f"👥 Aglomeração ({person_count} pessoas)",
                "type": "multidao",
                "risk": crowd_risk,
                "count": person_count,
            })

        # 3. Pessoa isolada em área de monumento
        if person_count == 1 and len(valid) <= 3:
            lone_risk = 0.15
            risk_score += lone_risk
            risk_factors.append({
                "object": "pessoa_isolada",
                "label": "🧍 Pessoa isolada no monumento",
                "type": "vigilancia",
                "risk": lone_risk,
                "count": 1,
            })

        # 4. Pessoa + veículo (possível fuga)
        vehicle_count = sum(1 for d in valid if d.get("class_id") in VEHICLE_CLASSES)
        if person_count > 0 and vehicle_count > 0:
            vehicle_risk = min(0.1 + person_count * 0.05, 0.4)
            risk_score += vehicle_risk
            risk_factors.append({
                "object": "pessoas_veiculos",
                "label": f"🚗 {person_count} pessoa(s) + {vehicle_count} veículo(s)",
                "type": "movimentacao",
                "risk": vehicle_risk,
                "count": person_count + vehicle_count,
            })

        # 5. Alta densidade de objetos
        if len(valid) > 15:
            density_risk = min(0.1 + (len(valid) - 15) * 0.02, 0.5)
            risk_score += density_risk
            risk_factors.append({
                "object": "alta_densidade",
                "label": f"📊 Alta atividade ({len(valid)} objetos)",
                "type": "movimentacao",
                "risk": density_risk,
                "count": len(valid),
            })

        # Normaliza risco para 0-1
        risk_score = min(max(risk_score, 0.0), 1.0)

        # Gera alertas se risco alto
        if risk_score >= 0.5:
            last_alert = self.alert_cooldown.get(camera_id, 0)
            if now - last_alert > 30:
                top_risk = max(risk_factors, key=lambda x: x["risk"]) if risk_factors else {}
                alerts.append({
                    "level": "ALTO" if risk_score >= 0.7 else "MODERADO",
                    "score": round(risk_score, 2),
                    "message": self._alert_message(risk_score, top_risk),
                    "timestamp": now,
                    "camera_id": camera_id,
                })
                self.alert_cooldown[camera_id] = now

        return {
            "risk_score": round(risk_score, 3),
            "risk_level": self._risk_level(risk_score),
            "risk_factors": risk_factors,
            "alerts": alerts,
            "person_count": person_count,
            "vehicle_count": vehicle_count,
            "total_objects": len(valid),
            "has_vandal_tools": len(vandal_tools) > 0,
            "vandal_tools": [
                {"class_name": d["class_name"], "confidence": d["confidence"]}
                for d in vandal_tools
            ],
        }

    def _risk_level(self, score: float) -> str:
        if score >= 0.7:
            return "CRÍTICO"
        if score >= 0.5:
            return "ALTO"
        if score >= 0.3:
            return "MODERADO"
        return "BAIXO"

    def _alert_message(self, score: float, top_risk: dict) -> str:
        if score >= 0.7:
            return f"🚨 ALTA PROBABILIDADE DE VANDALISMO: {top_risk.get('label', 'Atividade suspeita')}"
        return f"⚠️ ATENÇÃO: {top_risk.get('label', 'Atividade suspeita')} detectado(a)"
