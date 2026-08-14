"""
Detector de Mudanças em Patrimônios.
Combina:
  1. SSIM no ROI da estátua → detecta pichação, danos, peças removidas
  2. HF Model (KzRyan/Burglary_and_Vandalism) → confirma se é roubo/vandalismo

O ROI (Região de Interesse) é extraído do centro do frame,
onde a estátua/monumento está posicionada.
"""

import base64
import logging
import time
from io import BytesIO
from typing import Optional

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

from app.services import zone_service

logger = logging.getLogger(__name__)


def _zone_rect_px(frame: np.ndarray, camera_code: Optional[str] = None) -> tuple:
    """Calcula o retângulo da zona (em pixels do frame original)."""
    zone = zone_service.get_zone(camera_code)
    h, w = frame.shape[:2]
    x1 = int(w * zone["x_start"])
    x2 = int(w * zone["x_end"])
    y1 = int(h * zone["y_start"])
    y2 = int(h * zone["y_end"])
    return x1, y1, x2, y2


def extrair_roi(frame: np.ndarray, camera_code: Optional[str] = None) -> np.ndarray:
    """Extrai a região de interesse (onde está o monumento) do frame.

    Usa a zona calibrada da câmera (zone_service), se houver;
    senão cai no quadrante padrão.
    """
    x1, y1, x2, y2 = _zone_rect_px(frame, camera_code)
    return frame[y1:y2, x1:x2]


class ChangeDetector:
    """
    Detecta mudanças no monumento comparando frames ao longo do tempo.
    
    Fluxo:
    1. set_reference() → captura frame, extrai ROI da estátua, armazena
    2. check() → captura novo frame, extrai ROI, compara com referência via SSIM
    3. Se SSIM mostrar mudança significativa → executa HF model no ROI
    4. Alerta combina: gravidade da mudança SSIM + confirmação HF
    """

    def __init__(self):
        # {camera_code: {
        #     "reference_image": np.ndarray (ROI),
        #     "reference_time": float,
        #     "last_check": float,
        #     "last_hf": dict,
        #     "history": list
        # }}
        self.monitored: dict[str, dict] = {}
        self.change_history: dict[str, list] = {}

    def set_reference(self, camera_code: str, frame: np.ndarray,
                      det_service=None) -> dict:
        """
        Define a imagem de referência do monumento.
        Extrai o ROI (região da estátua) e armazena.
        Se det_service for fornecido, também executa HF model.
        """
        roi = extrair_roi(frame, camera_code)
        hf_result = None
        if det_service and det_service.hf_vandalism.model_loaded:
            try:
                hf_result = det_service.hf_vandalism.predict_image(roi)
            except Exception as e:
                logger.warning(f"HF na referência: {e}")

        self.monitored[camera_code] = {
            "reference_image": roi,
            "reference_time": time.time(),
            "last_check": time.time(),
            "last_hf": hf_result,
        }
        logger.info(f"Referência definida para câmera {camera_code}")
        return {
            "success": True,
            "camera_code": camera_code,
            "timestamp": time.time(),
            "reference_hf": hf_result,
        }

    def check(self, camera_code: str, current_frame: np.ndarray,
              det_service=None, ignore_boxes: Optional[list] = None) -> dict:
        """
        Compara o frame atual com a referência.

        Args:
            camera_code: Código da câmera
            current_frame: Frame atual (numpy RGB)
            det_service: Opcional, para HF model
            ignore_boxes: Opcional, bboxes [x1,y1,x2,y2] (coords do frame
                original) de elementos passageiros (pessoas, veículos)
                detectados pelo YOLO — ver TRANSIENT_CLASSES. Essas áreas
                são excluídas do cálculo de alteração — alguém passando ou
                um carro na rua não pode contar como dano/pichação no
                monumento.

        Returns:
            dict: Resultado com SSIM, mudanças, alerta, HF
        """
        if camera_code not in self.monitored:
            return {"success": False, "error": "Câmera não monitorada. Defina referência primeiro."}

        ref_data = self.monitored[camera_code]
        ref_img = ref_data["reference_image"]

        # Extrai ROI do frame atual e redimensiona para match
        zx1, zy1, zx2, zy2 = _zone_rect_px(current_frame, camera_code)
        current_roi = current_frame[zy1:zy2, zx1:zx2]
        crop_h, crop_w = current_roi.shape[:2]
        current_roi = cv2.resize(current_roi, (ref_img.shape[1], ref_img.shape[0]))
        resized_h, resized_w = ref_img.shape[0], ref_img.shape[1]
        scale_x = resized_w / crop_w if crop_w else 1.0
        scale_y = resized_h / crop_h if crop_h else 1.0

        # ─── 1. SSIM entre ROI de referência e ROI atual ───────────
        gray_ref = cv2.cvtColor(ref_img, cv2.COLOR_RGB2GRAY)
        gray_cur = cv2.cvtColor(current_roi, cv2.COLOR_RGB2GRAY)

        # Normaliza iluminação (CLAHE) para evitar falso-positivo por luz do dia
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray_ref = clahe.apply(gray_ref)
        gray_cur = clahe.apply(gray_cur)

        # Aplica blur leve para reduzir ruído de compressão
        gray_ref = cv2.GaussianBlur(gray_ref, (3, 3), 0)
        gray_cur = cv2.GaussianBlur(gray_cur, (3, 3), 0)

        score, diff_mask = ssim(gray_ref, gray_cur, full=True, data_range=255)
        diff_mask = (1 - diff_mask).astype(np.uint8) * 255

        _, thresh = cv2.threshold(diff_mask, 40, 255, cv2.THRESH_BINARY)  # threshold mais alto
        kernel = np.ones((5, 5), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        # ─── Ignora áreas passageiras (YOLO: pessoas/veículos) no cálculo ──
        # Alguém passando ou um carro na rua muda pixels no ROI, mas isso
        # não é dano/pichação — apaga essas regiões do mapa de diff antes
        # de contar % alterado e regiões, e conta separadamente.
        ignored_count = 0
        if ignore_boxes:
            for (px1, py1, px2, py2) in ignore_boxes:
                ix1, iy1 = max(px1, zx1), max(py1, zy1)
                ix2, iy2 = min(px2, zx2), min(py2, zy2)
                if ix2 <= ix1 or iy2 <= iy1:
                    continue  # fora da zona do monumento
                ignored_count += 1
                rx1 = int((ix1 - zx1) * scale_x)
                ry1 = int((iy1 - zy1) * scale_y)
                rx2 = int((ix2 - zx1) * scale_x)
                ry2 = int((iy2 - zy1) * scale_y)
                cv2.rectangle(thresh, (rx1, ry1), (rx2, ry2), 0, -1)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        total_pixels = thresh.shape[0] * thresh.shape[1]
        changed_pixels = int(np.sum(thresh > 0))
        change_pct = (changed_pixels / total_pixels) * 100

        # Regiões de mudança significativa (área mínima maior para filtrar ruído)
        changes = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 300:  # ignora ruídos muito pequenos
                x, y, w, h = cv2.boundingRect(cnt)
                changes.append({
                    "bbox": [int(x), int(y), int(x + w), int(y + h)],
                    "area_pixels": int(area),
                    "area_percent": round((area / total_pixels) * 100, 3),
                })

        # Gera imagem highlight (diferenças em vermelho no ROI)
        highlight = current_roi.copy()
        overlay = highlight.copy()
        overlay[thresh > 0] = [255, 0, 0]
        highlight = cv2.addWeighted(overlay, 0.4, highlight, 0.6, 0)
        for ch in changes:
            x1, y1, x2, y2 = ch["bbox"]
            cv2.rectangle(highlight, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(highlight, f"{ch['area_percent']:.1f}%",
                        (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX,
                        0.4, (0, 0, 255), 1)

        # Marca (em azul) os elementos passageiros ignorados no diff, pra
        # deixar claro pro operador por que aquela área não entrou na % alterado
        if ignore_boxes:
            for (px1, py1, px2, py2) in ignore_boxes:
                ix1, iy1 = max(px1, zx1), max(py1, zy1)
                ix2, iy2 = min(px2, zx2), min(py2, zy2)
                if ix2 <= ix1 or iy2 <= iy1:
                    continue
                rx1 = int((ix1 - zx1) * scale_x)
                ry1 = int((iy1 - zy1) * scale_y)
                rx2 = int((ix2 - zx1) * scale_x)
                ry2 = int((iy2 - zy1) * scale_y)
                cv2.rectangle(highlight, (rx1, ry1), (rx2, ry2), (255, 180, 0), 2)
                cv2.putText(highlight, "ignorado", (rx1, max(ry1 - 5, 0)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 180, 0), 1)

        ignored_alert = None
        if ignored_count > 0:
            ignored_alert = {
                "level": "INFO",
                "message": (
                    f"👤🚗 {ignored_count} elemento(s) passageiro(s) "
                    f"(pessoas/veículos) perto do monumento "
                    f"(área ignorada na comparação de alteração)"
                ),
                "count": ignored_count,
            }

        # ─── 2. Alerta baseado no SSIM ────────────────────────────
        ssim_alert_level = self._ssim_alert_level(change_pct, len(changes))

        # ─── 3. HF Model no ROI (se disponível) ──────────────────
        hf_result = None
        hf_alert = None
        if det_service and det_service.hf_vandalism.model_loaded:
            try:
                hf_result = det_service.hf_vandalism.predict_image(current_roi)
                hf_alert, _ = self._hf_alert(hf_result)
            except Exception as e:
                logger.warning(f"Erro HF check: {e}")

        # ─── 4. Alerta combinado ─────────────────────────────────
        alert, final_level = self._combined_alert(
            ssim_alert_level, change_pct, changes, hf_result, hf_alert
        )

        # Atualiza estado
        self.monitored[camera_code]["last_check"] = time.time()
        self.monitored[camera_code]["last_hf"] = hf_result

        # Registra histórico
        timestamp = time.time()
        entry = {
            "timestamp": timestamp,
            "similarity_score": round(float(score), 4),
            "change_percentage": round(change_pct, 2),
            "change_regions": len(changes),
            "ssim_alert": ssim_alert_level,
            "hf_prediction": hf_result,
            "alert_level": final_level,
        }
        if camera_code not in self.change_history:
            self.change_history[camera_code] = []
        self.change_history[camera_code].append(entry)
        if len(self.change_history[camera_code]) > 100:
            self.change_history[camera_code].pop(0)

        # Codifica highlight como base64
        _, buffer = cv2.imencode(".jpg", cv2.cvtColor(highlight, cv2.COLOR_RGB2BGR),
                                 [cv2.IMWRITE_JPEG_QUALITY, 85])
        highlight_b64 = base64.b64encode(buffer).decode("utf-8")

        return {
            "success": True,
            "camera_code": camera_code,
            "timestamp": timestamp,
            "similarity_score": round(float(score), 4),
            "change_percentage": round(change_pct, 2),
            "change_regions": len(changes),
            "significant_changes": changes[:10],
            "ssim_alert_level": ssim_alert_level,
            "hf_prediction": hf_result,
            "alert": alert,
            "alert_level": final_level,
            "ignored_objects_count": ignored_count,
            "ignored_objects_alert": ignored_alert,
            "highlight_image_base64": highlight_b64,
            "history_count": len(self.change_history[camera_code]),
        }

    def get_history(self, camera_code: str) -> list:
        """Retorna histórico de verificações"""
        return self.change_history.get(camera_code, [])

    def _ssim_alert_level(self, change_pct: float, num_regions: int) -> str:
        """Nível de alerta baseado na mudança SSIM
        
        Thresholds mais conservadores para evitar falso-positivo:
        - Pequenas variações de iluminação/pessoas passando são NORMAL
        - Só alerta se houver mudança significativa e consistente no monumento
        """
        if change_pct > 20 or num_regions > 15:
            return "CRÍTICO"
        if change_pct > 8 or num_regions > 8:
            return "ALTO"
        if change_pct > 3 or num_regions > 3:
            return "MODERADO"
        return "NORMAL"

    def _hf_alert(self, prediction: dict) -> tuple:
        """Verifica alerta do HF model. Retorna (alert_dict, level)."""
        if not prediction or "error" in prediction:
            return None, None
        burglary = prediction.get("burglary", 0)
        vandalism_val = prediction.get("vandalism", 0)
        max_anormal = max(burglary, vandalism_val)
        if max_anormal < 0.3:
            return None, None
        if max_anormal >= 0.7:
            level = "CRÍTICO"
        elif max_anormal >= 0.5:
            level = "ALTO"
        else:
            level = "MODERADO"
        tipos = []
        if burglary >= 0.3:
            tipos.append("roubo/furto")
        if vandalism_val >= 0.3:
            tipos.append("vandalismo")
        msg = f"{level}: {', '.join(tipos).capitalize()} (confiança: {max_anormal*100:.0f}%)"
        alert = {
            "level": level,
            "max_probability": round(max_anormal, 3),
            "types": tipos,
            "burglary_prob": round(burglary, 3),
            "vandalism_prob": round(vandalism_val, 3),
            "message": msg,
        }
        return alert, level

    def _combined_alert(self, ssim_level: str, change_pct: float,
                        changes: list, hf_result: dict,
                        hf_alert: dict) -> tuple:
        """
        Combina alerta SSIM + HF.
        
        - SSIM sozinho com MODERADO+ já gera alerta de mudança física
        - HF confirma se é roubo/vandalismo
        - Se ambos alertam, nível sobe
        - Se NÃO há mudança física (SSIM ≈ 100%), SUPRIME alerta HF
          (modelo HF tende a dar falso-positivo em imagens estáticas
          pois foi treinado para vídeo e sempre produz ~62% em qualquer frame)
        """
        # Só SSIM já indica mudança física (pichação, dano, peça quebrada)
        has_ssim_change = ssim_level in ("MODERADO", "ALTO", "CRÍTICO")
        has_hf_alert = hf_alert is not None

        # ─── Se NÃO há mudança física, ignora HF completamente ─────
        # O modelo HF (KzRyan/Burglary_and_Vandalism) é de classificação
        # de vídeo e sempre produz ~60-62% em imagens estáticas, gerando
        # falso-positivo. Só consideramos HF se SSIM detectou alteração.
        if not has_ssim_change:
            if has_hf_alert:
                logger.debug(
                    f"HF alert suprimido (SSIM sem mudança): "
                    f"similarity=~{1 - change_pct/100:.4f}, "
                    f"hf={hf_alert.get('max_probability', 0):.3f}"
                )
            # Sem mudança SSIM → NORMAL, mesmo que HF alerte
            return None, "NORMAL"

        if has_ssim_change and has_hf_alert:
            # Ambos confirmam: alerta combinado
            hf_level = hf_alert["level"]
            if ssim_level == "CRÍTICO" or hf_level == "CRÍTICO":
                level = "CRÍTICO"
            elif ssim_level == "ALTO" or hf_level == "ALTO":
                level = "ALTO"
            else:
                level = "MODERADO"
            msg = (f"🚨 {level}: Mudança física detectada no monumento "
                   f"({change_pct:.1f}% alterado) + "
                   f"HF confirma {', '.join(hf_alert['types'])}")
            alert = {"level": level, "message": msg, "source": "ssim+hf"}
            return alert, level

        if has_ssim_change:
            # Só mudança física (sem confirmação HF)
            level = ssim_level
            msg = (f"⚠️ {level}: {change_pct:.1f}% do monumento alterado "
                   f"({len(changes)} região(is))")
            alert = {"level": level, "message": msg, "source": "ssim"}
            return alert, level

        return None, "NORMAL"
