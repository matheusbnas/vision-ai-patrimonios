"""
Serviço de gerenciamento de câmeras
Comunicação com a API externa de câmeras do Rio de Janeiro
"""

import base64
import json
import re
import threading
import time
import random
import logging
from pathlib import Path
from typing import Optional

import requests

from app.config import (
    API_BASE_URL, API_KEY, API_EMAIL, API_PASSWORD,
    STREAM_BASE_URL, STREAM_ENDPOINT, STREAM_KEY, CACHE_DIR,
)

logger = logging.getLogger(__name__)

TOKEN_FILE = CACHE_DIR / "jwt_token.json"
CAMERAS_CACHE_FILE = CACHE_DIR / "cameras_cache.json"


def _jwt_exp(token: str) -> float:
    """Campo exp (unix) de um JWT, sem validar assinatura; 0 se ilegível."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0))
    except Exception:
        return 0.0


def _is_retryable(error: requests.exceptions.RequestException) -> bool:
    if hasattr(error, "response") and error.response is not None:
        return error.response.status_code in (429, 502, 503, 504)
    return isinstance(error, (requests.exceptions.ConnectionError,
                              requests.exceptions.Timeout))


class CameraService:
    """Serviço para comunicação com a API de câmeras"""

    def __init__(self):
        self.base_url = API_BASE_URL
        self.token: Optional[str] = None
        self.token_expires_at: float = 0
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self._cameras_cache: list[dict] | None = None
        self._cameras_cache_time: float = 0
        self._last_auth_time: float = 0
        # KEY de stream (JWT de ~60min, a mesma pra todas as câmeras) —
        # renovada via refresh_url/refreshToken, ver _fresh_stream_key
        self._stream_key: Optional[str] = None
        self._stream_key_exp: float = 0
        self._stream_key_lock = threading.Lock()
        self._last_key_relogin: float = 0
        self._load_token()

    # ─── Gerenciamento de Token ──────────────────────────────────

    def _save_token(self):
        try:
            data = {"token": self.token, "expires_at": self.token_expires_at}
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(TOKEN_FILE, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Erro ao salvar token: {e}")

    def _load_token(self):
        try:
            if TOKEN_FILE.exists():
                with open(TOKEN_FILE) as f:
                    data = json.load(f)
                if data.get("token") and time.time() < data.get("expires_at", 0):
                    self.token = data["token"]
                    self.token_expires_at = data["expires_at"]
                    self.session.headers.update(
                        {"Authorization": f"Bearer {self.token}"}
                    )
        except Exception as e:
            logger.warning(f"Erro ao carregar token: {e}")

    # ─── Requisições com Retry ───────────────────────────────────

    def _request_with_retry(self, method: str, url: str,
                            max_retries: int = 2, reauth: bool = True,
                            **kwargs) -> requests.Response:
        for attempt in range(max_retries + 1):
            try:
                resp = self.session.request(method, url, **kwargs)
                # Token rejeitado antes do expires_at previsto (revogado,
                # relógio diferente etc.) — faz login de novo e repete uma vez.
                if resp.status_code == 401 and reauth:
                    logger.warning("API de câmeras respondeu 401 — renovando token")
                    reauth = False
                    self._last_auth_time = 0  # ignora o cooldown nesse caso
                    if self.authenticate():
                        resp = self.session.request(method, url, **kwargs)
                if resp.status_code == 429 and attempt < max_retries:
                    wait = (10 * (2 ** attempt)) + random.uniform(0, 3)
                    logger.warning(
                        f"Rate limit! Tentativa {attempt + 1}/{max_retries}. "
                        f"Aguardando {wait:.0f}s..."
                    )
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                if attempt < max_retries and _is_retryable(e):
                    wait = (10 * (2 ** attempt)) + random.uniform(0, 3)
                    time.sleep(wait)
                    continue
                raise
        raise requests.exceptions.RequestException("Máximo de tentativas excedido")

    # ─── Autenticação ────────────────────────────────────────────

    def authenticate(self) -> bool:
        now = time.time()
        since_last = now - self._last_auth_time
        if since_last < 30:
            logger.warning(f"API em cooldown. Aguarde {30 - since_last:.0f}s.")
            return False

        try:
            payload = {
                "api_key": API_KEY,
                "email": API_EMAIL,
                "password": API_PASSWORD,
            }
            resp = self._request_with_retry(
                "POST",
                f"{self.base_url}/api/auth/login",
                json=payload,
                timeout=30,
                max_retries=1,
                reauth=False,
            )
            data = resp.json()
            self._last_auth_time = time.time()

            if data.get("success") and data.get("access_token"):
                self.token = data["access_token"]
                self.token_expires_at = time.time() + data.get("expires_in", 3600) - 60
                self.session.headers.update(
                    {"Authorization": f"Bearer {self.token}"}
                )
                self._save_token()

                auth_cameras = data.get("cameras", [])
                if auth_cameras:
                    self._cameras_cache = auth_cameras
                    self._cameras_cache_time = time.time()
                    self._save_cameras_cache(auth_cameras)

                return True

            logger.error(f"Falha na autenticação: {data}")
            return False

        except requests.exceptions.RequestException as e:
            self._last_auth_time = time.time()
            logger.error(f"Erro de conexão com a API: {e}")
            return False

    def _ensure_auth(self) -> bool:
        if not self.token or time.time() >= self.token_expires_at:
            return self.authenticate()
        return True

    # ─── Cache de Câmeras ────────────────────────────────────────

    def _save_cameras_cache(self, cameras: list[dict]):
        try:
            with open(CAMERAS_CACHE_FILE, "w") as f:
                json.dump({"cameras": cameras, "time": time.time()}, f)
        except Exception as e:
            logger.warning(f"Erro ao salvar cache: {e}")

    def _load_cameras_cache(self, allow_stale: bool = False) -> Optional[list[dict]]:
        try:
            if CAMERAS_CACHE_FILE.exists():
                with open(CAMERAS_CACHE_FILE) as f:
                    data = json.load(f)
                cached = data.get("cameras", [])
                cache_time = data.get("time", 0)
                # 1h de validade real do KEY de cada câmera, com margem de 5min —
                # sem essa margem, o cache "válido" por 1h expira no MESMO instante
                # que as KEYs de stream, e uma leitura na borda serve dados já
                # rejeitados pela Tixxi ("Acesso negado: Token expirado").
                if cached and (allow_stale or (time.time() - cache_time) < 3300):  # 55min
                    if not allow_stale:
                        self._cameras_cache_time = cache_time
                    return cached
        except Exception as e:
            logger.warning(f"Erro ao ler cache: {e}")
        return None

    # ─── Endpoints ───────────────────────────────────────────────

    def get_cameras(self, page: int = 1, per_page: int = 100) -> dict:
        """Obtém lista paginada de câmeras"""
        if not self._ensure_auth():
            return {"cameras": [], "total": 0, "success": False}

        try:
            resp = self._request_with_retry(
                "GET",
                f"{self.base_url}/api/cameras",
                params={"page": page, "per_page": per_page},
                timeout=30,
            )
            return resp.json()
        except Exception as e:
            logger.error(f"Erro ao buscar câmeras: {e}")
            return {"cameras": [], "total": 0, "success": False}

    def get_all_cameras(self) -> list[dict]:
        """Obtém todas as câmeras (com paginação automática)"""
        # Cache em memória primeiro — o arquivo tem ~6 MB e era relido do
        # disco a cada get_camera_by_code
        if self._cameras_cache and time.time() - self._cameras_cache_time < 3300:
            return self._cameras_cache
        cached = self._load_cameras_cache()
        if cached:
            self._cameras_cache = cached
            return cached

        if not self._ensure_auth():
            # Login falhou (API fora/cooldown): melhor o cadastro antigo do que
            # nenhuma câmera — as KEYs podem estar vencidas, mas a próxima
            # renovação bem-sucedida corrige.
            return self._load_cameras_cache(allow_stale=True) or []

        all_cameras = []
        page = 1
        per_page = 100

        try:
            while True:
                result = self.get_cameras(page, per_page)
                cameras = result.get("cameras", [])
                if not cameras:
                    break
                all_cameras.extend(cameras)
                total = result.get("total", 0)
                if len(all_cameras) >= total:
                    break
                page += 1

            if all_cameras:
                self._cameras_cache = all_cameras
                self._cameras_cache_time = time.time()
                self._save_cameras_cache(all_cameras)

        except Exception as e:
            logger.error(f"Erro ao buscar todas as câmeras: {e}")

        return all_cameras or self._load_cameras_cache(allow_stale=True) or []

    def refresh(self) -> bool:
        """Força login novo e recarrega o cadastro de câmeras (novas KEYs de stream).

        Usado pela renovação periódica (main.py) e quando uma captura recebe 401.
        """
        self._last_auth_time = 0
        self._stream_key_exp = 0  # força KEY de stream nova no próximo uso
        if not self.authenticate():
            return False
        # O login já devolve as câmeras; se não devolveu, busca paginado.
        if not self._load_cameras_cache():
            self.get_all_cameras()
        logger.info("🔑 Token e KEYs de stream das câmeras renovados")
        return True

    def get_camera_by_code(self, code: str) -> Optional[dict]:
        """Busca uma câmera específica pelo código (stream_url com KEY válida)"""
        cameras = self.get_all_cameras()
        for cam in cameras:
            # A API externa retorna "code", mas aceitamos vários nomes
            if any(
                cam.get(k) == code
                for k in ("code", "codigo", "camera_code")
            ):
                return self._with_fresh_key(cam)
        return None

    # ─── KEY de stream ───────────────────────────────────────────
    # O login da Tixxi devolve as câmeras com uma KEY gerada ~1h ANTES
    # (já vencida ou quase: "Acesso negado: Token expirado"), então só
    # refazer o login não resolve. Cada câmera traz refresh_token (~8h) e
    # refresh_url; POST {"refreshToken": ...} nesse endpoint devolve
    # {"token": <KEY nova, 60min>} — a mesma KEY vale pra todas as câmeras.

    def _fresh_stream_key(self, refresh_token: str, refresh_url: str) -> Optional[str]:
        with self._stream_key_lock:
            # Reaproveita até 5min antes de vencer
            if self._stream_key and time.time() < self._stream_key_exp - 300:
                return self._stream_key
            try:
                resp = requests.post(refresh_url, json={"refreshToken": refresh_token},
                                     timeout=10, verify=False)
                token = resp.json().get("token") if resp.status_code == 200 else None
            except Exception as e:
                logger.warning(f"Erro ao renovar KEY de stream: {e}")
                token = None
            if not token:
                logger.warning(f"Renovação da KEY de stream falhou (HTTP {getattr(resp, 'status_code', '?')})"
                               if 'resp' in locals() else "Renovação da KEY de stream falhou")
                return None
            self._stream_key = token
            self._stream_key_exp = _jwt_exp(token) or (time.time() + 3600)
            logger.info("🔑 KEY de stream renovada (válida por ~60min)")
            return token

    def _with_fresh_key(self, cam: dict) -> dict:
        """Cópia da câmera com a KEY da stream_url trocada por uma válida."""
        url = cam.get("stream_url") or ""
        if "KEY=" not in url or not cam.get("refresh_token") or not cam.get("refresh_url"):
            return cam
        key = self._fresh_stream_key(cam["refresh_token"], cam["refresh_url"])
        if not key and time.time() - self._last_key_relogin > 300:
            # refresh_token (~8h) provavelmente venceu: login novo traz um
            # cadastro com refresh_token atualizado — tenta uma vez a cada 5min
            self._last_key_relogin = time.time()
            logger.warning("Renovação da KEY falhou — refazendo login para obter refresh_token novo")
            if self.refresh():
                fresh = next((c for c in self.get_all_cameras() if c.get("code") == cam.get("code")), cam)
                if fresh.get("refresh_token"):
                    key = self._fresh_stream_key(fresh["refresh_token"], fresh.get("refresh_url") or cam["refresh_url"])
        if not key:
            return cam  # mantém a KEY do cadastro (pode estar vencida)
        return {**cam, "stream_url": re.sub(r"KEY=[^&]*", f"KEY={key}", url)}

    def _get_stream_key(self) -> Optional[str]:
        """Obtém chave de stream do servidor.
        Tenta API primeiro, fallback para STREAM_KEY do .env"""
        # Fallback: STREAM_KEY do .env (se configurado)
        if STREAM_KEY:
            return STREAM_KEY
        try:
            resp = self.session.get(
                f"{STREAM_BASE_URL}/api/stream/key",
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.text.strip()
        except Exception as e:
            logger.warning(f"Erro ao obter stream key: {e}")
        return None

    def get_stream_url(self, camera_code: str) -> Optional[str]:
        """Monta URL de stream para uma câmera (formato: /stream?CODE=xxx&KEY=xxx)"""
        key = self._get_stream_key()
        if key and camera_code:
            return f"{STREAM_BASE_URL}{STREAM_ENDPOINT}?CODE={camera_code}&KEY={key}"
        return None

    def check_health(self) -> dict:
        """Verifica saúde da conexão com a API"""
        try:
            resp = self.session.get(
                f"{self.base_url}/health",
                timeout=5,
            )
            return {"status": "online" if resp.status_code == 200 else "offline"}
        except Exception:
            return {"status": "offline", "error": "Conexão recusada"}
