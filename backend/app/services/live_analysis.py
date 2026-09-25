"""
Análise CONTÍNUA sobre o vídeo ao vivo (fase 2 da cascata).

Para cada câmera com captura contínua (live_capture), roda o YOLO com
rastreamento (ByteTrack) a LIVE_ANALYSIS_FPS sobre o frame mais recente:

  existe pessoa? → perto da estátua? → há quanto tempo ESTA pessoa (ID)?
      → pose (mão na área sensível / em cima) → alertas

Diferença pro monitoramento por prints: com ID por pessoa, a permanência
é real ("pessoa #12 encostada na estátua há 4 min"), não "sempre tem
alguém" — em monumento turístico isso era sempre verdade.

O resultado (frame anotado + detecções + alertas) fica em latest_result()
e é o que as rotas /live, /multi e o background_monitor usam para essas
câmeras, em vez de rodar a detecção de novo (evita estado de rastreamento
duplicado e alertas repetidos).
"""

import logging
import threading
import time
from typing import Optional

import cv2
import numpy as np

from app.config import (
    LIVE_ANALYSIS_FPS,
    PERSON_LOITERING_ALERT_SECONDS,
)
from app.models.detector import PatrimonyDetector
from app.services import live_capture

logger = logging.getLogger(__name__)

# ID que some por mais que isto é descartado (saiu de cena)
TRACK_FORGET_SECONDS = 10
# "Pessoa" sobre o contorno que não se move (centro desloca menos que
# STATIC_MAX_SHIFT da largura do frame) por STATIC_MIN_SECONDS = a estátua
STATIC_MIN_SECONDS = 15
STATIC_MAX_SHIFT = 0.02


class CameraAnalysis:
    def __init__(self, code: str):
        self.code = code
        # Um detector por câmera: o estado do ByteTrack fica no modelo
        self.detector = PatrimonyDetector()
        self.last_seq = -1
        self.last_run = 0.0
        # track_id → {"first": ts, "last": ts, "near_since": ts|None,
        #             "origin": (cx, cy), "max_shift": float}
        self.tracks: dict[int, dict] = {}
        # IDs reconhecidos como a própria estátua (parados sobre o contorno)
        self.statue_ids: set[int] = set()
        self.result: Optional[dict] = None
        self.name: Optional[str] = None
        self._lock = threading.Lock()
        self._times: list[float] = []  # ts das últimas análises (FPS real)

    def update_tracks(self, objects: list[dict], ts: float, frame_w: int) -> list[dict]:
        """Atualiza a permanência por ID; devolve as pessoas junto à estátua."""
        near_now = []
        for d in objects:
            tid = d.get("track_id")
            if d["class_name"] != "pessoa" or tid is None:
                continue
            x1, y1, x2, y2 = d["bbox"]
            center = ((x1 + x2) / 2, (y1 + y2) / 2)
            t = self.tracks.setdefault(tid, {"first": ts, "last": ts, "near_since": None,
                                             "origin": center, "max_shift": 0.0})
            t["last"] = ts
            shift = max(abs(center[0] - t["origin"][0]), abs(center[1] - t["origin"][1])) / max(frame_w, 1)
            t["max_shift"] = max(t["max_shift"], shift)
            # Estátua: parada sobre o contorno tempo suficiente
            if (tid not in self.statue_ids and (d["statue_overlap"] or 0) >= 0.8
                    and ts - t["first"] >= STATIC_MIN_SECONDS and t["max_shift"] < STATIC_MAX_SHIFT):
                self.statue_ids.add(tid)
                logger.info(f"[análise {self.code}] ID #{tid} reconhecido como a própria estátua (parado)")
            if d.get("is_statue") or tid in self.statue_ids:
                continue
            # Com contorno calibrado: encostada na estátua; sem: dentro da zona
            near = (d["statue_overlap"] or 0) >= 0.1 if d["statue_overlap"] is not None else d["in_zone"]
            if near:
                t["near_since"] = t["near_since"] or ts
                near_now.append({"track_id": tid, "seconds": round(ts - t["near_since"], 1)})
            else:
                t["near_since"] = None
        for tid in [k for k, v in self.tracks.items() if ts - v["last"] > TRACK_FORGET_SECONDS]:
            del self.tracks[tid]
            self.statue_ids.discard(tid)
        return sorted(near_now, key=lambda x: -x["seconds"])

    def analysis_fps(self) -> float:
        now = time.time()
        recent = [t for t in self._times if now - t <= 10]
        return round((len(recent) - 1) / (recent[-1] - recent[0]), 2) if len(recent) > 1 else 0.0


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
        r = cam.detector.detect(frame, camera_code=cam.code, track=True, statue_track_ids=cam.statue_ids)
        near = cam.update_tracks(r["objects"], ts, frame.shape[1])

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

        if cam.name is None and monitor_api.camera_service:
            c = monitor_api.camera_service.get_camera_by_code(cam.code)
            cam.name = c.get("name", cam.code) if c else cam.code
        name = cam.name or cam.code
        monitor_api.record_risk_alert(cam.code, name, r["risk_alert"])
        monitor_api.record_interaction_alert(cam.code, name, r["interaction_alert"])
        monitor_api.record_loitering_alert(cam.code, name, loitering)

        annotated = r["annotated_image"]
        _, jpg = cv2.imencode(".jpg", cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 80])
        objects = [{k: v for k, v in d.items()} for d in r["objects"]]
        with cam._lock:
            cam._times = [t for t in cam._times if time.time() - t <= 10] + [time.time()]
            cam.result = {
                "timestamp": ts,
                "camera_code": cam.code,
                "camera_name": name,
                "jpeg": jpg.tobytes(),
                "yolo_detection": {
                    "objects": objects,
                    "counts": r["counts"],
                    "total_objects": r["total_objects"],
                },
                "risk_alert": r["risk_alert"],
                "interaction_alert": r["interaction_alert"],
                "loitering_alert": loitering,
                "people_near_statue": near,
                "processing_time_ms": round((time.time() - t0) * 1000, 1),
            }


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
    cam = _analyzer.cameras.get(camera_code) if _analyzer else None
    if not cam:
        return None
    with cam._lock:
        r = cam.result
    return r["jpeg"] if r and time.time() - r["timestamp"] <= max_age else None


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
        })
    return out
