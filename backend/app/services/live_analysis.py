"""
Análise CONTÍNUA sobre o vídeo ao vivo (fase 2 da cascata).

Para cada câmera com captura contínua (live_capture), roda o YOLO com
rastreamento (ByteTrack) a LIVE_ANALYSIS_FPS sobre o frame mais recente:

  existe pessoa? → perto da estátua? → há quanto tempo ESTA pessoa (ID)?
      → pose (mão na área sensível / em cima) → alertas

Diferença pro monitoramento por prints: com ID por pessoa, a permanência
é real ("pessoa #12 encostada na estátua há 4 min"), não "sempre tem
alguém" — em monumento turístico isso era sempre verdade.

Detecção com pessoa identificada (superfície protegida):
  - a superfície protegida é o contorno calibrado da estátua (vermelho) e
    a zona monitorada é o quadrante da câmera (amarelo);
  - cada pessoa rastreada tem um estado: "passando" (fora da zona),
    "na_zona" ou "suspeito" (ficou junto à superfície por
    SURFACE_SUSPECT_SECONDS);
  - SurfaceMonitor compara a superfície visível com um fundo que se
    atualiza sozinho; mudança sustentada com um suspeito presente (ou
    visto há pouco) → alerta CRÍTICO em poucos segundos, com imagens
    antes/durante/depois e um trecho do vídeo (evidence_service).
  O alerta é sempre um POSSÍVEL evento pra validação humana: não há
  reconhecimento facial nem identificação de pessoas — o "#ID" é só o
  número do rastreamento enquanto a pessoa está em cena.

O resultado (frame anotado + detecções + alertas) fica em latest_result()
e é o que as rotas /live, /multi e o background_monitor usam para essas
câmeras, em vez de rodar a detecção de novo (evita estado de rastreamento
duplicado e alertas repetidos).
"""

import logging
import threading
import time
from collections import deque
from datetime import datetime
from typing import Optional

import cv2
import numpy as np

from app.config import (
    LIVE_ANALYSIS_FPS,
    PERSON_LOITERING_ALERT_SECONDS,
    SURFACE_SUSPECT_SECONDS,
    SURFACE_SUSPECT_MEMORY_SECONDS,
    SURFACE_CHANGE_MIN_FRAC,
    SURFACE_CRITICAL_FRAC,
    SURFACE_CHANGE_CONFIRM_SECONDS,
    SURFACE_UNATTRIBUTED_ABSORB_SECONDS,
    SURFACE_EVENT_COOLDOWN_SECONDS,
    EVIDENCE_PRE_SECONDS,
    EVIDENCE_POST_SECONDS,
)
from app.models.detector import PatrimonyDetector, _zone_box, _frac_box
from app.models.surface_monitor import SurfaceMonitor
from app.services import alert_service, evidence_service, live_capture, zone_service

logger = logging.getLogger(__name__)

# ID que some por mais que isto é descartado (saiu de cena)
TRACK_FORGET_SECONDS = 10
# "Pessoa" sobre o contorno que não se move (centro desloca menos que
# STATIC_MAX_SHIFT da largura do frame) por STATIC_MIN_SECONDS = a estátua
STATIC_MIN_SECONDS = 15
STATIC_MAX_SHIFT = 0.02
# Superfície "desobstruída" pra servir de imagem ANTES do evento
BEFORE_MIN_VISIBLE = 0.9
# Faixa vermelha "possível pichação" no vídeo por este tempo após o alerta;
# depois, só a linha "alerta registrado às ..." até EVENT_NOTE_SECONDS
EVENT_BANNER_SECONDS = 20
EVENT_NOTE_SECONDS = 600

# Cores (RGB) da sobreposição
_GREEN = (70, 200, 70)
_ORANGE = (255, 160, 0)
_RED = (230, 30, 30)
_YELLOW = (255, 215, 0)
_MAGENTA = (255, 0, 200)
_STATE_COLOR = {"passando": _GREEN, "na_zona": _ORANGE, "suspeito": _RED}
# Hershey (cv2.putText) não desenha acento nem "·" — rótulos em ASCII
_STATE_LABEL = {"na_zona": "Pessoa - na zona", "suspeito": "Pessoa - suspeito"}


def _within_reach(bbox: list, surface_px: tuple) -> bool:
    """Pessoa ao alcance da superfície: caixa a até ~um braço (0,35 da altura
    da pessoa) do contorno. Sobreposição com o contorno não basta —
    superfície estreita (poste, pedestal) quase não fica "dentro" da caixa
    de quem está ao lado. Altura em vez de largura: varia menos com a pose."""
    x1, y1, x2, y2 = bbox
    sx1, sy1, sx2, sy2 = surface_px
    reach = (y2 - y1) * 0.35
    dx = max(sx1 - x2, x1 - sx2, 0)
    dy = max(sy1 - y2, y1 - sy2, 0)
    return dx <= reach and dy <= reach


class CameraAnalysis:
    def __init__(self, code: str):
        self.code = code
        # Um detector por câmera: o estado do ByteTrack fica no modelo
        self.detector = PatrimonyDetector()
        self.last_seq = -1
        self.last_run = 0.0
        # track_id → {"first": ts, "last": ts, "near_since": ts|None,
        #             "origin": (cx, cy), "max_shift": float, "suspect": bool}
        self.tracks: dict[int, dict] = {}
        # IDs reconhecidos como a própria estátua (parados sobre o contorno)
        self.statue_ids: set[int] = set()
        # Suspeitos recentes (track_id → último ts visto), sobrevivem ao track
        self.recent_suspects: dict[int, float] = {}
        self.surface = SurfaceMonitor()
        # Evidências: frames anotados recentes (ts, jpeg) pro clipe
        self.evidence_buf: deque = deque()
        self.before_jpg: Optional[bytes] = None
        self.change_since: Optional[float] = None
        self.pending: Optional[dict] = None     # evento aguardando o "depois"
        self.cooldown_until = 0.0
        self.last_event: Optional[dict] = None  # meta do último evento (frontend)
        self.result: Optional[dict] = None
        self.result_seq = 0                     # incrementa a cada análise (MJPEG)
        self.name: Optional[str] = None
        self._lock = threading.Lock()
        self._times: list[float] = []  # ts das últimas análises (FPS real)

    def update_tracks(self, objects: list[dict], ts: float, frame_w: int,
                      surface_px: Optional[tuple] = None) -> list[dict]:
        """Atualiza permanência e estado por ID (grava d["state"]); devolve as pessoas junto à estátua."""
        near_now = []
        for d in objects:
            tid = d.get("track_id")
            if d["class_name"] != "pessoa" or tid is None:
                continue
            x1, y1, x2, y2 = d["bbox"]
            center = ((x1 + x2) / 2, (y1 + y2) / 2)
            t = self.tracks.setdefault(tid, {"first": ts, "last": ts, "near_since": None,
                                             "origin": center, "max_shift": 0.0, "suspect": False})
            t["last"] = ts
            shift = max(abs(center[0] - t["origin"][0]), abs(center[1] - t["origin"][1])) / max(frame_w, 1)
            t["max_shift"] = max(t["max_shift"], shift)
            # Estátua: parada sobre o contorno tempo suficiente
            if (tid not in self.statue_ids and (d["statue_overlap"] or 0) >= 0.8
                    and ts - t["first"] >= STATIC_MIN_SECONDS and t["max_shift"] < STATIC_MAX_SHIFT):
                self.statue_ids.add(tid)
                self.recent_suspects.pop(tid, None)
                logger.info(f"[análise {self.code}] ID #{tid} reconhecido como a própria estátua (parado)")
            if d.get("is_statue") or tid in self.statue_ids:
                continue
            # Com contorno calibrado: ao alcance da superfície; sem: dentro da zona
            near = _within_reach(d["bbox"], surface_px) if surface_px else d["in_zone"]
            if near:
                t["near_since"] = t["near_since"] or ts
                near_now.append({"track_id": tid, "seconds": round(ts - t["near_since"], 1)})
                if ts - t["near_since"] >= SURFACE_SUSPECT_SECONDS:
                    t["suspect"] = True
            else:
                t["near_since"] = None
            # Suspeito continua suspeito enquanto está em cena (mesmo se afastar)
            if t["suspect"]:
                self.recent_suspects[tid] = ts
                d["state"] = "suspeito"
            else:
                d["state"] = "na_zona" if d["in_zone"] or near else "passando"
        for tid in [k for k, v in self.tracks.items() if ts - v["last"] > TRACK_FORGET_SECONDS]:
            del self.tracks[tid]
            self.statue_ids.discard(tid)
        for tid in [k for k, v in self.recent_suspects.items() if ts - v > SURFACE_SUSPECT_MEMORY_SECONDS]:
            del self.recent_suspects[tid]
        return sorted(near_now, key=lambda x: -x["seconds"])

    def analysis_fps(self) -> float:
        now = time.time()
        recent = [t for t in self._times if now - t <= 10]
        return round((len(recent) - 1) / (recent[-1] - recent[0]), 2) if len(recent) > 1 else 0.0


# ─── Sobreposição (desenhada sobre o frame limpo) ───────────────

def _label(img: np.ndarray, text: str, org: tuple, color: tuple, scale: float):
    """Texto colorido sobre fundo escuro, acima de `org` (canto sup. esq. da caixa)."""
    th = max(int(scale * 2), 1)
    (w, h), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, th)
    x, y = org[0], max(org[1] - 4, h + base + 2)
    cv2.rectangle(img, (x, y - h - base - 2), (x + w + 6, y + 2), (25, 25, 25), -1)
    cv2.putText(img, text, (x + 3, y - base), cv2.FONT_HERSHEY_SIMPLEX, scale, color, th, cv2.LINE_AA)


def _banner(img: np.ndarray, text: str, scale: float, strong: bool):
    h, w = img.shape[:2]
    th = max(int(scale * 2), 1)
    (tw, tht), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, th)
    bar = tht + base + 12
    if strong:
        cv2.rectangle(img, (0, h - bar), (w, h), _RED, -1)
        cv2.rectangle(img, (0, 0), (w - 1, h - 1), _RED, max(int(4 * scale), 2))
        cv2.putText(img, text, ((w - tw) // 2, h - base - 6), cv2.FONT_HERSHEY_SIMPLEX,
                    scale, (255, 255, 255), th, cv2.LINE_AA)
    else:
        cv2.rectangle(img, (0, h - bar), (tw + 12, h), (160, 20, 20), -1)
        cv2.putText(img, text, (6, h - base - 6), cv2.FONT_HERSHEY_SIMPLEX,
                    scale, (255, 255, 255), th, cv2.LINE_AA)


def draw_overlay(img: np.ndarray, objects: list[dict], zone_px: tuple, surface_px: Optional[tuple],
                 surface: Optional[dict], risk_objects: list[dict], last_event: Optional[dict], ts: float):
    """Zona (amarelo), superfície (vermelho), mudança (magenta) e pessoas por estado."""
    s = max(img.shape[1] / 1280, 0.4)
    lw = max(int(2 * s), 1)
    zx1, zy1, zx2, zy2 = zone_px
    cv2.rectangle(img, (zx1, zy1), (zx2, zy2), _YELLOW, lw)
    _label(img, "Zona monitorada", (zx1, zy2 + int(24 * s)), _YELLOW, 0.5 * s)

    if surface_px:
        sx1, sy1, sx2, sy2 = surface_px
        if surface and surface.get("mask") is not None:
            roi = img[sy1:sy2, sx1:sx2]
            m = surface["mask"][:roi.shape[0], :roi.shape[1]]
            roi[m] = (0.45 * roi[m] + 0.55 * np.array(_MAGENTA)).astype(np.uint8)
        cv2.rectangle(img, (sx1, sy1), (sx2, sy2), _RED, lw + 1)
        _label(img, "Superficie protegida", (sx1, sy2 + int(24 * s)), _RED, 0.5 * s)

    for d in objects:
        state = d.get("state")
        if d["class_name"] != "pessoa" or d.get("is_statue") or not state:
            continue
        x1, y1, x2, y2 = d["bbox"]
        color = _STATE_COLOR[state]
        cv2.rectangle(img, (x1, y1), (x2, y2), color, lw if state == "passando" else lw + 1)
        if state in _STATE_LABEL:
            _label(img, f"{_STATE_LABEL[state]} #{d['track_id']}", (x1, y1), color, 0.5 * s)

    for d in risk_objects:
        x1, y1, x2, y2 = d["bbox"]
        cv2.rectangle(img, (x1, y1), (x2, y2), _RED, lw + 1)
        _label(img, d["class_name"], (x1, y1), _RED, 0.5 * s)

    if last_event:
        age = ts - last_event["timestamp"]
        if age <= EVENT_BANNER_SECONDS:
            _banner(img, "Possivel pichacao detectada - requer validacao humana", 0.7 * s, True)
        elif age <= EVENT_NOTE_SECONDS:
            hhmm = datetime.fromtimestamp(last_event["timestamp"]).strftime("%H:%M:%S")
            _banner(img, f"Alerta registrado as {hhmm}", 0.5 * s, False)


class LiveAnalyzer:
    def __init__(self, fps: float):
        self.interval = 1.0 / fps
        self.cameras: dict[str, CameraAnalysis] = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="live-analysis", daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        from app.api import monitor as monitor_api  # import tardio (evita ciclo)

        # Uma thread, câmeras em rodízio: inferência sequencial (sem disputar
        # CPU entre modelos) e cada câmera limitada a LIVE_ANALYSIS_FPS
        while not self._stop.is_set():
            did_work = False
            for code in live_capture.codes():
                cam = self.cameras.get(code) or self.cameras.setdefault(code, CameraAnalysis(code))
                if time.time() - cam.last_run < self.interval:
                    continue
                stream = live_capture.get_stream(code)
                item = stream.latest_with_ts(max_age=3.0) if stream else None
                if not item or item[2] == cam.last_seq:
                    continue  # sem frame novo
                ts, frame, seq = item
                cam.last_seq, cam.last_run = seq, time.time()
                try:
                    self._analyze(cam, frame, ts, monitor_api)
                    did_work = True
                except Exception as e:
                    logger.warning(f"[análise {code}] erro: {e}")
            if not did_work:
                self._stop.wait(0.05)

    def _analyze(self, cam: CameraAnalysis, frame: np.ndarray, ts: float, monitor_api):
        t0 = time.time()
        r = cam.detector.detect(frame, camera_code=cam.code, track=True,
                                statue_track_ids=cam.statue_ids, draw=False)
        h, w = frame.shape[:2]
        zone_px = _zone_box(w, h, cam.code)
        surface_px = _frac_box(zone_service.get_statue(cam.code)["statue"], w, h)
        near = cam.update_tracks(r["objects"], ts, w, surface_px)

        if cam.name is None and monitor_api.camera_service:
            c = monitor_api.camera_service.get_camera_by_code(cam.code)
            cam.name = c.get("name", cam.code) if c else cam.code
        name = cam.name or cam.code

        # ─── Superfície protegida ────────────────────────────────────
        surface = None
        if surface_px:
            # Tudo que o YOLO achou na frente da superfície (menos a própria
            # estátua) é oclusão, não mudança
            occluders = [d["bbox"] for d in r["objects"] if not d.get("is_statue")
                         and d.get("track_id") not in cam.statue_ids]
            surface = cam.surface.update(frame, surface_px, occluders)

        # Permanência REAL por pessoa (substitui a aproximação por classe
        # do detector) — informativa, não notifica (ver alert_service)
        loitering = None
        if near and near[0]["seconds"] >= PERSON_LOITERING_ALERT_SECONDS:
            top = near[0]
            loitering = {
                "level": "MODERADO",
                "message": f"👥 Pessoa #{top['track_id']} junto ao monumento há {int(top['seconds'] // 60)} min",
                "dwell_seconds": top["seconds"],
            }

        monitor_api.record_risk_alert(cam.code, name, r["risk_alert"])
        monitor_api.record_interaction_alert(cam.code, name, r["interaction_alert"])
        monitor_api.record_loitering_alert(cam.code, name, loitering)

        annotated = r["annotated_image"]
        draw_overlay(annotated, r["objects"], zone_px, surface_px, surface,
                     r["risk_objects"], cam.last_event, ts)
        _, buf = cv2.imencode(".jpg", cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 80])
        jpg = buf.tobytes()

        surface_alert = self._surface_events(cam, name, ts, surface, jpg)

        objects = [{k: v for k, v in d.items()} for d in r["objects"]]
        with cam._lock:
            cam._times = [t for t in cam._times if time.time() - t <= 10] + [time.time()]
            cam.result_seq += 1
            cam.result = {
                "timestamp": ts,
                "camera_code": cam.code,
                "camera_name": name,
                "jpeg": jpg,
                "yolo_detection": {
                    "objects": objects,
                    "counts": r["counts"],
                    "total_objects": r["total_objects"],
                },
                "risk_alert": r["risk_alert"],
                "interaction_alert": r["interaction_alert"],
                "loitering_alert": loitering,
                "surface_alert": surface_alert,
                "surface_event": cam.last_event,
                "surface": {
                    "calibrated": surface_px is not None,
                    "change_frac": surface["change_frac"] if surface else None,
                    "clear_change_frac": surface.get("clear_change_frac") if surface else None,
                    "visible_frac": surface["visible_frac"] if surface else None,
                },
                "suspects": sorted(cam.recent_suspects),
                "people_near_statue": near,
                "processing_time_ms": round((time.time() - t0) * 1000, 1),
            }

    def _surface_events(self, cam: CameraAnalysis, name: str, ts: float,
                        surface: Optional[dict], jpg: bytes) -> Optional[dict]:
        """Mudança sustentada na superfície + suspeito → evento com evidências."""
        # Buffer do clipe: o suficiente pra cobrir PRE antes do início da mudança
        keep = EVIDENCE_PRE_SECONDS + SURFACE_UNATTRIBUTED_ABSORB_SECONDS + EVIDENCE_POST_SECONDS
        cam.evidence_buf.append((ts, jpg))
        while cam.evidence_buf and ts - cam.evidence_buf[0][0] > keep:
            cam.evidence_buf.popleft()

        # Evento confirmado aguardando o "depois": fecha e grava o clipe
        if cam.pending and ts >= cam.pending["finalize_at"]:
            p, cam.pending = cam.pending, None
            frames = [(t, j) for t, j in cam.evidence_buf if t >= p["clip_from"]]
            alert_id = p["alert_id"]

            def _done(meta, cam=cam, alert_id=alert_id):
                alert_service.update_evidence(alert_id, meta)
                cam.last_event = meta

            evidence_service.finish_event(p["meta"], jpg, frames, on_done=_done)
            cam.surface.absorb()  # a mudança já virou evento: passa a ser o novo normal

        if surface is None:
            return None

        # Só a mudança fora do halo de quem está na frente confirma: sombra,
        # mochila e perna de turista sentado ao lado ficam de fora
        clear_frac = surface.get("clear_change_frac", surface["change_frac"])
        changed = clear_frac >= SURFACE_CHANGE_MIN_FRAC
        if not changed:
            cam.change_since = None
            if surface["visible_frac"] >= BEFORE_MIN_VISIBLE and surface["change_frac"] == 0:
                cam.before_jpg = jpg
            return None

        if cam.change_since is None:
            cam.change_since = ts
        sustained = ts - cam.change_since
        suspects = sorted(cam.recent_suspects)
        if not suspects:
            if sustained >= SURFACE_UNATTRIBUTED_ABSORB_SECONDS:
                # Mudou sem ninguém suspeito junto (luz, objeto deixado, câmera
                # mexeu): vira fundo — não dispara quando alguém chegar depois
                logger.info(f"[análise {cam.code}] mudança na superfície sem suspeito — absorvida")
                cam.surface.absorb()
                cam.change_since = None
            return None
        if sustained < SURFACE_CHANGE_CONFIRM_SECONDS or cam.pending or ts < cam.cooldown_until:
            return None

        # ─── Confirma o evento ───────────────────────────────────────
        pct = round(clear_frac * 100, 1)
        ids = ", ".join(f"#{i}" for i in suspects)
        level = "CRÍTICO" if clear_frac >= SURFACE_CRITICAL_FRAC else "ALTO"
        alert = {
            "level": level,
            "message": (f"🎨 {level}: Possível pichação/alteração na superfície protegida ({pct}% alterado) "
                        f"com pessoa suspeita {ids} junto — requer validação humana"),
        }
        event_id = datetime.fromtimestamp(ts).strftime("%Y%m%d_%H%M%S")
        meta = evidence_service.start_event(cam.code, event_id, {
            "timestamp": ts,
            "camera_name": name,
            "change_started_at": cam.change_since,
            "change_percent": pct,
            "suspect_track_ids": suspects,
            "message": alert["message"],
        }, cam.before_jpg, jpg)  # durante = agora: suspeito + mudança no mesmo frame
        entry = alert_service.add_alert(cam.code, name, alert["level"], alert["message"], source="surface",
                                        objects=[f"pessoa {i}" for i in ids.split(", ")], evidence=meta)
        cam.pending = {"meta": meta, "alert_id": entry["id"], "finalize_at": ts + EVIDENCE_POST_SECONDS,
                       "clip_from": cam.change_since - EVIDENCE_PRE_SECONDS}
        cam.cooldown_until = ts + SURFACE_EVENT_COOLDOWN_SECONDS
        cam.last_event = meta
        logger.warning(f"[análise {cam.code}] 🎨 evento de superfície {event_id}: {pct}% alterado, suspeitos {ids}")
        return alert


# ─── Registro global ─────────────────────────────────────────────
_analyzer: Optional[LiveAnalyzer] = None


def start() -> None:
    global _analyzer
    if _analyzer or not live_capture.codes():
        return
    _analyzer = LiveAnalyzer(LIVE_ANALYSIS_FPS)
    _analyzer.start()
    logger.info(f"🧠 Análise contínua iniciada @ {LIVE_ANALYSIS_FPS} FPS por câmera")


def stop() -> None:
    if _analyzer:
        _analyzer.stop()


def latest_result(camera_code: str, max_age: float = 5.0) -> Optional[dict]:
    """Última análise da câmera (sem o JPEG), se recente."""
    cam = _analyzer.cameras.get(camera_code) if _analyzer else None
    if not cam:
        return None
    with cam._lock:
        r = cam.result
    if not r or time.time() - r["timestamp"] > max_age:
        return None
    return {k: v for k, v in r.items() if k != "jpeg"}


def latest_jpeg(camera_code: str, max_age: float = 10.0) -> Optional[bytes]:
    item = latest_jpeg_seq(camera_code, max_age)
    return item[1] if item else None


def latest_jpeg_seq(camera_code: str, max_age: float = 10.0) -> Optional[tuple[int, bytes]]:
    """(seq, jpeg) do último frame analisado — seq muda a cada análise nova."""
    cam = _analyzer.cameras.get(camera_code) if _analyzer else None
    if not cam:
        return None
    with cam._lock:
        r, seq = cam.result, cam.result_seq
    return (seq, r["jpeg"]) if r and time.time() - r["timestamp"] <= max_age else None


def status() -> list[dict]:
    if not _analyzer:
        return []
    out = []
    for code, cam in _analyzer.cameras.items():
        with cam._lock:
            r = cam.result
        out.append({
            "camera_code": code,
            "analysis_fps": cam.analysis_fps(),
            "last_analysis_age_s": round(time.time() - r["timestamp"], 1) if r else None,
            "processing_time_ms": r["processing_time_ms"] if r else None,
            "tracked_people": len(cam.tracks) - len(cam.statue_ids),
            "statue_track_ids": sorted(cam.statue_ids),
            "people_near_statue": r["people_near_statue"] if r else [],
            "suspects": r["suspects"] if r else [],
            "surface": r["surface"] if r else None,
        })
    return out
