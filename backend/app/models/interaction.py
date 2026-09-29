"""
Interação de pessoas com a estátua, via YOLO-pose (keypoints COCO).

A ideia é separar o comportamento normal de turista (sentar ao lado,
abraçar, segurar a mão do Drummond pra foto) do que é suspeito:

  - mão dentro da ÁREA SENSÍVEL (óculos/cabeça, violão...) — alvo típico
    de furto. Pose pra foto dura segundos: só vira ALTO se a MESMA pessoa
    ficar com a mão lá por INTERACTION_ESCALATE_SECONDS. Antes, MODERADO
    (histórico, sem som);
  - pessoa EM PÉ em cima da estátua/pedestal: os dois tornozelos acima da
    base, dentro do contorno, com as pernas esticadas (joelho quase reto).
    Sentado no banco do Drummond — perna cruzada ou pés no banco — tem o
    joelho dobrado e não conta. ALTO depois de CLIMB_CONFIRM_SECONDS da
    MESMA pessoa.

"Mesma pessoa": na análise contínua (vídeo) cada pose é casada com o ID do
rastreamento (ByteTrack) — turistas se revezando pra foto não somam tempo.
Nos prints (câmeras sem vídeo contínuo) não há ID; a tolerância entre
detecções é maior (os prints são espaçados) e cada evento conta por câmera.

Limitação: nos prints, um gesto rápido entre dois deles passa despercebido —
por isso a change_detector escala para CRÍTICO uma mudança física
confirmada no contorno logo depois de uma interação confirmada
(INTERACTION_MEMORY_SECONDS).
"""

import logging
import math
import threading
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.config import (
    POSE_MODEL,
    POSE_KEYPOINT_CONF,
    CLIMB_FOOT_MIN_HEIGHT,
    CLIMB_CONFIRM_SECONDS,
    INTERACTION_ESCALATE_SECONDS,
    INTERACTION_GRACE_SECONDS,
    STATUE_SELF_IOU,
)

logger = logging.getLogger(__name__)

# Índices dos keypoints COCO-17
WRISTS = (9, 10)
HIPS = (11, 12)
KNEES = (13, 14)
ANKLES = (15, 16)
# Joelho com ângulo acima disto = perna esticada (em pé). Sentado ≈ 90-120°.
STANDING_KNEE_ANGLE = 145
# Nos prints (sem vídeo) a mesma situação reaparece minutos depois: tolera
# esse intervalo sem zerar a contagem
PRINT_GRACE_SECONDS = 300

EVENT_LABEL = {"mao_area_sensivel": "mao na area sensivel", "em_cima_da_estatua": "em cima da estatua"}
EVENT_NEEDED = {"mao_area_sensivel": INTERACTION_ESCALATE_SECONDS, "em_cima_da_estatua": CLIMB_CONFIRM_SECONDS}

# Última interação CONFIRMADA por câmera (timestamp) — lida pela change_detector
_last_interaction: dict[str, float] = {}
# (câmera, evento, pessoa) → (primeira vez visto, última vez visto)
_event_seen: dict[tuple[str, str, str], tuple[float, float]] = {}
_lock = threading.Lock()


def last_interaction(camera_code: str) -> Optional[float]:
    with _lock:
        return _last_interaction.get(camera_code)


def _event_dwell(camera_code: str, present: set[tuple[str, str]], now: float,
                 grace: float = INTERACTION_GRACE_SECONDS) -> dict[tuple[str, str], float]:
    """Há quanto tempo cada (evento, pessoa) está acontecendo. Ausência
    menor que `grace` (pose que "pisca") não zera a contagem."""
    dwell = {}
    with _lock:
        for key in [k for k in _event_seen if k[0] == camera_code and (k[1], k[2]) not in present]:
            if now - _event_seen[key][1] > grace:
                del _event_seen[key]
        for ev, who in present:
            first, _ = _event_seen.get((camera_code, ev, who), (now, now))
            _event_seen[(camera_code, ev, who)] = (first, now)
            dwell[(ev, who)] = now - first
    return dwell


def clear(camera_code: str, grace: float = INTERACTION_GRACE_SECONDS) -> None:
    """Ninguém junto da estátua neste frame/print: expira as contagens."""
    _event_dwell(camera_code, set(), time.time(), grace)


def _inside(pt, box, margin: float = 0.0) -> bool:
    x, y = pt
    x1, y1, x2, y2 = box
    mx, my = (x2 - x1) * margin, (y2 - y1) * margin
    return x1 - mx <= x <= x2 + mx and y1 - my <= y <= y2 + my


def _overlap_frac(a, b) -> float:
    """Fração da caixa `a` que está dentro da caixa `b`."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    area_a = max((a[2] - a[0]) * (a[3] - a[1]), 1)
    return (ix2 - ix1) * (iy2 - iy1) / area_a


def iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def is_statue_itself(bbox, statue_px) -> bool:
    """Detecção de 'pessoa' que é a própria estátua (figura humana).

    IoU alto com o contorno, ou caixa inteira dentro do contorno ocupando
    boa parte dele (estátuas pequenas no quadro, onde a caixa do YOLO sai
    mais justa que o contorno calibrado e o IoU fica baixo).
    """
    if not statue_px:
        return False
    if iou(bbox, statue_px) >= STATUE_SELF_IOU:
        return True
    area_box = max((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]), 1)
    area_statue = max((statue_px[2] - statue_px[0]) * (statue_px[3] - statue_px[1]), 1)
    return _overlap_frac(bbox, statue_px) >= 0.9 and area_box / area_statue >= 0.3


def _knee_angle(pts, side: int) -> Optional[float]:
    """Ângulo (graus) no joelho entre coxa e canela; None se pontos incertos."""
    hip, knee, ankle = pts[HIPS[side]], pts[KNEES[side]], pts[ANKLES[side]]
    if min(hip[2], knee[2], ankle[2]) < POSE_KEYPOINT_CONF:
        return None
    v1 = (hip[0] - knee[0], hip[1] - knee[1])
    v2 = (ankle[0] - knee[0], ankle[1] - knee[1])
    n = math.hypot(*v1) * math.hypot(*v2)
    if n == 0:
        return None
    cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / n))
    return math.degrees(math.acos(cos))


def _is_standing(pts) -> bool:
    """Em pé = as pernas visíveis estão esticadas (e pelo menos uma visível)."""
    angles = [a for a in (_knee_angle(pts, 0), _knee_angle(pts, 1)) if a is not None]
    return bool(angles) and all(a >= STANDING_KNEE_ANGLE for a in angles)


class InteractionAnalyzer:
    def __init__(self):
        self.model = None
        self.model_loaded = False
        self._load_failed = False
        # Modelos ultralytics não são thread-safe — a análise contínua
        # (live_analysis) e as rotas/background usam o mesmo analisador
        self._infer_lock = threading.Lock()

    def load_model(self) -> bool:
        if self.model_loaded or self._load_failed:
            return self.model_loaded
        try:
            from ultralytics import YOLO
            self.model = YOLO(str(Path(POSE_MODEL)))  # ultralytics baixa se não existir
            self.model_loaded = True
            logger.info(f"Modelo YOLO-pose carregado: {POSE_MODEL}")
        except Exception as e:
            # Não tenta de novo a cada print (download bloqueado etc.)
            self._load_failed = True
            logger.error(f"YOLO-pose indisponível — análise de interação desativada: {e}")
        return self.model_loaded

    def analyze(self, image: np.ndarray, camera_code: str,
                statue_px: tuple, sensitive_px: Optional[tuple],
                annotated: Optional[np.ndarray] = None,
                statue_boxes: Optional[list] = None,
                people: Optional[list[tuple[list, Optional[int]]]] = None,
                continuous: bool = False) -> Optional[dict]:
        """
        Roda pose num recorte ao redor da estátua (pessoas pequenas no
        quadro ganham resolução) e devolve o alerta de interação, se houver.

        people: [(bbox, track_id)] das pessoas rastreadas — casa cada pose
            com o ID pra contar o tempo por pessoa (análise contínua).
        continuous: True no vídeo (tolerância curta entre frames); False
            nos prints (tolerância longa, prints espaçados).

        Desenha no `annotated` (se dado) os pontos que dispararam a regra.
        O retorno traz `progress` (quem está em qual regra e há quanto
        tempo), mesmo antes de confirmar — pra mostrar no vídeo.
        """
        grace = INTERACTION_GRACE_SECONDS if continuous else PRINT_GRACE_SECONDS
        if not self.load_model():
            return None

        h, w = image.shape[:2]
        sx1, sy1, sx2, sy2 = statue_px
        pad_x, pad_y = (sx2 - sx1) * 0.6, (sy2 - sy1) * 0.4
        cx1, cy1 = max(int(sx1 - pad_x), 0), max(int(sy1 - pad_y), 0)
        cx2, cy2 = min(int(sx2 + pad_x), w), min(int(sy2 + pad_y), h)
        crop = image[cy1:cy2, cx1:cx2]
        if crop.size == 0:
            return None

        try:
            with self._infer_lock:
                results = self.model(crop, conf=0.3, verbose=False)
        except Exception as e:
            logger.warning(f"Erro YOLO-pose: {e}")
            return None

        climb_floor = sy2 - (sy2 - sy1) * CLIMB_FOOT_MIN_HEIGHT
        present: set[tuple[str, str]] = set()   # (evento, pessoa)
        hits: list[tuple] = []  # (x, y, cor) pra desenhar

        res = results[0] if results else None
        kps = getattr(res, "keypoints", None)
        if kps is not None and kps.data is not None and len(kps.data) > 0:
            boxes = res.boxes.xyxy.cpu().numpy() if res.boxes is not None else []
            for i, person in enumerate(kps.data.cpu().numpy()):  # (17, 3): x, y, conf
                pts = [(x + cx1, y + cy1, c) for x, y, c in person]
                who = "?"
                if i < len(boxes):
                    bx = boxes[i]
                    pbox = (bx[0] + cx1, bx[1] + cy1, bx[2] + cx1, bx[3] + cy1)
                    # Só quem está junto da estátua interessa — e a própria
                    # estátua (figura humana) também sai pelo pose
                    if (_overlap_frac(pbox, statue_px) < 0.1 or is_statue_itself(pbox, statue_px)
                            or any(iou(pbox, sb) >= 0.5 for sb in (statue_boxes or []))):
                        continue
                    # Casa a pose com a pessoa rastreada (maior IoU)
                    best = max(((iou(pbox, pb), tid) for pb, tid in (people or []) if tid is not None),
                               default=(0.0, None))
                    if best[0] >= 0.3:
                        who = str(best[1])
                    elif not continuous:
                        who = "print"
                    else:
                        who = f"p{i}"

                if sensitive_px:
                    for k in WRISTS:
                        x, y, c = pts[k]
                        if c >= POSE_KEYPOINT_CONF and _inside((x, y), sensitive_px, margin=0.1):
                            present.add(("mao_area_sensivel", who))
                            hits.append((x, y, (255, 0, 255)))

                # Em cima = os dois tornozelos visíveis, dentro do contorno,
                # acima da base E pernas esticadas (em pé). Perna cruzada ou
                # pés no banco de quem está sentado ficam de fora.
                raised = [pts[k] for k in ANKLES
                          if pts[k][2] >= POSE_KEYPOINT_CONF and sx1 <= pts[k][0] <= sx2
                          and sy1 <= pts[k][1] < climb_floor]
                if len(raised) == len(ANKLES) and _is_standing(pts):
                    present.add(("em_cima_da_estatua", who))
                    hits.extend((x, y, (255, 0, 0)) for x, y, _ in raised)

        now = time.time()
        dwell = _event_dwell(camera_code, present, now, grace)
        if not present:
            return None

        if annotated is not None:
            for x, y, color in hits:
                cv2.circle(annotated, (int(x), int(y)), 9, color, 3)

        # Tempo da pessoa há mais tempo em cada regra
        def top(ev: str) -> tuple[float, Optional[str]]:
            cands = [(s, who) for (e, who), s in dwell.items() if e == ev]
            return max(cands) if cands else (0.0, None)

        climb_secs, climb_who = top("em_cima_da_estatua")
        hand_secs, hand_who = top("mao_area_sensivel")
        progress = [
            {"event": ev, "label": EVENT_LABEL[ev], "who": who, "seconds": round(s, 1),
             "needed": EVENT_NEEDED[ev]}
            for (ev, who), s in sorted(dwell.items(), key=lambda kv: -kv[1])
        ]

        confirmed = climb_secs >= CLIMB_CONFIRM_SECONDS or hand_secs >= INTERACTION_ESCALATE_SECONDS
        # Só interação confirmada "arma" a escalada da mudança física para
        # CRÍTICO — turista encostando pra foto não pode armar
        if confirmed:
            with _lock:
                _last_interaction[camera_code] = now

        def pessoa(who):
            return f"pessoa #{who}" if who and who.isdigit() else "pessoa"

        if climb_secs >= CLIMB_CONFIRM_SECONDS:
            level = "ALTO"
            msg = f"🚨 ALTO: {pessoa(climb_who).capitalize()} em pé em cima da estátua/pedestal há {int(climb_secs)}s"
        elif hand_secs >= INTERACTION_ESCALATE_SECONDS:
            level = "ALTO"
            msg = (f"🚨 ALTO: {pessoa(hand_who).capitalize()} com a mão na área sensível da estátua há "
                   f"{int(hand_secs)}s — possível tentativa de retirada de peça")
        elif climb_who is not None:
            level = "MODERADO"
            msg = (f"⚠️ MODERADO: Possível {pessoa(climb_who)} em cima da estátua/pedestal "
                   f"(confirmando {int(climb_secs)}/{int(CLIMB_CONFIRM_SECONDS)}s)")
        else:
            level = "MODERADO"
            msg = (f"⚠️ MODERADO: {pessoa(hand_who).capitalize()} com a mão na área sensível "
                   f"(normal em foto; alerta se passar de {int(INTERACTION_ESCALATE_SECONDS)}s)")

        return {
            "level": level,
            "message": msg,
            "events": sorted({ev for ev, _ in present}),
            "dwell_seconds": round(max(climb_secs, hand_secs), 1),
            "progress": progress,
        }


# Instância única compartilhada por todos os detectores (um só modelo de
# pose na memória, mesmo com um detector por câmera na análise contínua)
shared_analyzer = InteractionAnalyzer()
