"""
🏛️ Sistema de Visão Computacional - Patrimônios do Rio
CO-RIO - Coordenadoria de Operações e Resiliência

Dashboard interativo para monitoramento de câmeras
e detecção de patrimônios públicos via IA
"""

import io
import json
import time
import math
from pathlib import Path
from datetime import datetime

import requests as req_module

import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from PIL import Image
import plotly.express as px
import plotly.graph_objects as go

from config import (
    STREAMLIT_TITLE,
    STREAMLIT_ICON,
    DEFAULT_MAP_CENTER,
    DEFAULT_MAP_ZOOM,
    CONFIDENCE_THRESHOLD,
    PATRIMONY_CLASSES,
    INTEREST_CLASSES,
    PATRIMONIOS,
)
from api_client import APIClient
from detector import PatrimonyDetector
from vandalism_detector import VandalismDetector

# ─── Configuração da Página ─────────────────────────────────────
st.set_page_config(
    page_title=STREAMLIT_TITLE,
    page_icon=STREAMLIT_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Inicialização do Estado da Sessão ──────────────────────────
if "api_client" not in st.session_state:
    st.session_state.api_client = APIClient()
if "detector" not in st.session_state:
    st.session_state.detector = PatrimonyDetector()
if "vandalism_detector" not in st.session_state:
    st.session_state.vandalism_detector = VandalismDetector()
if "cameras" not in st.session_state:
    st.session_state.cameras = []
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "last_detection" not in st.session_state:
    st.session_state.last_detection = None
if "page" not in st.session_state:
    st.session_state.page = "patrimonios"
if "stream_key" not in st.session_state:
    st.session_state.stream_key = ""
if "_auto_init_done" not in st.session_state:
    st.session_state._auto_init_done = False


# ─── Auto-inicialização ─────────────────────────────────────────
def auto_init():
    """Tenta autenticar automaticamente usando token salvo ou API"""
    if st.session_state._auto_init_done or st.session_state.authenticated:
        return

    api = st.session_state.api_client

    # Se já tem token carregado do disco, considera autenticado
    if api.token:
        st.session_state.authenticated = True
        # O token da API de auth NÃO é o mesmo do servidor de stream
        # Busca a chave de stream separadamente
        stream_key = api._get_stream_key()
        if stream_key:
            st.session_state.stream_key = stream_key
        # Tenta carregar câmeras do cache em disco direto
        try:
            from api_client import CAMERAS_CACHE_FILE
            if CAMERAS_CACHE_FILE.exists():
                with open(CAMERAS_CACHE_FILE) as f:
                    _cache_data = json.load(f)
                _cached_cams = _cache_data.get("cameras", [])
                if _cached_cams:
                    st.session_state.cameras = _cached_cams
                    api._cameras_cache = _cached_cams
                    api._cameras_cache_time = _cache_data.get("time", 0)
        except Exception:
            pass
        st.session_state._auto_init_done = True
        return

    # Evita re-tentar se falhou recentemente
    if getattr(api, '_auth_failed_recently', False):
        since_last = time.time() - getattr(api, '_last_auth_time', 0)
        if since_last < 30:
            st.session_state._auto_init_done = True
            return

    with st.spinner("🔄 Conectando à API..."):
        ok = api.authenticate()
        if ok:
            st.session_state.authenticated = True
            st.session_state.stream_key = api.token or ""
            api._auth_failed_recently = False
        else:
            api._auth_failed_recently = True

    st.session_state._auto_init_done = True


def load_cameras_async():
    """Carrega câmeras automaticamente se autenticado e ainda não carregadas"""
    if st.session_state.cameras:
        return
    api = st.session_state.api_client
    if not st.session_state.authenticated:
        return

    # Tenta cache em disco primeiro (rápido, sem chamada de rede)
    try:
        from api_client import CAMERAS_CACHE_FILE
        if CAMERAS_CACHE_FILE.exists():
            with open(CAMERAS_CACHE_FILE) as f:
                data = json.load(f)
            cached = data.get("cameras", [])
            if cached:
                st.session_state.cameras = cached
                return
    except Exception:
        pass

    # Fallback: chamada à API
    cameras = api.get_all_cameras()
    if cameras:
        st.session_state.cameras = cameras


# ─── Sidebar ─────────────────────────────────────────────────────
def render_sidebar():
    """Renderiza a barra lateral com navegação e filtros"""
    with st.sidebar:
        st.markdown(
            f"# {STREAMLIT_ICON} Visão Patrimônios"
        )
        st.caption("CO-RIO | Monitoramento Inteligente")
        st.divider()

        # Navegação
        st.markdown("### Navegação")
        pages = {
            "dashboard": "📊 Dashboard",
            "patrimonios": "🏛️ Patrimônios",
            "mapa": "🗺️ Mapa de Câmeras",
            "detector": "🔍 Detector de Patrimônios",
            "vandalismo": "🚨 Monitor Antivandalismo",
            "analise": "📈 Análise por Região",
            "sobre": "ℹ️ Sobre",
        }

        for page_id, page_label in pages.items():
            if st.button(
                page_label,
                width='stretch',
                type="primary" if st.session_state.page == page_id else "secondary",
            ):
                st.session_state.page = page_id
                st.rerun()

        st.divider()

        # Status da API
        st.markdown("### 🔌 Status da Conexão")
        api = st.session_state.api_client

        if st.session_state.authenticated:
            cam_count = len(st.session_state.cameras)
            st.success(f"✅ API Conectada")
            if cam_count > 0:
                st.metric("📹 Câmeras Carregadas", f"{cam_count:,}".replace(",", "."))
                if st.button("🔄 Recarregar câmeras", width='stretch'):
                    st.session_state.cameras = []
                    st.session_state._pat_cache = None
                    st.rerun()
            else:
                if st.button("📥 Carregar Câmeras", width='stretch'):
                    with st.spinner("📥 Carregando..."):
                        cameras = api.get_all_cameras()
                        if cameras:
                            st.session_state.cameras = cameras
                            st.rerun()
        else:
            st.warning("⛔ API Desconectada")
            since_last = time.time() - getattr(api, '_last_auth_time', 0)
            if since_last < 15:
                restante = int(15 - since_last)
                st.error(f"🚫 Limite. Aguarde **{restante}s**...")
            else:
                if st.button("🔑 Conectar à API", width='stretch'):
                    with st.spinner("Autenticando..."):
                        if api.authenticate():
                            st.session_state.authenticated = True
                            st.session_state.stream_key = api.token or ""
                            st.rerun()

        # Filtros quando conectado
        if st.session_state.authenticated and st.session_state.cameras:
            st.divider()
            st.markdown("### 🎯 Filtros")

            # Filtro por nome/busca
            search = st.text_input(
                "Buscar câmera (nome/código):",
                placeholder="Ex: CRISTO, PÃO DE AÇÚCAR...",
            )

            if search:
                filtered = [
                    c
                    for c in st.session_state.cameras
                    if search.upper()
                    in f"{c.get('name', '')} {c.get('code', '')}".upper()
                ]
            else:
                filtered = st.session_state.cameras

            # Filtro por código
            codes = sorted(
                set(
                    c.get("code", "")
                    for c in filtered
                    if c.get("code")
                )
            )
            selected_code = st.selectbox(
                "Filtrar por código:",
                options=["Todos"] + codes,
            )

            if selected_code != "Todos":
                filtered = [c for c in filtered if c.get("code") == selected_code]

            st.metric("Câmeras visíveis", len(filtered))
            st.session_state.filtered_cameras = filtered

            # Info
            st.divider()
            st.caption(
                f"Total: {len(st.session_state.cameras)} câmeras | "
                f"{datetime.now().strftime('%d/%m/%Y %H:%M')}"
            )

        # Teste rápido de stream (sempre visível)
        st.divider()
        st.markdown("### 📡 Teste de Stream ao Vivo")
        st.caption("⚠️ Máx. 10 streams simultâneos. Desligue o player quando não usar.")

        # Input da chave JWT (dinâmica)
        sk = st.text_input(
            "Chave JWT do Stream:",
            value=st.session_state.stream_key,
            placeholder="eyJhbGciOiJIUzI1NiIs...",
            type="password",
            help="Preenchido automaticamente ao conectar na API",
        )
        if sk != st.session_state.stream_key:
            st.session_state.stream_key = sk
            st.rerun()

        # Sugerir códigos se tiver câmeras carregadas
        unique_codes_list = ["000012", "000014", "000001", "000007"]
        if st.session_state.authenticated and st.session_state.cameras:
            unique_codes_list = sorted(set(
                c["code"] for c in st.session_state.cameras if c.get("code")
            ))[:30]

        test_code = st.selectbox(
            "Código da câmera:",
            options=unique_codes_list,
            index=0,
        )

        # Toggle para ligar/desligar o player ao vivo
        stream_on = st.toggle(
            "📺 Ver Câmera ao Vivo",
            value=st.session_state.get("_stream_active", False),
            key="_stream_toggle",
        )

        if stream_on:
            st.session_state._stream_active = True
            _api = st.session_state.api_client
            # Usa a chave de stream (do servidor de stream, não da API de auth)
            key = st.session_state.stream_key or _api._get_stream_key()
            url = _api.build_stream_url(test_code, key)
            if url:
                st.markdown(
                    stream_player_html(url, height=400),
                    unsafe_allow_html=True,
                )
                st.caption(
                    "🔴 Stream ao vivo — a página React carrega automaticamente. "
                    "Desligue o player para liberar slot (limite 10)."
                )
            else:
                st.error("❌ Defina a chave JWT no campo acima para ver o stream.")
        else:
            st.session_state._stream_active = False


# ─── Utilitários de busca ───────────────────────────────────────

def find_cameras_by_monument_name(
    monument_name: str, cameras: list[dict] | None = None
) -> list[dict]:
    """
    Busca câmeras cujo nome contenha palavras-chave do monumento.
    Ex: 'Princesa Isabel' -> encontra 'MONUMENTO PRINCESA ISABEL'
    Prioriza câmeras com 'MONUMENTO' ou 'ESTATUA' no nome.
    """
    if cameras is None:
        cameras = st.session_state.cameras

    stopwords = {"de", "da", "do", "das", "dos", "e", "a", "o", "em", "no", "na"}
    keywords = [
        w for w in monument_name.upper().split()
        if w not in stopwords and len(w) > 2
    ]
    if not keywords:
        return []

    found = []
    seen = set()
    for cam in cameras:
        name = cam.get("name", "").upper()
        score = sum(1 for kw in keywords if kw in name)
        if score >= 1:
            # Penaliza se for nome de via/avenida (ex: AV. AYRTON SENNA em Barra)
            # em vez do monumento em Copacabana
            is_monument = "MONUMENTO" in name or "ESTATUA" in name
            is_avenida = name.startswith("AV. ") or name.startswith("AV ")
            bonus = 10 if is_monument else (-5 if is_avenida else 0)
            final_score = score + bonus

            key = (name, cam.get("latitude"), cam.get("longitude"))
            if key not in seen:
                seen.add(key)
                found.append({**cam, "monument_match_score": final_score})

    found.sort(key=lambda x: (-x["monument_match_score"], x.get("name", "")))
    return found


# ─── Páginas ─────────────────────────────────────────────────────

def page_patrimonios():
    """Página de monitoramento dos 10 patrimônios específicos do Rio"""
    st.markdown(f"# 🏛️ Patrimônios Monitorados")
    st.markdown("### 10 patrimônios históricos e culturais do Rio de Janeiro")

    api = st.session_state.api_client

    if not st.session_state.authenticated:
        st.warning("👈 Conecte-se à API na sidebar para ver as câmeras dos patrimônios.")
        # Mostrar só a lista mesmo sem conexão
        cols = st.columns(2)
        for i, p in enumerate(PATRIMONIOS):
            with cols[i % 2]:
                with st.container(border=True):
                    c1, c2 = st.columns([1, 3])
                    with c1:
                        st.markdown(f"# {p['emoji']}")
                    with c2:
                        st.markdown(f"**{p['nome']}**")
                        st.caption(p["descricao"])
                        st.caption(f"📍 {p['bairro']} | 🏷️ {p['categoria']}")
        return

    cam_count = len(st.session_state.cameras)
    if not cam_count:
        st.info("📥 Carregando câmeras, aguarde...")
        return

    # Calcular câmeras próximas (cache em session_state)
    if "_pat_cache" not in st.session_state or st.session_state.get("_last_cam_hash") != id(st.session_state.cameras):
        with st.spinner("🔍 Buscando câmeras próximas aos patrimônios..."):
            patrimonios_data = []
            for p in PATRIMONIOS:
                # 1. Tenta encontrar câmeras com nome do monumento (ex: "MONUMENTO PRINCESA ISABEL")
                monument_cameras = find_cameras_by_monument_name(
                    p["nome"], cameras=st.session_state.cameras,
                )

                # 2. Busca câmeras próximas num raio menor (150m)
                nearby_cameras = api.get_nearby_cameras(
                    p["latitude"], p["longitude"], radius_km=0.15,
                    cameras=st.session_state.cameras,
                )

                # 3. Se não achou nada em 150m, tenta 300m
                if not nearby_cameras and not monument_cameras:
                    nearby_cameras = api.get_nearby_cameras(
                        p["latitude"], p["longitude"], radius_km=0.3,
                        cameras=st.session_state.cameras,
                    )

                # Junta câmeras do monumento + próximas, sem duplicatas
                seen_codes = set()
                cameras_finais = []
                for cam in monument_cameras + nearby_cameras:
                    code = cam.get("code")
                    if code not in seen_codes:
                        seen_codes.add(code)
                        # Só marca como câmera do monumento se tiver MONUMENTO/ESTÁTUA no nome
                        name = cam.get("name", "").upper()
                        is_monument = "MONUMENTO" in name or "ESTATUA" in name
                        cam["is_monument_camera"] = is_monument
                        cameras_finais.append(cam)

                # Ordena: câmeras verdadeiramente do monumento primeiro,
                # depois por distância (mais perto primeiro)
                cameras_finais.sort(key=lambda x: (
                    not x.get("is_monument_camera", False),
                    x.get("distance_km", 999),
                ))

                patrimonios_data.append({
                    "patrimonio": p,
                    "cameras": cameras_finais,
                    "total": len(cameras_finais),
                    "has_monument_camera": any(c.get("is_monument_camera") for c in cameras_finais),
                })
            st.session_state._pat_cache = patrimonios_data
            st.session_state._last_cam_hash = id(st.session_state.cameras)

    patrimonios_data = st.session_state._pat_cache

    total_com_cobertura = sum(1 for pd_ in patrimonios_data if pd_["total"] > 0)
    total_cameras_pat = sum(pd_["total"] for pd_ in patrimonios_data)

    # KPIs
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🏛️ Patrimônios", len(PATRIMONIOS))
    k2.metric("📹 Com Cobertura", f"{total_com_cobertura}/{len(PATRIMONIOS)}")
    k3.metric("📍 Câmeras Próximas", total_cameras_pat)
    k4.metric("📡 Total no Sistema", f"{cam_count:,}".replace(",", "."))

    st.divider()
    st.markdown("### 🎥 Câmeras ao Vivo por Patrimônio")

    # Botão para ligar/desligar todas
    ver_todas = st.toggle(
        "🔴 VER TODAS AS CÂMERAS AO VIVO",
        key="ver_todas_pat",
        help="Ativa o player de todas os patrimônios com câmera disponível",
    )

    # Grid de cards com players
    cols = st.columns(2)
    for i, pd_ in enumerate(patrimonios_data):
        p = pd_["patrimonio"]
        cameras_proximas = pd_["cameras"]
        with cols[i % 2]:
            with st.container(border=True):
                # Cabeçalho do patrimônio
                c1, c2 = st.columns([1, 3])
                with c1:
                    st.markdown(f"# {p['emoji']}")
                with c2:
                    st.markdown(f"**{p['nome']}**")
                    st.caption(p["descricao"])
                    st.caption(f"📍 {p['bairro']} | 🏷️ {p['categoria']}")

                if not cameras_proximas:
                    st.info("🔍 Nenhuma câmera próxima encontrada")
                    continue

                has_monument = pd_.get("has_monument_camera", False)
                if has_monument:
                    st.success(f"📹 Câmera do monumento encontrada! +{len(cameras_proximas)-1} próxima(s)")
                else:
                    closest = cameras_proximas[0].get("distance_km", 999) * 1000
                    st.info(f"📹 {len(cameras_proximas)} câmera(s) — mais próxima a {closest:.0f}m")

                # Seletor de câmera (se houver mais de 1)
                if len(cameras_proximas) > 1:
                    cam_options = {}
                    for c in cameras_proximas[:5]:
                        prefix = "🟢 " if c.get("is_monument_camera") else ""
                        dist = c.get("distance_km", 0) * 1000
                        label = f"{prefix}{c['name']} (cód. {c['code']}) — {dist:.0f}m"
                        cam_options[label] = c
                    selected_label = st.selectbox(
                        "Escolher câmera:",
                        options=list(cam_options.keys()),
                        key=f"cam_sel_{i}",
                        label_visibility="collapsed",
                    )
                    cam_top = cam_options[selected_label]
                else:
                    cam_top = cameras_proximas[0]

                # Tenta usar stream_url próprio da câmera (vem preenchido na auth),
                # ou constrói dinamicamente com a chave do servidor de stream
                code = cam_top.get("code", "???")
                stream_url = api.get_stream_url_for_camera(cam_top)
                if not stream_url:
                    key = st.session_state.stream_key or api._get_stream_key()
                    stream_url = api.build_stream_url(code, key)

                if not stream_url:
                    st.info(f"📡 Câmera `{code}` — sem URL de stream")
                    continue

                # Player ao vivo (toggle individual ou força do "ver todas")
                toggle_key = f"live_pat_{i}"
                show = ver_todas or st.toggle(
                    f"📺 {cam_top['name']} (cód. {code})",
                    key=toggle_key,
                )

                if show:
                    st.markdown(
                        stream_player_html(stream_url, height=350),
                        unsafe_allow_html=True,
                    )
                    badge = "🟢 Câmera do monumento" if cam_top.get("is_monument_camera") else "📷 Câmera da via"
                    st.caption(
                        f"🔴 {cam_top['name']} | "
                        f"{badge} | "
                        f"{cam_top.get('distance_km',0)*1000:.0f}m do patrimônio. "
                        "Desligue o player para liberar slot (limite 10)."
                    )

    st.divider()

    # Mapa com todos os patrimônios e câmeras
    st.markdown("### 🗺️ Localização dos Patrimônios")

    m = folium.Map(
        location=[DEFAULT_MAP_CENTER["lat"], DEFAULT_MAP_CENTER["lon"]],
        zoom_start=12,
        control_scale=True,
    )

    for i, p in enumerate(PATRIMONIOS):
        popup_html = f"""
        <div style="font-family: sans-serif; min-width: 220px;">
            <h3>{p['emoji']} {p['nome']}</h3>
            <p><b>{p['descricao']}</b></p>
            <p>📍 {p['bairro']}<br>🏷️ {p['categoria']}</p>
        </div>
        """
        folium.Marker(
            location=[p["latitude"], p["longitude"]],
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(color="red", icon="star", prefix="fa"),
            tooltip=p["nome"],
        ).add_to(m)

        # Adicionar câmeras próximas no mapa (reusa cache já calculado)
        if st.session_state.authenticated and "_pat_cache" in st.session_state:
            pd_item = st.session_state._pat_cache[i]
            for cam in pd_item["cameras"]:
                if cam.get("distance_km", 999) <= 0.3:
                    folium.CircleMarker(
                        location=[cam["latitude"], cam["longitude"]],
                        radius=4,
                        color="blue",
                        fill=True,
                        popup=cam["name"],
                        tooltip=f"📷 {cam['name']} ({cam.get('distance_km',0)*1000:.0f}m)",
                    ).add_to(m)

    st_folium(m, width=None, height=500)

    # Tabela resumo
    st.divider()
    st.markdown("### 📋 Resumo dos Patrimônios")
    df = pd.DataFrame(PATRIMONIOS)
    df_display = df[["nome", "bairro", "categoria", "descricao"]].copy()
    df_display.columns = ["Patrimônio", "Bairro", "Categoria", "Descrição"]
    st.dataframe(df_display, width='stretch', hide_index=True)


def page_dashboard():
    """Página principal com visão geral do sistema"""
    st.markdown(f"# {STREAMLIT_ICON} Dashboard de Monitoramento")
    st.markdown("### Visão Geral do Sistema de Câmeras - Patrimônios do Rio")

    if not st.session_state.authenticated:
        st.info(
            "👈 Conecte-se à API usando o menu lateral para começar."
        )
        return

    cameras = st.session_state.cameras
    if not cameras:
        st.info(
            "📥 Após conectar, clique em 'Carregar Câmeras' no menu lateral "
            "para carregar os dados."
        )
        return

    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "📹 Total de Câmeras",
            f"{len(cameras):,}".replace(",", "."),
        )
    with col2:
        unique_codes = len(set(c.get("code", "") for c in cameras if c.get("code")))
        st.metric(
            "📍 Locais Únicos",
            f"{unique_codes:,}".replace(",", "."),
        )
    with col3:
        st.metric(
            "🧠 Modelo de IA",
            "YOLOv11",
            "Ativo" if st.session_state.detector.ensure_model() else "Não carregado",
        )
    with col4:
        with_strean = sum(
            1 for c in cameras if c.get("stream_url")
        )
        st.metric(
            "🔴 Streams Ativos",
            with_strean,
        )

    st.divider()

    # Mapa rápido com amostra
    st.markdown("### 🗺️ Mapa de Calor - Cobertura das Câmeras")
    sample = cameras[::50]  # Amostra a cada 50 para performance
    m = folium.Map(
        location=[DEFAULT_MAP_CENTER["lat"], DEFAULT_MAP_CENTER["lon"]],
        zoom_start=DEFAULT_MAP_ZOOM,
        control_scale=True,
    )

    # Heatmap simplificado com marcadores
    from folium.plugins import HeatMap

    heat_data = [
        [c["latitude"], c["longitude"]]
        for c in sample
        if c.get("latitude") and c.get("longitude")
    ]
    if heat_data:
        HeatMap(heat_data, radius=15, blur=20, max_zoom=13).add_to(m)

    st_folium(m, width=None, height=500)

    # Tabela com estatísticas
    st.divider()
    st.markdown("### 📊 Top Localidades com Mais Câmeras")

    # Contar câmeras por local
    loc_counts = {}
    for c in cameras:
        name = c.get("name", "")
        base = name.split(" - FIXA")[0].strip() if " - FIXA" in name else name.split(" - ")[0].strip() if " - " in name else name
        if base:
            loc_counts[base] = loc_counts.get(base, 0) + 1

    top_df = pd.DataFrame(
        sorted(loc_counts.items(), key=lambda x: -x[1])[:30],
        columns=["Localidade", "Qtd. Câmeras"],
    )
    top_df.index = range(1, len(top_df) + 1)

    fig = px.bar(
        top_df.head(15),
        x="Qtd. Câmeras",
        y="Localidade",
        orientation="h",
        title="Top 15 Localidades com Mais Cobertura",
        color="Qtd. Câmeras",
        color_continuous_scale="Viridis",
    )
    fig.update_layout(height=500, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, width='stretch')


def page_map():
    """Página de mapa interativo com todas as câmeras"""
    st.markdown(f"# 🗺️ Mapa Interativo de Câmeras")
    st.markdown("### Visualize todas as câmeras do sistema")

    if not st.session_state.authenticated:
        st.info("👈 Conecte-se à API para visualizar o mapa.")
        return

    cameras = st.session_state.get("filtered_cameras", st.session_state.cameras)
    if not cameras:
        st.info(
            "📥 Após conectar, clique em 'Carregar Câmeras' no menu lateral "
            "para carregar os dados das câmeras."
        )
        return

    # Usar amostra se非常多 (>2000)
    max_markers = 2000
    if len(cameras) > max_markers:
        display = cameras[:: len(cameras) // max_markers + 1]
        st.caption(
            f"Mostrando {len(display)} de {len(cameras)} câmeras "
            f"(amostra para performance)"
        )
    else:
        display = cameras

    m = folium.Map(
        location=[DEFAULT_MAP_CENTER["lat"], DEFAULT_MAP_CENTER["lon"]],
        zoom_start=DEFAULT_MAP_ZOOM,
        control_scale=True,
    )

    # Agrupar marker clusters
    from folium.plugins import MarkerCluster

    marker_cluster = MarkerCluster().add_to(m)

    for cam in display:
        lat, lon = cam.get("latitude"), cam.get("longitude")
        if lat and lon:
            name = cam.get("name", "Sem nome")
            code = cam.get("code", "")
            cid = cam.get("id", "")

            popup_html = f"""
            <div style="font-family: sans-serif; min-width: 200px;">
                <b>{name}</b><br>
                <b>Código:</b> {code}<br>
                <b>ID:</b> {cid}<br>
                <b>Lat:</b> {lat:.6f}<br>
                <b>Lon:</b> {lon:.6f}
            </div>
            """

            folium.Marker(
                location=[lat, lon],
                popup=folium.Popup(popup_html, max_width=300),
                icon=folium.Icon(
                    color="blue",
                    icon="camera",
                    prefix="fa",
                ),
                tooltip=name,
            ).add_to(marker_cluster)

    # Escolha de tiles
    tile_style = st.selectbox(
        "Estilo do mapa:",
        ["OpenStreetMap", "CartoDB positron", "CartoDB dark_matter"],
        index=0,
    )

    # Recriar com tile escolhido
    m = folium.Map(
        location=[DEFAULT_MAP_CENTER["lat"], DEFAULT_MAP_CENTER["lon"]],
        zoom_start=DEFAULT_MAP_ZOOM,
        control_scale=True,
        tiles=tile_style,
    )

    marker_cluster = MarkerCluster().add_to(m)
    for cam in display:
        lat, lon = cam.get("latitude"), cam.get("longitude")
        if lat and lon:
            name = cam.get("name", "Sem nome")
            code = cam.get("code", "")
            cid = cam.get("id", "")
            popup_html = f"""
            <div style="font-family: sans-serif; min-width: 200px;">
                <b>{name}</b><br>
                <b>Código:</b> {code}<br>
                <b>ID:</b> {cid}<br>
                <b>Lat:</b> {lat:.6f}<br>
                <b>Lon:</b> {lon:.6f}
            </div>
            """
            folium.Marker(
                location=[lat, lon],
                popup=folium.Popup(popup_html, max_width=300),
                icon=folium.Icon(color="blue", icon="camera", prefix="fa"),
                tooltip=name,
            ).add_to(marker_cluster)

    st_folium(m, width=None, height=650)

    # Dados em tabela
    with st.expander("📋 Ver dados em tabela"):
        df = pd.DataFrame(cameras)
        if not df.empty:
            cols = ["id", "code", "name", "latitude", "longitude"]
            cols = [c for c in cols if c in df.columns]
            st.dataframe(df[cols], width='stretch', hide_index=True)


def page_detector():
    """Página de detecção de patrimônios por IA"""
    st.markdown(f"# 🔍 Detector Inteligente de Patrimônios")
    st.markdown(
        "Faça upload de imagens ou use a webcam para detectar "
        "patrimônios públicos automaticamente com IA."
    )

    detector = st.session_state.detector

    # Verificar modelo
    with st.spinner("Carregando modelo de IA..."):
        model_ok = detector.ensure_model()

    if not model_ok:
        st.error(
            "Não foi possível carregar o modelo YOLO. "
            "Verifique se o ultralytics está instalado corretamente."
        )
        st.info(
            "💡 Dica: Execute `pip install ultralytics` "
            "para instalar o YOLO."
        )
        return

    st.success("✅ Modelo YOLO carregado com sucesso!")

    # Seletor de confiança
    confidence = st.slider(
        "Threshold de Confiança (%)",
        min_value=10,
        max_value=95,
        value=int(CONFIDENCE_THRESHOLD * 100),
        help="Quanto maior, mais preciso mas menos detecções",
    ) / 100

    # Abas para diferentes fontes de imagem
    tab1, tab2, tab3 = st.tabs(
        ["📤 Upload de Imagem", "📷 Webcam", "🎯 Simular Detecção"]
    )

    with tab1:
        uploaded_file = st.file_uploader(
            "Escolha uma imagem",
            type=["jpg", "jpeg", "png", "webp"],
            help="Faça upload de uma foto de patrimônio público",
        )

        if uploaded_file is not None:
            col1, col2 = st.columns(2)

            with col1:
                image = Image.open(uploaded_file)
                st.image(image, caption="Imagem Original", width='stretch')

            with col2:
                with st.spinner("🔍 Analisando imagem..."):
                    uploaded_file.seek(0)
                    result = detector.detect_from_upload(
                        uploaded_file, confidence
                    )

                if result.get("annotated_image") is not None:
                    st.image(
                        result["annotated_image"],
                        caption="Imagem com Detecções",
                        width='stretch',
                    )

                st.session_state.last_detection = result

    with tab2:
        st.info(
            "📷 Use sua webcam para capturar uma imagem ao vivo. "
            "Clique em 'Capturar' para tirar uma foto."
        )
        camera_image = st.camera_input("Tirar foto", key="webcam_detector")

        if camera_image is not None:
            col1, col2 = st.columns(2)

            with col1:
                st.image(
                    camera_image,
                    caption="Foto Capturada",
                    width='stretch',
                )

            with col2:
                with st.spinner("🔍 Analisando imagem..."):
                    result = detector.detect_from_upload(
                        camera_image, confidence
                    )

                if result.get("annotated_image") is not None:
                    st.image(
                        result["annotated_image"],
                        caption="Imagem com Detecções",
                        width='stretch',
                    )

                st.session_state.last_detection = result

    with tab3:
        st.markdown("### Simular Detecção com imagem de teste")
        st.info(
            "Use uma imagem de exemplo para testar o detector. "
            "Você pode fazer upload de qualquer imagem nas abas acima."
        )

        # Criar imagem de exemplo com shapes para demonstração
        test_img = np.ones((480, 640, 3), dtype=np.uint8) * 240
        test_img = cv2_put_text(test_img, "Upload uma imagem", (120, 240))

        st.image(test_img, caption="Imagem de teste", width='stretch')
        st.caption(
            "💡 Faça upload de uma imagem real nas abas 'Upload de Imagem' "
            "ou 'Webcam' para detecção real."
        )

    # Mostrar resultados
    if st.session_state.last_detection is not None:
        result = st.session_state.last_detection

        if result.get("error"):
            st.error(result["error"])
        else:
            st.divider()
            st.markdown("## 📊 Resultados da Detecção")

            col1, col2 = st.columns([1, 2])

            with col1:
                st.metric("Total de Objetos", result.get("total_objects", 0))

            with col2:
                if result.get("counts"):
                    counts_df = pd.DataFrame(
                        [
                            {
                                "Tipo": k,
                                "Categoria": INTEREST_CLASSES.get(k, "Outro"),
                                "Quantidade": v,
                            }
                            for k, v in result["counts"].items()
                        ]
                    )
                    if not counts_df.empty:
                        fig = px.pie(
                            counts_df,
                            values="Quantidade",
                            names="Tipo",
                            title="Distribuição por Tipo de Patrimônio",
                        )
                        st.plotly_chart(fig, width='stretch')

            with st.expander("📋 Relatório Detalhado"):
                report = detector.generate_report(result)
                st.markdown(report)

            with st.expander("📄 Dados Brutos (JSON)"):
                st.json(result)


def page_analysis():
    """Página de análise por região"""
    st.markdown(f"# 📈 Análise por Região")
    st.markdown("### Distribuição geográfica das câmeras e patrimônios")

    if not st.session_state.authenticated:
        st.info("👈 Conecte-se à API para visualizar as análises.")
        return

    cameras = st.session_state.cameras
    if not cameras:
        st.info(
            "📥 Após conectar, clique em 'Carregar Câmeras' no menu lateral "
            "para carregar os dados."
        )
        return

    df = pd.DataFrame(cameras)

    # Grid de análise
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 📊 Distribuição por Faixa de Latitude")
        if "latitude" in df.columns:
            fig = px.histogram(
                df,
                x="latitude",
                nbins=30,
                title="Concentração de Câmeras por Latitude",
                color_discrete_sequence=["#1f77b4"],
            )
            fig.update_layout(height=350)
            st.plotly_chart(fig, width='stretch')

    with col2:
        st.markdown("#### 📊 Distribuição por Faixa de Longitude")
        if "longitude" in df.columns:
            fig = px.histogram(
                df,
                x="longitude",
                nbins=30,
                title="Concentração de Câmeras por Longitude",
                color_discrete_sequence=["#ff7f0e"],
            )
            fig.update_layout(height=350)
            st.plotly_chart(fig, width='stretch')

    st.divider()

    # Análise por bairro/região
    st.markdown("#### 🌆 Densidade de Câmeras por Região")
    st.info(
        "Mapa de calor 2D mostrando a densidade de câmeras na cidade."
    )

    if "latitude" in df.columns and "longitude" in df.columns:
        fig = px.density_mapbox(
            df.sample(min(5000, len(df))),
            lat="latitude",
            lon="longitude",
            radius=15,
            center=dict(
                lat=DEFAULT_MAP_CENTER["lat"],
                lon=DEFAULT_MAP_CENTER["lon"],
            ),
            zoom=10,
            mapbox_style="stamen-terrain",
            title="Mapa de Densidade - Cobertura de Câmeras",
            opacity=0.7,
        )
        fig.update_layout(height=600)
        st.plotly_chart(fig, width='stretch')

    # Tabela de locais
    st.divider()
    st.markdown("#### 🏙️ Localidades Monitoradas")

    loc_data = []
    for c in cameras:
        name = c.get("name", "")
        base = name.split(" - FIXA")[0].strip() if " - FIXA" in name else name
        loc_data.append(base)

    loc_series = pd.Series(loc_data)
    loc_df = (
        loc_series.value_counts()
        .head(50)
        .reset_index()
    )
    loc_df.columns = ["Localidade", "Câmeras"]

    fig = px.bar(
        loc_df.head(20),
        x="Câmeras",
        y="Localidade",
        orientation="h",
        title="Top 20 Localidades Monitoradas",
        color="Câmeras",
        color_continuous_scale="Blues",
    )
    fig.update_layout(height=600, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, width='stretch')

    st.dataframe(
        loc_df,
        width='stretch',
        hide_index=True,
    )


def page_vandalism():
    """Página de monitoramento antivandalismo com IA"""
    st.markdown("# 🚨 Monitor Antivandalismo")
    st.markdown("### Detecção inteligente de atividades suspeitas em patrimônios")

    detector = st.session_state.detector
    vandal_detector = st.session_state.vandalism_detector

    if not detector.ensure_model():
        st.error("Modelo YOLO não disponível. Execute `pip install ultralytics`")
        return

    st.success("✅ Modelo YOLO carregado — sistema de detecção ativo")

    # Configurações
    col1, col2 = st.columns(2)
    with col1:
        confidence = st.slider(
            "Threshold de Confiança (%)", 10, 95,
            value=int(CONFIDENCE_THRESHOLD * 100),
        ) / 100
    with col2:
        st.metric("Alertas Ativos", len(vandal_detector._get_all_alerts()))

    st.divider()

    # Duas abas: Detecção por upload e Simulação ao vivo
    tab1, tab2, tab3 = st.tabs([
        "📤 Analisar Imagem",
        "🎬 Simular Vandalismo",
        "📊 Dashboard de Risco",
    ])

    with tab1:
        st.markdown("#### Faça upload de uma imagem para análise de vandalismo")
        uploaded = st.file_uploader(
            "Escolha uma imagem", type=["jpg", "jpeg", "png", "webp"],
            key="vandal_upload",
        )
        if uploaded:
            from PIL import Image
            image = Image.open(uploaded)
            img_array = np.array(image)

            col_img1, col_img2 = st.columns(2)

            with col_img1:
                st.image(image, caption="Imagem Original", width='stretch')

            with col_img2:
                with st.spinner("🔍 Analisando..."):
                    # Detecta objetos
                    result = detector.detect(img_array, confidence)
                    detections = result.get("objects", [])
                    annotated = result.get("annotated_image", img_array)

                    # Analisa vandalismo
                    analysis = vandal_detector.analyze(
                        detections, camera_id="upload",
                    )

                    # Frame anotado com risco
                    vandal_frame = vandal_detector.annotate_frame(
                        annotated, analysis, detections
                    )
                    st.image(vandal_frame, caption="Análise de Vandalismo", width='stretch')

            # Resultados
            st.divider()
            rcol1, rcol2, rcol3, rcol4 = st.columns(4)
            rcol1.metric("🎯 Risco", analysis.get("risk_level", "NORMAL"))
            rcol2.metric("Score", f"{analysis.get('risk_score', 0):.0%}")
            rcol3.metric("👥 Pessoas", analysis.get("person_count", 0))
            rcol4.metric("🔧 Obj. Suspeitos", len(analysis.get("vandal_tools", [])))

            if analysis.get("risk_factors"):
                st.markdown("#### 🔍 Fatores de Risco")
                for f in analysis["risk_factors"]:
                    level = "🔴" if f["risk"] >= 0.7 else "🟠" if f["risk"] >= 0.5 else "🟡"
                    st.markdown(f"{level} **{f['label']}** — risco {f['risk']:.0%}")

            if analysis.get("alerts"):
                st.error("🚨 **ALERTA DE VANDALISMO**")
                for a in analysis["alerts"]:
                    st.warning(f"[{a['level']}] {a['message']}")

            with st.expander("📋 Relatório Completo"):
                st.markdown(vandal_detector.generate_report(analysis))

            with st.expander("📄 Dados brutos"):
                st.json({
                    "analysis": {k: v for k, v in analysis.items() if k != "alerts"},
                    "objects": detections[:10],
                })

    with tab2:
        st.markdown("#### 🎬 Simulador de Detecção de Vandalismo")
        st.markdown("""
        Use este simulador para testar o sistema de detecção com diferentes cenários.
        O sistema analisa:
        - **🔪 Ferramentas/objetos** perto de pessoas (facas, tacos, garrafas)
        - **👥 Aglomerações** suspeitas (5+ pessoas)
        - **🧍 Pessoa isolada** em área de monumento
        - **🚗 Pessoa + veículo** (possível fuga)
        """)

        # Simulador
        sim_col1, sim_col2 = st.columns(2)

        with sim_col1:
            st.markdown("##### Cenários de Teste")
            scenario = st.selectbox(
                "Escolher cenário:",
                [
                    "🌊 Cena normal — pedestres na via",
                    "🔪 Pessoa com objeto cortante",
                    "👥 Aglomeração suspeita (10 pessoas)",
                    "🧍 Pessoa isolada no monumento",
                    "🚗 Pessoa + veículo suspeitos",
                    "⚔️ Múltiplos vândalos com ferramentas",
                ]
            )

        with sim_col2:
            st.markdown("##### Ações")
            if st.button("▶️ Executar Simulação", width='stretch', type="primary"):
                with st.spinner("🔄 Simulando..."):
                    # Cria detecções simuladas baseadas no cenário
                    sim_detections = _generate_simulated_detections(scenario, confidence)
                    sim_image = _generate_simulated_image(scenario, (640, 480))

                    # Analisa
                    analysis = vandal_detector.analyze(
                        sim_detections, camera_id="simulacao",
                    )
                    annotated = vandal_detector.annotate_frame(
                        sim_image, analysis, sim_detections
                    )

                    st.image(annotated, width='stretch')

                    r1, r2, r3 = st.columns(3)
                    r1.metric("Nível de Risco", analysis.get("risk_level", "NORMAL"))
                    r2.metric("Score", f"{analysis.get('risk_score', 0):.0%}")
                    r3.metric("Fatores", len(analysis.get("risk_factors", [])))

                    if analysis.get("alerts"):
                        for a in analysis["alerts"]:
                            st.error(f"🚨 **{a['level']}**: {a['message']}")

                    with st.expander("📋 Detalhes da Análise"):
                        st.markdown(vandal_detector.generate_report(analysis))

    with tab3:
        st.markdown("#### 📊 Dashboard de Risco em Tempo Real")
        st.markdown("""
        O dashboard mostra o histórico de análises e alertas do sistema.
        *Conecte câmeras ao vivo para monitoramento em tempo real.*
        """)

        alerts = vandal_detector._get_all_alerts()
        if alerts:
            st.markdown("##### 🚨 Alertas Recentes")
            for a in alerts:
                ts = time.strftime('%H:%M:%S', time.localtime(a["timestamp"]))
                st.warning(f"[{ts}] Câmera: {a['camera_id']} — Nível: {a['level']}")
        else:
            st.info("✅ Nenhum alerta no momento. Faça upload de imagens ou execute simulações para testar.")

        # Guia de riscos
        st.divider()
        st.markdown("##### 📋 Guia de Classificação de Risco")
        risk_guide = pd.DataFrame([
            ["✅ NORMAL", "0-15%", "Atividade normal, sem sinais de vandalismo"],
            ["🟢 BAIXO", "15-30%", "Pessoa isolada ou atividade leve"],
            ["🟡 MÉDIO", "30-50%", "Objetos suspeitos ou pequenas aglomerações"],
            ["🟠 ALTO", "50-70%", "Ferramentas perto de pessoas, aglomeração"],
            ["🔴 CRÍTICO", "70-100%", "Múltiplos fatores de risco simultâneos"],
        ], columns=["Nível", "Score", "Descrição"])
        st.dataframe(risk_guide, width='stretch', hide_index=True)


def page_about():
    """Página sobre o sistema"""
    st.markdown(f"# {STREAMLIT_ICON} Sobre o Sistema")
    st.markdown(
        """
    ### Sistema de Visão Computacional para Monitoramento de Patrimônios
    
    Desenvolvido para a **CO-RIO** (Coordenadoria de Operações e Resiliência)
    da Prefeitura do Rio de Janeiro.
    
    #### 🔧 Tecnologias Utilizadas
    
    | Componente | Tecnologia |
    |---|---|
    | **Interface** | Streamlit |
    | **Visão Computacional** | YOLOv11 (Ultralytics) |
    | **Mapas** | Folium / Plotly |
    | **API** | Sistema de Câmeras do Rio |
    | **Linguagem** | Python 3.13+ |
    
    #### 🎯 Funcionalidades
    
    - **Dashboard** → Visão geral do sistema de câmeras
    - **Mapa Interativo** → Visualização geográfica de todas as câmeras
    - **Detector IA** → Identificação automática de patrimônios em imagens
    - **Análise Regional** → Distribuição e densidade por região
    
    #### 📌 Classes Detectáveis
    
    O modelo YOLO pode detectar **80 classes** do dataset COCO, incluindo:
    - 🚶 Pessoas (visitantes, pedestres)
    - 🚗 Veículos (carros, motos, ônibus, caminhões)
    - 🚲 Bicicletas (mobilidade urbana)
    - 🏺 Vasos e ornamentos
    - 🪴 Áreas verdes e paisagismo
    - 🪑 Mobiliário urbano
    - E muito mais...
    
    #### 📞 Contato
    
    **CO-RIO** - Coordenadoria de Operações e Resiliência
    """
    )


# ─── Utilitários ─────────────────────────────────────────────────


def stream_player_html(stream_url: str, height: int = 400) -> str:
    """Gera HTML com iframe para exibir stream (página React)"""
    return f'''
    <div style="border:2px solid #ff4b4b;border-radius:12px;overflow:hidden;
                background:#000;text-align:center;">
      <iframe src="{stream_url}"
              style="width:100%;height:{height}px;border:none;"
              allow="accelerometer;autoplay;encrypted-media;gyroscope"
              allowfullscreen>
      </iframe>
    </div>
    <p style="color:#ff4b4b;font-size:13px;text-align:center;">
      🔴 AO VIVO
    </p>
    '''


def cv2_put_text(img: np.ndarray, text: str, org: tuple) -> np.ndarray:
    """Adiciona texto em imagem OpenCV (fallback sem OpenCV)"""
    try:
        import cv2
        cv2.putText(
            img, text, org,
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2,
        )
    except Exception:
        pass
    return img


# ─── Simulador de Vandalismo ────────────────────────────────────

def _generate_simulated_detections(scenario: str, confidence: float) -> list[dict]:
    """Gera detecções simuladas para teste do sistema antivandalismo"""
    from random import uniform
    cf = confidence or 0.35
    scenarios = {
        "🌊 Cena normal — pedestres na via": [
            {"class_id": 0, "class_name": "pessoa", "confidence": cf + 0.2, "bbox": [100, 200, 150, 350]},
            {"class_id": 0, "class_name": "pessoa", "confidence": cf + 0.3, "bbox": [300, 180, 370, 340]},
            {"class_id": 2, "class_name": "carro", "confidence": cf + 0.4, "bbox": [400, 300, 550, 380]},
            {"class_id": 1, "class_name": "bicicleta", "confidence": cf + 0.1, "bbox": [200, 250, 260, 320]},
        ],
        "🔪 Pessoa com objeto cortante": [
            {"class_id": 0, "class_name": "pessoa", "confidence": cf + 0.3, "bbox": [200, 150, 280, 400]},
            {"class_id": 0, "class_name": "pessoa", "confidence": cf + 0.2, "bbox": [350, 180, 400, 360]},
            {"class_id": 42, "class_name": "faca", "confidence": cf + 0.15, "bbox": [230, 280, 260, 340]},
            {"class_id": 72, "class_name": "livro", "confidence": cf + 0.3, "bbox": [100, 300, 140, 350]},
        ],
        "👥 Aglomeração suspeita (10 pessoas)": [
            {"class_id": 0, "class_name": "pessoa", "confidence": cf + uniform(0.1, 0.4), "bbox": [50 + i*50, 150 + i*10, 100 + i*50, 350]}
            for i in range(10)
        ],
        "🧍 Pessoa isolada no monumento": [
            {"class_id": 0, "class_name": "pessoa", "confidence": cf + 0.3, "bbox": [250, 100, 320, 420]},
        ],
        "🚗 Pessoa + veículo suspeitos": [
            {"class_id": 0, "class_name": "pessoa", "confidence": cf + 0.25, "bbox": [150, 220, 200, 380]},
            {"class_id": 0, "class_name": "pessoa", "confidence": cf + 0.2, "bbox": [180, 230, 230, 390]},
            {"class_id": 2, "class_name": "carro", "confidence": cf + 0.4, "bbox": [350, 280, 500, 380]},
            {"class_id": 75, "class_name": "tesoura", "confidence": cf + 0.1, "bbox": [170, 320, 195, 360]},
        ],
        "⚔️ Múltiplos vândalos com ferramentas": [
            {"class_id": 0, "class_name": "pessoa", "confidence": cf + 0.3, "bbox": [100, 150, 170, 380]},
            {"class_id": 0, "class_name": "pessoa", "confidence": cf + 0.25, "bbox": [300, 140, 370, 390]},
            {"class_id": 0, "class_name": "pessoa", "confidence": cf + 0.2, "bbox": [450, 160, 510, 370]},
            {"class_id": 33, "class_name": "taco_de_beisebol", "confidence": cf + 0.15, "bbox": [320, 260, 380, 310]},
            {"class_id": 42, "class_name": "faca", "confidence": cf + 0.1, "bbox": [140, 290, 165, 340]},
            {"class_id": 39, "class_name": "garrafa", "confidence": cf + 0.2, "bbox": [470, 280, 510, 340]},
        ],
    }
    return scenarios.get(scenario, scenarios["🌊 Cena normal — pedestres na via"])


def _generate_simulated_image(scenario: str, size: tuple = (640, 480)) -> np.ndarray:
    """Gera imagem simulada para visualização do cenário de vandalismo"""
    img = np.ones((*size[::-1], 3), dtype=np.uint8) * 220

    # Desenha um "monumento" (retângulo central)
    cv2_rect(img, (260, 100), (380, 350), (160, 140, 120), -1)
    cv2_rect(img, (270, 110), (370, 340), (180, 160, 140), -1)

    if "aglomeração" in scenario.lower() or "10 pessoas" in scenario:
        # Muitas pessoas
        for i in range(10):
            x = 60 + i * 50
            y = 150 + (i % 3) * 30
            cv2_circle(img, (x, y), 15, (50 + i * 10, 100, 50), -1)
        cv2_put_text(img, "AGLOMERACAO", (200, 50))
    elif "ferramentas" in scenario.lower() or "múltiplos" in scenario.lower():
        cv2_put_text(img, "MULTIPLOS VANDALOS", (200, 50))
        for i in range(3):
            x = 100 + i * 200
            cv2_circle(img, (x, 200), 20, (100, 80, 60), -1)
            cv2_rect(img, (x - 10, 220), (x + 10, 350), (60, 50, 40), -1)
    elif "objeto cortante" in scenario.lower() or "faca" in scenario.lower():
        cv2_put_text(img, "SUSPEITO COM OBJETO", (180, 50))
        cv2_circle(img, (240, 200), 20, (100, 80, 60), -1)
        cv2_rect(img, (230, 220), (250, 350), (60, 50, 40), -1)
        cv2_line(img, (245, 290), (260, 340), (0, 0, 255), 3)
    elif "isolada" in scenario.lower():
        cv2_put_text(img, "PESSOA ISOLADA", (220, 50))
        cv2_circle(img, (285, 200), 20, (100, 80, 60), -1)
        cv2_rect(img, (275, 220), (295, 350), (60, 50, 40), -1)
    elif "veículo" in scenario.lower() or "veiculo" in scenario.lower():
        cv2_put_text(img, "VEICULO SUSPEITO", (200, 50))
        cv2_circle(img, (180, 200), 20, (100, 80, 60), -1)
        cv2_rect(img, (170, 220), (190, 350), (60, 50, 40), -1)
        cv2_rect(img, (380, 280), (500, 360), (80, 80, 200), -1)
    else:
        cv2_put_text(img, "CENA NORMAL", (250, 50))
        cv2_circle(img, (150, 250), 18, (100, 150, 80), -1)
        cv2_circle(img, (330, 240), 18, (100, 150, 80), -1)
        cv2_rect(img, (420, 300), (540, 370), (120, 130, 200), -1)

    return img


def cv2_rect(img, pt1, pt2, color, thickness):
    try:
        import cv2
        cv2.rectangle(img, pt1, pt2, color, thickness)
    except Exception:
        pass

def cv2_circle(img, center, radius, color, thickness):
    try:
        import cv2
        cv2.circle(img, center, radius, color, thickness)
    except Exception:
        pass

def cv2_line(img, pt1, pt2, color, thickness):
    try:
        import cv2
        cv2.line(img, pt1, pt2, color, thickness)
    except Exception:
        pass


# ─── Main ────────────────────────────────────────────────────────

def main():
    """Função principal - orquestra a renderização"""
    auto_init()
    load_cameras_async()
    render_sidebar()

    # Roteamento de páginas
    pages = {
        "dashboard": page_dashboard,
        "patrimonios": page_patrimonios,
        "mapa": page_map,
        "detector": page_detector,
        "vandalismo": page_vandalism,
        "analise": page_analysis,
        "sobre": page_about,
    }

    current_page = st.session_state.page
    if current_page in pages:
        pages[current_page]()
    else:
        page_dashboard()


if __name__ == "__main__":
    main()
