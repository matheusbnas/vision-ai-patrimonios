"""
Captura CONTÍNUA de vídeo por câmera (fase 1 da cascata de análise).

Antes, cada captura abria um Chrome novo, negociava o WebRTC da Tixxi e
fechava — 5 a 60s por frame. Aqui UM Chrome headless fica aberto com uma
aba por câmera, cada aba lendo frames do <video> a LIVE_CAPTURE_FPS:

  - último frame + buffer circular dos últimos LIVE_CAPTURE_BUFFER_SECONDS
    (o buffer alimenta o modelo temporal da fase 4);
  - autorrecuperação: vídeo travado/tela de erro/KEY vencendo → recarrega
    SÓ aquela aba com stream_url nova (camera_service já troca a KEY);
    Chrome caiu → reabre tudo;
  - métricas (FPS real, reconexões, idade do último frame, RAM/CPU do
    Chrome) em status().

Um Chrome compartilhado (processo principal + GPU + rede uma vez só, um
renderer por aba) em vez de um Chrome por câmera: no protótipo com 1 Chrome
por câmera foram ~800 MB cada.

Playwright roda em modo assíncrono numa thread própria (o objeto Browser só
pode ser usado pela thread/loop que o criou). O resto do backend só lê os
frames já prontos (latest_frame/clip), protegidos por lock.

monitor.get_frame() usa o frame daqui quando ele está fresco; sem vídeo
contínuo para a câmera, cai na captura antiga, sem mudança.
"""

import asyncio
import base64
import logging
import threading
import time
from collections import deque
from typing import Optional

import cv2
import numpy as np

from app.config import (
    LIVE_CAPTURE_CODES,
    LIVE_CAPTURE_FPS,
    LIVE_CAPTURE_BUFFER_SECONDS,
)

logger = logging.getLogger(__name__)

# Recarrega a aba antes da KEY de stream (60min) vencer
PAGE_MAX_AGE_SECONDS = 50 * 60
# Sem frame novo (vídeo congelado) por este tempo → recarrega a aba
STALL_SECONDS = 20
# Tempo máximo esperando o primeiro frame decodificado após abrir a aba
FIRST_FRAME_TIMEOUT = 40
# Largura máxima do frame lido (as câmeras mandam 1920x1080; o YOLO
# trabalha em 640 — reduzir no navegador corta tempo de JPEG/transferência)
GRAB_MAX_WIDTH = 1280
# Marcador na linha de comando do Chrome (switch desconhecido é ignorado)
# pra achar o processo e medir RAM/CPU
_CHROME_MARKER = "--cor-live-capture"

# Desenha o <video> num canvas e devolve JPEG base64 (mais rápido que
# page.screenshot e sem o layout da página). Stream WebRTC não "suja" o
# canvas (não é cross-origin), então toDataURL funciona. Devolve null
# enquanto o vídeo não tem frame decodificado.
_GRAB_JS = """([q, maxW]) => {
    const v = document.querySelector("video");
    if (!v || !v.videoWidth || v.readyState < 2) return null;
    let c = window.__grabCanvas;
    if (!c) { c = window.__grabCanvas = document.createElement("canvas"); }
    const s = Math.min(1, maxW / v.videoWidth);
    c.width = Math.round(v.videoWidth * s); c.height = Math.round(v.videoHeight * s);
    c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
    return { data: c.toDataURL("image/jpeg", q), t: v.currentTime,
             w: v.videoWidth, h: v.videoHeight };
}"""


def _decode(data_url: str) -> Optional[np.ndarray]:
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1])
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB) if img is not None else None
    except Exception:
        return None


class CameraStream:
    """Estado de UMA câmera (uma aba no Chrome compartilhado)."""

    def __init__(self, camera_code: str, fps: float, buffer_seconds: float):
        self.code = camera_code
        self.interval = 1.0 / fps
        self.frames: deque = deque(maxlen=max(int(fps * buffer_seconds), 1))  # (ts, frame RGB)
        self._lock = threading.Lock()
        self.seq = 0  # incrementa a cada frame novo (consumidores detectam novidade)
        # métricas
        self.state = "iniciando"
        self.started_at = time.time()
        self.time_to_first_frame: Optional[float] = None
        self.frames_total = 0
        self.reconnects = 0
        self.last_error: Optional[str] = None
        self.source_resolution: Optional[str] = None
        self._fps_window: deque = deque(maxlen=50)

    def latest(self, max_age: float) -> Optional[np.ndarray]:
        item = self.latest_with_ts(max_age)
        return item[1] if item else None

    def latest_with_ts(self, max_age: float) -> Optional[tuple[float, np.ndarray, int]]:
        with self._lock:
            if not self.frames:
                return None
            ts, frame = self.frames[-1]
            seq = self.seq
        if time.time() - ts > max_age:
            return None
        return ts, frame.copy(), seq

    def clip(self) -> list[tuple[float, np.ndarray]]:
        """Cópia do buffer (ts, frame) — pro modelo temporal (fase 4)."""
        with self._lock:
            return list(self.frames)

    def push(self, frame: np.ndarray, ts: float):
        with self._lock:
            self.frames.append((ts, frame))
            self._fps_window.append(ts)
            self.frames_total += 1
            self.seq += 1

    def status(self) -> dict:
        with self._lock:
            last_ts = self.frames[-1][0] if self.frames else None
            window = list(self._fps_window)
        # FPS nos últimos ~10s (janela de 50 frames pode ser velha após queda)
        window = [t for t in window if time.time() - t <= 10]
        fps = (len(window) - 1) / (window[-1] - window[0]) if len(window) > 1 and window[-1] > window[0] else 0.0
        return {
            "camera_code": self.code,
            "state": self.state,
            "fps": round(fps, 2),
            "target_fps": round(1 / self.interval, 2),
            "last_frame_age_s": round(time.time() - last_ts, 1) if last_ts else None,
            "time_to_first_frame_s": round(self.time_to_first_frame, 1) if self.time_to_first_frame else None,
            "frames_total": self.frames_total,
            "buffer_frames": len(self.frames),
            "reconnects": self.reconnects,
            "uptime_s": round(time.time() - self.started_at),
            "source_resolution": self.source_resolution,
            "last_error": self.last_error,
        }


class LiveCaptureManager:
    """Uma thread + um loop asyncio + um Chrome; uma aba por câmera."""

    def __init__(self, codes: list[str], fps: float, buffer_seconds: float):
        self.streams = {c: CameraStream(c, fps, buffer_seconds) for c in codes}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._thread_main, name="live-capture", daemon=True)
        self._procs: dict = {}  # pid → psutil.Process (cpu_percent precisa do mesmo objeto)
        self.browser_restarts = 0

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    # ─── Loop ────────────────────────────────────────────────────
    def _thread_main(self):
        asyncio.run(self._main())

    async def _main(self):
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            while not self._stop.is_set():
                try:
                    await self._run_browser(p)
                except Exception as e:
                    logger.warning(f"[live] Chrome caiu: {e}")
                if self._stop.is_set():
                    break
                self.browser_restarts += 1
                for s in self.streams.values():
                    s.state = "reconectando"
                await asyncio.sleep(5)

    async def _run_browser(self, p):
        # Mesmas opções da captura antiga: Chrome de verdade (H.265 no
        # WebRTC) e sem --disable-gpu (decodificação por hardware).
        # As flags de background impedem o Chrome de estrangular timers/
        # renderização das abas que não estão "em foco" — com várias câmeras,
        # só uma aba seria a ativa e as outras cairiam pra ~0-1 FPS.
        args = ["--no-sandbox", "--disable-dev-shm-usage", "--mute-audio", _CHROME_MARKER,
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows"]
        try:
            browser = await p.chromium.launch(channel="chrome", headless=True, args=args)
        except Exception:
            browser = await p.chromium.launch(headless=True, args=args)
        try:
            tasks = [asyncio.create_task(self._camera_loop(browser, s)) for s in self.streams.values()]
            # Uma câmera nunca derruba as outras (cada loop trata os próprios
            # erros); só sai daqui se pedirem parada ou o Chrome morrer.
            while not self._stop.is_set() and browser.is_connected():
                await asyncio.sleep(1)
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            try:
                await browser.close()
            except Exception:
                pass

    async def _camera_loop(self, browser, stream: CameraStream):
        while not self._stop.is_set() and browser.is_connected():
            try:
                await self._session(browser, stream)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                stream.last_error = str(e)[:200]
                logger.warning(f"[live {stream.code}] aba caiu: {e}")
            if self._stop.is_set() or not browser.is_connected():
                return
            stream.reconnects += 1
            stream.state = "reconectando"
            await asyncio.sleep(5)

    async def _session(self, browser, stream: CameraStream):
        from app.api import monitor as monitor_api  # import tardio (evita ciclo)

        loop = asyncio.get_running_loop()
        svc = monitor_api.camera_service
        # get_camera_by_code pode fazer HTTP (renovar KEY) — fora do loop
        camera = await loop.run_in_executor(None, svc.get_camera_by_code, stream.code) if svc else None
        url = camera.get("stream_url") if camera else None
        if not url:
            stream.state = "sem stream_url"
            await asyncio.sleep(30)
            return

        # Contexto próprio por câmera: cookies/sessão WebRTC isolados
        context = await browser.new_context(viewport={"width": 800, "height": 600}, locale="pt-BR")
        try:
            page = await context.new_page()
            stream.state = "conectando"
            opened = time.time()
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await page.evaluate("""() => { const v = document.querySelector("video");
                                          if (v) { v.muted = true; v.play().catch(() => {}); } }""")

            last_new_frame = opened
            last_video_t = None
            while not self._stop.is_set():
                tick = time.time()
                if tick - opened > PAGE_MAX_AGE_SECONDS:
                    logger.info(f"[live {stream.code}] recarregando antes da KEY vencer")
                    return
                got = await page.evaluate(_GRAB_JS, [0.85, GRAB_MAX_WIDTH])
                # currentTime parado = vídeo congelado (mesmo frame)
                if got and got["t"] != last_video_t:
                    last_video_t = got["t"]
                    stream.source_resolution = f"{got['w']}x{got['h']}"
                    # decodificar JPEG é CPU — fora do loop asyncio
                    frame = await loop.run_in_executor(None, _decode, got["data"])
                    if frame is not None:
                        if monitor_api._is_stream_error_frame(frame):
                            stream.state = "tela de erro"
                        else:
                            last_new_frame = tick
                            stream.push(frame, tick)
                            if stream.time_to_first_frame is None:
                                stream.time_to_first_frame = tick - opened
                            if stream.state != "ao vivo":
                                stream.state = "ao vivo"
                                logger.info(f"[live {stream.code}] vídeo ao vivo ({tick - opened:.1f}s pra conectar)")
                waited = tick - last_new_frame
                limit = STALL_SECONDS if stream.state == "ao vivo" else FIRST_FRAME_TIMEOUT
                if waited > limit:
                    # Texto visível da página ajuda a diagnosticar (ex.: aviso
                    # de KEY/sessão, "Reconectando...", erro de codec)
                    try:
                        txt = " ".join((await page.inner_text("body")).split())[:120]
                    except Exception:
                        txt = ""
                    raise RuntimeError(f"sem frame novo há {int(waited)}s ({stream.state})"
                                       + (f" — página: {txt!r}" if txt else ""))
                await asyncio.sleep(max(stream.interval - (time.time() - tick), 0))
        finally:
            try:
                await context.close()
            except Exception:
                pass

    # ─── Consumo do Chrome (medição pra escalar) ─────────────────
    def chrome_usage(self) -> dict:
        try:
            import psutil
            root = None
            for proc in psutil.process_iter(["pid", "cmdline"]):
                cmd = proc.info.get("cmdline") or []
                # o principal não tem --type= (renderer/gpu/utility têm)
                if _CHROME_MARKER in cmd and not any(a.startswith("--type=") for a in cmd):
                    root = proc
                    break
            if root is None:
                return {"chrome_ram_mb": None, "chrome_cpu_pct": None, "chrome_processes": 0}
            alive = {pr.pid: pr for pr in [root] + root.children(recursive=True)}
            # Reaproveita os objetos: cpu_percent mede desde a chamada anterior
            self._procs = {pid: self._procs.get(pid, pr) for pid, pr in alive.items()}
            ram = sum(pr.memory_info().rss for pr in self._procs.values()) / 1e6
            # % de UM núcleo, somado entre processos (100 = 1 núcleo inteiro)
            cpu = sum(pr.cpu_percent(interval=None) for pr in self._procs.values())
            return {"chrome_ram_mb": round(ram), "chrome_cpu_pct": round(cpu, 1),
                    "chrome_processes": len(self._procs)}
        except Exception:
            return {"chrome_ram_mb": None, "chrome_cpu_pct": None, "chrome_processes": 0}


# ─── Registro global ─────────────────────────────────────────────
_manager: Optional[LiveCaptureManager] = None


def start() -> None:
    global _manager
    if _manager or not LIVE_CAPTURE_CODES:
        return
    _manager = LiveCaptureManager(LIVE_CAPTURE_CODES, LIVE_CAPTURE_FPS, LIVE_CAPTURE_BUFFER_SECONDS)
    _manager.start()
    logger.info(f"🎥 Captura contínua iniciada: {', '.join(LIVE_CAPTURE_CODES)} @ {LIVE_CAPTURE_FPS} FPS")


def stop() -> None:
    if _manager:
        _manager.stop()


def codes() -> list[str]:
    return list(_manager.streams) if _manager else []


def get_stream(camera_code: str) -> Optional[CameraStream]:
    return _manager.streams.get(camera_code) if _manager else None


def latest_frame(camera_code: str, max_age: float = 5.0) -> Optional[np.ndarray]:
    s = get_stream(camera_code)
    return s.latest(max_age) if s else None


def status() -> dict:
    if not _manager:
        return {"cameras": [], "chrome": None, "browser_restarts": 0}
    return {
        "cameras": [s.status() for s in _manager.streams.values()],
        "chrome": _manager.chrome_usage(),
        "browser_restarts": _manager.browser_restarts,
    }
