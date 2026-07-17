"""
Módulo de Detecção de Vandalismo em Patrimônios
Usa YOLO + lógica de análise para identificar atividades suspeitas
"""

import time
import numpy as np
from collections import Counter, defaultdict
from typing import Optional

import cv2
import streamlit as st

from config import CONFIDENCE_THRESHOLD, PATRIMONY_CLASSES, INTEREST_CLASSES


# ─── Classes COCO com potencial de vandalismo ───────────────────
VANDALISM_OBJECTS = {
    # Ferramentas/armas que podem danificar monumentos
    "faca": {"risk": 0.8, "type": "corte", "label": "🔪 Faca"},
    "taco_de_beisebol": {"risk": 0.9, "type": "impacto", "label": "🏏 Taco"},
    "garrafa": {"risk": 0.6, "type": "impacto", "label": "🍾 Garrafa"},
    "tesoura": {"risk": 0.8, "type": "corte", "label": "✂️ Tesoura"},
    "skate": {"risk": 0.5, "type": "impacto", "label": "🛹 Skate"},
    "cadeira": {"risk": 0.4, "type": "arremesso", "label": "🪑 Cadeira"},

    # Objetos que sugerem atividade suspeita
    "mochila": {"risk": 0.2, "type": "suspeito", "label": "🎒 Mochila"},
    "bolsa": {"risk": 0.1, "type": "suspeito", "label": "👜 Bolsa"},
}

# Classes que indicam concentração anormal de pessoas
PERSON_CLASS_ID = 0
VEHICLE_CLASSES = {2: "carro", 3: "moto", 5: "ônibus", 7: "caminhão"}


class VandalismDetector:
    """
    Analisa detecções do YOLO para identificar potencial vandalismo.
    Usa regras heurísticas baseadas em objetos detectados e seus padrões.
    """

    def __init__(self):
        self.history = defaultdict(list)  # camera_id -> lista de detecções
        self.max_history = 30  # frames de histórico
        self.alert_cooldown = {}  # camera_id -> timestamp do último alerta

    def analyze(
        self,
        detections: list[dict],
        camera_id: str = "unknown",
        confidence: float = None,
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

        # Filtra por confiança
        valid = [d for d in detections if d.get("confidence", 0) >= conf]

        # Atualiza histórico
        self.history[camera_id].append({
            "time": now,
            "detections": valid,
        })
        if len(self.history[camera_id]) > self.max_history:
            self.history[camera_id].pop(0)

        # Análises
        alerts = []
        risk_score = 0.0
        risk_factors = []

        # 1. Detecta ferramentas/objetos de risco perto de pessoas
        person_count = sum(1 for d in valid if d.get("class_id") == PERSON_CLASS_ID)
        vandal_tools = []
        for d in valid:
            cls_name = d.get("class_name", "")
            if cls_name in VANDALISM_OBJECTS:
                info = VANDALISM_OBJECTS[cls_name]
                vandal_tools.append(d)
                tool_risk = info["risk"]
                # Maior risco se houver pessoas por perto
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

        # 2. Alta concentração de pessoas (possível protesto/aglomeração)
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

        # 3. Pessoa isolada em área de monumento (possível ação)
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

        # 4. Pessoa + veículo (possível fuga ou chegada suspeita)
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

        # 5. Alta densidade de objetos (muitas detecções)
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
            # Verifica cooldown (evita spam a cada frame)
            last_alert = self.alert_cooldown.get(camera_id, 0)
            if now - last_alert > 30:  # 30s de cooldown
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
            return "🔴 CRÍTICO"
        elif score >= 0.5:
            return "🟠 ALTO"
        elif score >= 0.3:
            return "🟡 MÉDIO"
        elif score >= 0.15:
            return "🟢 BAIXO"
        return "✅ NORMAL"

    def _alert_message(self, score: float, top_risk: dict) -> str:
        if not top_risk:
            return "Atividade suspeita detectada"
        obj = top_risk.get("label", "Atividade suspeita")
        if score >= 0.7:
            return f"🚨 VANDALISMO CRÍTICO: {obj}"
        return f"⚠️ ATENÇÃO: {obj}"

    def get_alerts(self, camera_id: Optional[str] = None) -> list[dict]:
        """Retorna alertas ativos"""
        if camera_id:
            return [a for a in self._get_all_alerts() if a["camera_id"] == camera_id]
        return self._get_all_alerts()

    def _get_all_alerts(self) -> list[dict]:
        """Retorna todos os alertas recentes (últimos 5 min)"""
        now = time.time()
        all_alerts = []
        # Alerts stored in alert_cooldown only show the last alert time
        for cid, timestamp in self.alert_cooldown.items():
            if now - timestamp <= 300:  # 5 min
                all_alerts.append({
                    "camera_id": cid,
                    "timestamp": timestamp,
                    "level": "ATIVO",
                })
        return all_alerts

    def annotate_frame(
        self, image: np.ndarray, analysis: dict, detections: list[dict]
    ) -> np.ndarray:
        """
        Desenha indicadores de vandalismo no frame.

        Args:
            image: Imagem original (numpy array RGB)
            analysis: Resultado da análise de vandalismo
            detections: Lista de objetos detectados

        Returns:
            np.ndarray: Imagem com anotações
        """
        annotated = image.copy()
        risk = analysis.get("risk_score", 0)
        h, w = annotated.shape[:2]

        # Barra de risco no topo
        color = (0, 255, 0)  # Verde (baixo risco)
        if risk >= 0.7:
            color = (0, 0, 255)  # Vermelho
        elif risk >= 0.5:
            color = (0, 165, 255)  # Laranja
        elif risk >= 0.3:
            color = (0, 255, 255)  # Amarelo

        bar_height = 6
        bar_width = int(w * risk)
        cv2.rectangle(annotated, (0, 0), (w, bar_height), (30, 30, 30), -1)
        cv2.rectangle(annotated, (0, 0), (bar_width, bar_height), color, -1)

        # Texto de risco
        risk_text = f"Risco: {analysis.get('risk_level', 'NORMAL')} ({risk:.0%})"
        cv2.putText(
            annotated, risk_text, (10, bar_height + 25),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2,
        )

        # Destacar objetos de vandalismo
        for d in detections:
            cls_name = d.get("class_name", "")
            if cls_name in VANDALISM_OBJECTS and "bbox" in d:
                x1, y1, x2, y2 = d["bbox"]
                info = VANDALISM_OBJECTS[cls_name]
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 3)
                label = f"{info['label']} {d.get('confidence',0):.0%}"
                cv2.putText(
                    annotated, label, (x1, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2,
                )

        return annotated

    def generate_report(self, analysis: dict) -> str:
        """Gera relatório textual da análise de vandalismo"""
        lines = ["## 🚨 Relatório de Monitoramento Antivandalismo\n"]
        lines.append(f"**Nível de Risco:** {analysis.get('risk_level', 'NORMAL')}\n")
        lines.append(f"**Score:** {analysis.get('risk_score', 0):.1%}\n")
        lines.append(f"**Pessoas detectadas:** {analysis.get('person_count', 0)}\n")
        lines.append(f"**Veículos detectados:** {analysis.get('vehicle_count', 0)}\n")
        lines.append(f"**Total de objetos:** {analysis.get('total_objects', 0)}\n")

        factors = analysis.get("risk_factors", [])
        if factors:
            lines.append("\n### 🔍 Fatores de Risco:\n")
            for f in sorted(factors, key=lambda x: -x["risk"]):
                lines.append(f"- {f['label']} (risco: {f['risk']:.0%})\n")

        tools = analysis.get("vandal_tools", [])
        if tools:
            lines.append("\n### ⚠️ Objetos Suspeitos Detectados:\n")
            for t in tools:
                lines.append(f"- {t['class_name']} (confiança: {t['confidence']:.0%})\n")

        alerts = analysis.get("alerts", [])
        if alerts:
            lines.append("\n### 🚨 Alertas Emitidos:\n")
            for a in alerts:
                lines.append(f"- [{a['level']}] {a['message']}\n")

        return "\n".join(lines)
