"""
Cliente de API para o sistema de câmeras do Rio de Janeiro
Gerencia autenticação e requisições aos endpoints
"""

import os
import json
import math
import time
import random
import requests
from typing import Optional
import streamlit as st
from config import (
    API_BASE_URL, API_KEY, API_EMAIL, API_PASSWORD,
    STREAM_BASE_URL, STREAM_ENDPOINT, STREAM_KEY, CACHE_DIR,
)


CACHE_DIR.mkdir(parents=True, exist_ok=True)
TOKEN_FILE = CACHE_DIR / "jwt_token.json"
CAMERAS_CACHE_FILE = CACHE_DIR / "cameras_cache.json"


def _is_retryable(error: requests.exceptions.RequestException) -> bool:
    """Verifica se o erro é retryable (rate limit ou temporário)"""
    if hasattr(error, "response") and error.response is not None:
        return error.response.status_code in (429, 502, 503, 504)
    return isinstance(error, (requests.exceptions.ConnectionError,
                              requests.exceptions.Timeout))


class APIClient:
    """Cliente HTTP para comunicação com a API de câmeras"""

    def __init__(self):
        self.base_url = API_BASE_URL
        self.token: Optional[str] = None
        self.token_expires_at: float = 0
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self._cameras_cache: list[dict] | None = None
        self._cameras_cache_time: float = 0
        self._load_token()  # Tenta carregar token salvo

    def _save_token(self):
        """Salva token JWT em disco para reuso entre sessões"""
        try:
            data = {
                "token": self.token,
                "expires_at": self.token_expires_at,
            }
            TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(TOKEN_FILE, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    def _load_token(self):
        """Carrega token JWT salvo em disco"""
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
        except Exception:
            pass

    def _request_with_retry(
        self, method: str, url: str,
        max_retries: int = 2, **kwargs
    ) -> requests.Response:
        """
        Faz requisição com retry automático em caso de 429 (rate limit).
        Usa exponential backoff + jitter.
        """
        for attempt in range(max_retries + 1):
            try:
                resp = self.session.request(method, url, **kwargs)
                if resp.status_code == 429 and attempt < max_retries:
                    wait = (10 * (2 ** attempt)) + random.uniform(0, 3)
                    st.warning(
                        f"⏳ Rate limit! Tentativa {attempt + 1}/{max_retries}. "
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
        # Se chegou aqui, todas as tentativas falharam
        raise requests.exceptions.RequestException(
            "Máximo de tentativas excedido"
        )

    def authenticate(self) -> bool:
        """
        Autentica na API e armazena o token JWT.
        Inclui cooldown longo para evitar rate limit (429).

        Returns:
            bool: True se autenticado com sucesso
        """
        # Cooldown: se já tentou nos últimos 30s, recusa para não queimar rate limit
        now = time.time()
        since_last = now - getattr(self, '_last_auth_time', 0)
        if since_last < 30:
            wait = 30 - since_last
            st.warning(
                f"⏳ API em cooldown. Aguarde {wait:.0f}s antes de tentar novamente."
            )
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
                max_retries=1,  # só 1 retry para não queimar muitas requisições
            )
            data = resp.json()
            self._last_auth_time = time.time()

            if data.get("success") and data.get("access_token"):
                self.token = data["access_token"]
                self.token_expires_at = time.time() + data.get("expires_in", 3600) - 60
                self.session.headers.update(
                    {"Authorization": f"Bearer {self.token}"}
                )
                self._save_token()  # Salva em disco

                # A resposta de auth já inclui as câmeras — já salva no cache
                auth_cameras = data.get("cameras", [])
                if auth_cameras:
                    self._cameras_cache = auth_cameras
                    self._cameras_cache_time = time.time()
                    try:
                        with open(CAMERAS_CACHE_FILE, "w") as f:
                            json.dump({"cameras": auth_cameras, "time": time.time()}, f)
                    except Exception:
                        pass

                return True

            st.error(f"Falha na autenticação: {data}")
            return False

        except requests.exceptions.RequestException as e:
            self._last_auth_time = time.time()
            erro = str(e)
            if "429" in erro:
                st.error(
                    "🚫 **Limite de requisições excedido (429).** "
                    "A API bloqueou temporariamente. "
                    "Aguarde **1-2 minutos** e tente novamente."
                )
            else:
                st.error(f"Erro de conexão com a API: {e}")
            return False

    def _ensure_auth(self) -> bool:
        """Garante que o token ainda é válido"""
        if not self.token or time.time() >= self.token_expires_at:
            return self.authenticate()
        return True

    def get_cameras(self, page: int = 1, per_page: int = 100) -> dict:
        """
        Obtém lista de câmeras paginada

        Args:
            page: Número da página
            per_page: Itens por página

        Returns:
            dict: Resposta com câmeras
        """
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
        except requests.exceptions.RequestException as e:
            st.error(f"Erro ao buscar câmeras: {e}")
            return {"cameras": [], "total": 0, "success": False}

    def _load_disk_cache(self) -> list[dict] | None:
        """Carrega cache do disco, retornando câmeras ou None"""
        try:
            if CAMERAS_CACHE_FILE.exists():
                with open(CAMERAS_CACHE_FILE) as f:
                    data = json.load(f)
                cameras = data.get("cameras")
                if cameras:
                    self._cameras_cache = cameras
                    self._cameras_cache_time = data.get("time", 0)
                    return cameras
        except Exception:
            pass
        return None

    def get_all_cameras(self, force_refresh: bool = False) -> list[dict]:
        """
        Obtém câmeras. Tenta cache em disco primeiro,
        depois API (timeout 90s). Cache por 30 min.

        Args:
            force_refresh: Se True, ignora o cache

        Returns:
            list[dict]: Lista de câmeras
        """
        CACHE_TTL = 1800  # 30 minutos

        # Cache em memória
        cache_age = time.time() - self._cameras_cache_time
        if self._cameras_cache is not None and not force_refresh and cache_age < CACHE_TTL:
            return self._cameras_cache

        # Cache em disco (carrega p/ memória mesmo se expirado, como fallback)
        disk_cameras = self._load_disk_cache()
        if disk_cameras is not None and not force_refresh:
            age = time.time() - self._cameras_cache_time
            if age < CACHE_TTL:
                return disk_cameras

        if not self._ensure_auth():
            return disk_cameras or []

        st.info("⏳ Carregando câmeras da API (~30s)...")
        try:
            resp = self._request_with_retry(
                "GET",
                f"{self.base_url}/api/cameras",
                params={"page": 1, "per_page": 500},
                timeout=120,
                max_retries=2,
            )
            data = resp.json()
            cameras = data.get("cameras", []) or data.get("data", [])
            if not cameras:
                # Tentar com paginação menor
                resp = self._request_with_retry(
                    "GET",
                    f"{self.base_url}/api/cameras",
                    params={"page": 1, "per_page": 50},
                    timeout=120,
                    max_retries=1,
                )
                data = resp.json()
                cameras = data.get("cameras", []) or data.get("data", [])

            if cameras:
                self._cameras_cache = cameras
                self._cameras_cache_time = time.time()
                try:
                    with open(CAMERAS_CACHE_FILE, "w") as f:
                        json.dump({"cameras": cameras, "time": time.time()}, f)
                except Exception:
                    pass
                return cameras

            st.warning("API retornou lista vazia de câmeras.")
            return disk_cameras or []

        except requests.exceptions.RequestException as e:
            if disk_cameras:
                st.warning(f"⚠️ API indisponível. Usando cache de {len(disk_cameras)} câmeras.")
                return disk_cameras
            st.error(f"Erro ao buscar câmeras: {e}")
            return []

    def get_camera_detail(self, camera_id: int) -> Optional[dict]:
        """
        Obtém detalhes de uma câmera específica

        Args:
            camera_id: ID da câmera

        Returns:
            dict: Dados da câmera ou None
        """
        if not self._ensure_auth():
            return None

        try:
            resp = self.session.get(
                f"{self.base_url}/api/cameras/{camera_id}",
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException:
            return None

    def search_cameras(self, query: str) -> list[dict]:
        """
        Busca câmeras por nome, código ou endereço

        Args:
            query: Termo de busca

        Returns:
            list[dict]: Câmeras encontradas
        """
        if not self._ensure_auth():
            return []

        try:
            resp = self.session.get(
                f"{self.base_url}/api/cameras",
                params={"search": query},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("cameras", [])
        except requests.exceptions.RequestException:
            return []

    def get_nearby_cameras(
        self, lat: float, lon: float, radius_km: float = 1.0,
        cameras: list[dict] | None = None,
    ) -> list[dict]:
        """
        Encontra câmeras próximas a uma coordenada.
        Usa bounding box rápido antes do Haversine para performance.

        Args:
            lat: Latitude
            lon: Longitude
            radius_km: Raio de busca em km
            cameras: Lista de câmeras (opcional)

        Returns:
            list[dict]: Câmeras próximas ordenadas por distância
        """
        if cameras is None:
            cameras = self.get_all_cameras()

        # Bounding box aproximado para filtrar rápido
        # 1° lat ≈ 111km, 1° lon ≈ 111*cos(lat) km
        rad = radius_km / 111.0
        lon_rad = radius_km / (111.0 * abs(math.cos(math.radians(lat))) + 0.001)
        lat_min, lat_max = lat - rad, lat + rad
        lon_min, lon_max = lon - lon_rad, lon + lon_rad

        nearby = []
        for cam in cameras:
            clat, clon = cam.get("latitude"), cam.get("longitude")
            if not clat or not clon:
                continue
            # Filtro bounding box rápido
            if not (lat_min <= clat <= lat_max and lon_min <= clon <= lon_max):
                continue
            dist = self._haversine(lat, lon, clat, clon)
            if dist <= radius_km:
                nearby.append({**cam, "distance_km": round(dist, 3)})

        return sorted(nearby, key=lambda x: x["distance_km"])

    # ─── Stream / Vídeo ─────────────────────────────────────────

    @st.cache_resource(ttl=300)
    def _get_stream_key(_self) -> Optional[str]:
        """
        Obtém chave JWT para o servidor de stream.
        1. STREAM_KEY do .env (configuração manual)
        2. Gera token diretamente do servidor de stream via /api/auth/token

        Returns:
            str: Chave JWT ou None se não disponível
        """
        # 1. Chave manual do .env
        if STREAM_KEY:
            return STREAM_KEY

        # 2. Gerar token direto do servidor de stream
        try:
            resp = requests.post(
                f"{STREAM_BASE_URL}/api/auth/token",
                json={"key": "cor2024"},
                timeout=15,
            )
            if resp.ok:
                data = resp.json()
                token = data.get("token")
                if token:
                    return token
        except requests.exceptions.RequestException:
            pass

        return None

    def build_stream_url(self, camera_code: str, stream_key: str = None) -> Optional[str]:
        """
        Constrói URL de stream para uma câmera

        Args:
            camera_code: Código da câmera (ex: "000007")
            stream_key: Chave JWT do stream (opcional)

        Returns:
            str: URL completa do stream ou None
        """
        if not camera_code:
            return None
        if stream_key:
            return f"{STREAM_BASE_URL}{STREAM_ENDPOINT}?CODE={camera_code}&KEY={stream_key}"
        return None

    def get_stream_url_for_camera(self, camera: dict) -> Optional[str]:
        """
        Obtém URL de stream para uma câmera, tentando:
        1. stream_url do próprio objeto (se preenchido)
        2. Construção dinâmica via código + chave de stream

        Args:
            camera: Dados da câmera

        Returns:
            str: URL do stream ou None
        """
        # Tentar URL já existente
        if camera.get("stream_url"):
            return camera["stream_url"]

        # Tentar construir com código
        code = camera.get("code")
        if code:
            key = self._get_stream_key()
            if key:
                return self.build_stream_url(code, key)

        return None

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calcula distância entre dois pontos geográficos (fórmula de Haversine)"""
        R = 6371  # Raio da Terra em km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def get_camera_stats(self) -> dict:
        """Obtém estatísticas do sistema"""
        cameras = self.get_all_cameras()
        if not cameras:
            return {}

        total = len(cameras)
        unique_codes = len(set(c["code"] for c in cameras if c.get("code")))

        # Agrupar por nome de local (primeira parte antes do -)
        locations = {}
        for cam in cameras:
            name = cam.get("name", "")
            base_loc = name.split(" - ")[0].strip() if " - " in name else name.strip()
            if base_loc:
                locations[base_loc] = locations.get(base_loc, 0) + 1

        top_locations = sorted(locations.items(), key=lambda x: -x[1])[:20]

        return {
            "total_cameras": total,
            "unique_codes": unique_codes,
            "unique_locations": len(locations),
            "top_locations": top_locations,
        }
