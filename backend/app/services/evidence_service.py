"""
Evidências dos eventos de superfície (análise contínua).

Cada evento vira uma pasta em assets/evidence/{câmera}/{evento}/ com:
  antes.jpg   — último frame com a superfície desobstruída e sem mudança
  durante.jpg — frame da confirmação (mudança + pessoa suspeita junto)
  depois.jpg  — frame EVIDENCE_POST_SECONDS após a confirmação
  clip.webm   — trecho do vídeo anotado (de EVIDENCE_PRE_SECONDS antes do
                início da mudança até o "depois")
  meta.json   — dados do evento (lido de volta por list_events, então o
                histórico sobrevive a reinício do backend)

Servido pelo mount estático /assets (main.py). O clipe é gravado numa
thread à parte pra não travar a análise.
"""

import json
import logging
import threading
from typing import Optional

import cv2
import numpy as np

from app.config import ASSETS_DIR

logger = logging.getLogger(__name__)

EVIDENCE_DIR = ASSETS_DIR / "evidence"


def _url(camera_code: str, event_id: str, name: str) -> str:
    return f"/assets/evidence/{camera_code}/{event_id}/{name}"


def _write_meta(camera_code: str, event_id: str, meta: dict) -> None:
    with open(EVIDENCE_DIR / camera_code / event_id / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def start_event(camera_code: str, event_id: str, meta: dict,
                before_jpg: Optional[bytes], during_jpg: Optional[bytes]) -> dict:
    """Grava antes/durante na hora (o alerta sai já com eles); devolve o meta com as URLs."""
    folder = EVIDENCE_DIR / camera_code / event_id
    folder.mkdir(parents=True, exist_ok=True)
    images = {}
    for name, jpg in (("antes", before_jpg), ("durante", during_jpg)):
        if jpg:
            (folder / f"{name}.jpg").write_bytes(jpg)
            images[name] = _url(camera_code, event_id, f"{name}.jpg")
    meta = {**meta, "event_id": event_id, "camera_code": camera_code,
            "images": images, "clip": None, "complete": False}
    _write_meta(camera_code, event_id, meta)
    return meta


def _write_clip(path_base, frames: list[tuple[float, bytes]]) -> Optional[str]:
    """frames (ts, jpg) → WebM VP8 (toca no navegador); cai pra MP4 se o VP8 faltar."""
    imgs = [cv2.imdecode(np.frombuffer(j, np.uint8), cv2.IMREAD_COLOR) for _, j in frames]
    imgs = [i for i in imgs if i is not None]
    if len(imgs) < 2:
        return None
    span = frames[-1][0] - frames[0][0]
    fps = max(min((len(imgs) - 1) / span if span > 0 else 2.0, 30.0), 1.0)
    h, w = imgs[0].shape[:2]
    for ext, codec in ((".webm", "VP80"), (".mp4", "mp4v")):
        path = path_base.with_suffix(ext)
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*codec), fps, (w, h))
        if not writer.isOpened():
            continue
        for img in imgs:
            writer.write(img if img.shape[:2] == (h, w) else cv2.resize(img, (w, h)))
        writer.release()
        return path.name
    return None


def finish_event(meta: dict, after_jpg: Optional[bytes], frames: list[tuple[float, bytes]],
                 on_done=None) -> None:
    """Grava depois.jpg + clipe numa thread; chama on_done(meta) ao terminar."""
    def _run():
        code, event_id = meta["camera_code"], meta["event_id"]
        folder = EVIDENCE_DIR / code / event_id
        try:
            if after_jpg:
                (folder / "depois.jpg").write_bytes(after_jpg)
                meta["images"]["depois"] = _url(code, event_id, "depois.jpg")
            clip = _write_clip(folder / "clip", frames)
            meta["clip"] = _url(code, event_id, clip) if clip else None
            meta["clip_seconds"] = round(frames[-1][0] - frames[0][0], 1) if frames else 0
        except Exception as e:
            logger.warning(f"[evidência {event_id}] erro ao gravar: {e}")
        meta["complete"] = True
        _write_meta(code, event_id, meta)
        logger.info(f"🎞️ Evidências do evento {event_id} gravadas ({len(frames)} frames no clipe)")
        if on_done:
            on_done(meta)

    threading.Thread(target=_run, name=f"evidence-{meta['event_id']}", daemon=True).start()


def list_events(camera_code: Optional[str] = None, limit: int = 50) -> list[dict]:
    """Eventos gravados em disco, mais recentes primeiro."""
    if not EVIDENCE_DIR.exists():
        return []
    folders = [EVIDENCE_DIR / camera_code] if camera_code else [p for p in EVIDENCE_DIR.iterdir() if p.is_dir()]
    metas = []
    for cam in folders:
        if not cam.is_dir():
            continue
        for ev in cam.iterdir():
            try:
                with open(ev / "meta.json", encoding="utf-8") as f:
                    metas.append(json.load(f))
            except Exception:
                continue
    metas.sort(key=lambda m: m.get("timestamp", 0), reverse=True)
    return metas[:limit]
