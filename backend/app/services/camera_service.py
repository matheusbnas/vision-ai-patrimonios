"""
Serviço de gerenciamento de câmeras
Comunicação com a API externa de câmeras do Rio de Janeiro
"""

import json
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
                            max_retries: int = 2, **kwargs) -> requests.Response:
        for attempt in range(max_retries + 1):
            try:
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

    def _load_cameras_cache(self) -> Optional[list[dict]]:
        try:
            if CAMERAS_CACHE_FILE.exists():
                with open(CAMERAS_CACHE_FILE) as f:
                    data = json.load(f)
                cached = data.get("cameras", [])
                cache_time = data.get("time", 0)
                if cached and (time.time() - cache_time) < 3600:  # 1h de cache
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
        # Tenta cache primeiro
        cached = self._load_cameras_cache()
        if cached:
            self._cameras_cache = cached
            return cached

        if not self._ensure_auth():
            return []

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
                self._save_cameras_cache(all_cameras)

        except Exception as e:
            logger.error(f"Erro ao buscar todas as câmeras: {e}")

        return all_cameras

    def get_camera_by_code(self, code: str) -> Optional[dict]:
        """Busca uma câmera específica pelo código"""
        cameras = self.get_all_cameras()
        for cam in cameras:
            # A API externa retorna "code", mas aceitamos vários nomes
            if any(
                cam.get(k) == code
                for k in ("code", "codigo", "camera_code")
            ):
                return cam
        return None

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
