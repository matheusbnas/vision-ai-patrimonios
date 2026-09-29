# 🏛️ Visão Patrimônios v3.0

**Visão computacional para monitoramento de patrimônios públicos do Rio de Janeiro**

COR — Centro de Operações e Resiliência · Prefeitura da Cidade do Rio de Janeiro

---

## 📋 Visão geral

Plataforma web (FastAPI + React) que acompanha monumentos da cidade pelas câmeras do COR e gera alertas de risco ao patrimônio:

- **Detecção e rastreamento de pessoas/objetos** com YOLO26n + ByteTrack
- **Interação com a estátua** (mão na área sensível, pessoa em cima do pedestal) com YOLO26n-pose
- **Mudança física / pichação** na superfície calibrada da estátua (comparação SSIM + monitor de superfície)
- **Objetos de risco** (faca, tesoura, taco, garrafa) e **permanência suspeita** junto ao monumento
- **Evidências**: imagens e clipe de alguns segundos antes e depois de cada evento
- **Mapa de perímetro**: câmeras próximas de cada patrimônio num raio configurável
- Modelos Hugging Face auxiliares para classificação de vandalismo e danos estruturais

---

## ✨ Novidades (setembro/2026)

### Interface
- **Identidade visual do COR**: logo oficial da Prefeitura/COR no header; o rodapé da sidebar usa o brasão e o texto "Centro de Operações e Resiliência" recortados da logo oficial.
- **Sidebar dinâmica**:
  - Pode ser ocultada ou exibida pelo botão do header ou com **Ctrl+B**.
  - Pode ficar completa ou compacta (só ícones).
  - A escolha fica salva no navegador.
  - Em telas menores que 1024 px, vira uma gaveta sobreposta (fecha com Esc, clique fora ou ao navegar).
- **Visual renovado**:
  - Fonte Inter, sidebar em degradê com seções (Visão geral, Operação, Sistema) e item ativo em dourado.
  - Header com status da API e dos modelos em formato de etiqueta, e barras de rolagem discretas.

### Data e hora
- **Relógio no header** com dia da semana, data e hora, sempre no **horário de Brasília**, independente do PC do operador.
- **Selo de data/hora em cada câmera** do Monitoramento, no estilo de CFTV:
  - mostra o instante da imagem exibida e a situação dela;
  - atualiza a cada segundo, então a câmera muda de cor sozinha se parar de atualizar;
  - o ponto no cabeçalho do card segue a mesma cor.

  | Tipo de câmera | Situação exibida |
  |---|---|
  | Vídeo contínuo com IA | 🟢 AO VIVO (≤ 6 s) · 🟡 ATRASO (≤ 30 s) · 🔴 SEM SINAL |
  | Print + IA (ciclo de 10 s) | 🟢 MONITORANDO (≤ 45 s) · 🟡 ATRASADO (≤ 3 min) · 🔴 DESATUALIZADO · 🔴 FALHA · ⚪ PAUSADO / AGUARDANDO |
  | Player da câmera | 🟢 TRANSMISSÃO · 🔴 SEM SINAL |

### Mapa de Câmeras com perímetro de vigilância
- Cada patrimônio monitorado aparece com um **raio de vigilância** ajustável de 100 m a 1,5 km (padrão 300 m, fica salvo).
- **Cores das câmeras:**
  - 🟡 dourado: câmeras fixas do patrimônio;
  - 🟢 verde: câmeras dentro do raio;
  - 🔴 vermelho pulsando: câmeras com alerta nos últimos 30 min (o patrimônio também fica vermelho);
  - cinza: as demais câmeras da cidade, agrupadas, que podem ser ocultadas.
- Ao selecionar um patrimônio:
  - o mapa aproxima no raio e traça linhas até cada câmera do perímetro;
  - o painel lista as câmeras por distância (fixa / ao vivo) e os alertas recentes.
- **"Monitorar perímetro"** abre o Monitoramento com as câmeras fixas e as mais próximas (até 16, o limite por ciclo do backend) e já inicia a varredura.
- Status ao vivo e alertas são atualizados a cada 15 s.

> **Limitação atual:** "monitorar perímetro" usa o ciclo de print + IA. A captura de vídeo contínua (`LIVE_CAPTURE_CODES`) é definida na inicialização do backend e não é ligada pelo mapa.

---

## 🖥️ Telas

| Tela | O que faz |
|---|---|
| **Dashboard** | Indicadores gerais: patrimônios, câmeras, alertas e detecções |
| **Patrimônios** | Patrimônios monitorados, suas câmeras fixas e o vídeo de cada uma |
| **Mapa** | Patrimônios, raio de vigilância e câmeras do perímetro (ver acima) |
| **Monitoramento** | Grade de câmeras com vídeo ao vivo ou print + IA, alertas, comparação com referência, calibração de zona/contorno e selo de data/hora |
| **Antivandalismo** | Classificação de imagens com os modelos Hugging Face |
| **Sobre** | Informações do sistema |

O **sino de alertas** no header toca um som, mostra um contador e lista os alertas novos; clicar leva ao Monitoramento. O som pode ser silenciado e a preferência fica salva.

---

## 🧠 Como a detecção funciona

1. **Ciclo de print + IA** (câmeras dos patrimônios):
   - O backend captura um print de cada câmera com Playwright, uma por vez.
   - O print passa por: YOLO (objetos de risco e permanência), pose (interação com a estátua) e comparação SSIM com a imagem de referência (mudança física).
   - Um monitor em segundo plano (`BACKGROUND_MONITOR_*`) faz essa varredura mesmo sem ninguém com a tela aberta.
2. **Vídeo contínuo** (câmeras em `LIVE_CAPTURE_CODES`):
   - Um Chrome headless mantém a página de vídeo aberta e lê frames a `LIVE_CAPTURE_FPS`.
   - A análise contínua (YOLO + ByteTrack a `LIVE_ANALYSIS_FPS`) acompanha cada pessoa por ID e marca "suspeito" quem fica junto à superfície da estátua.
   - Uma mudança persistente na superfície atribuída a um suspeito gera alerta **CRÍTICO** com clipe de evidência (`EVIDENCE_PRE_SECONDS` / `EVIDENCE_POST_SECONDS`).
3. **Alertas** vêm de várias origens:
   - `risk`: objeto de risco;
   - `interaction`: pose;
   - `ssim`: mudança física;
   - `surface`: pichação ou alteração na superfície;
   - `loitering`: permanência.

   Níveis: MODERADO, ALTO e CRÍTICO. O mesmo tipo de alerta não notifica de novo antes de `NOTIFY_COOLDOWN_SECONDS`.

> Cada câmera em vídeo contínuo consome um Chrome (~200–400 MB de RAM). Adicione poucas por vez e acompanhe em `GET /api/monitor/live-capture/status`.

---

## 🏗️ Arquitetura

```
vision-ai-patrimonios/
├── backend/                         # FastAPI (Python)
│   ├── app/
│   │   ├── main.py                  # Entrypoint; inicia monitor em background e captura contínua
│   │   ├── config.py                # Configurações, patrimônios e câmeras fixas (PATRIMONIOS)
│   │   ├── api/
│   │   │   ├── auth.py              # Autenticação na API de câmeras
│   │   │   ├── cameras.py           # Câmeras, streams
│   │   │   ├── monitor.py           # Monitoramento, zona/contorno, referência, vídeo contínuo
│   │   │   ├── alerts.py            # Consulta de alertas (polling incremental)
│   │   │   ├── dashboard.py         # Estatísticas e patrimônios
│   │   │   ├── vandalism.py         # Modelos Hugging Face
│   │   │   ├── video_proxy.py       # Proxy do player de vídeo
│   │   │   └── webhooks.py          # Receptor de webhooks OctaVision
│   │   ├── models/
│   │   │   ├── detector.py          # YOLO + ByteTrack
│   │   │   ├── interaction.py       # Pose: interação com a estátua
│   │   │   ├── change_detector.py   # Mudança física (SSIM)
│   │   │   ├── surface_monitor.py   # Alteração na superfície da estátua
│   │   │   ├── hf_model.py / hf_hybrid.py
│   │   │   └── demo_scene.py
│   │   ├── services/
│   │   │   ├── camera_service.py
│   │   │   ├── detection_service.py
│   │   │   ├── background_monitor.py  # Varredura contínua das câmeras dos patrimônios
│   │   │   ├── live_capture.py        # Vídeo contínuo (Chrome headless)
│   │   │   ├── live_analysis.py       # Análise contínua + eventos de superfície
│   │   │   ├── alert_service.py
│   │   │   ├── evidence_service.py    # Imagens e clipes de evidência
│   │   │   ├── risk_tracker.py
│   │   │   └── zone_service.py        # Zona monitorada e contorno da estátua
│   │   └── schemas/
│   ├── assets/                      # Imagens de referência/evidências (servidas em /assets)
│   ├── requirements.txt
│   └── .env.example
├── frontend/                        # React 18 + TypeScript + Vite + Tailwind
│   ├── src/
│   │   ├── App.tsx                  # Layout, estado da sidebar, navegação
│   │   ├── api/client.ts
│   │   ├── assets/                  # Logo do COR (completa, brasão e texto)
│   │   ├── components/
│   │   │   ├── Sidebar.tsx / Header.tsx
│   │   │   ├── LiveClock.tsx        # Relógio (horário de Brasília)
│   │   │   ├── CameraClock.tsx      # Selo de data/hora e situação da câmera
│   │   │   ├── AlertNotifier.tsx    # Sino de alertas
│   │   │   ├── CameraStreamView.tsx / HlsVideoPlayer.tsx
│   │   │   └── ZoneCalibrator.tsx
│   │   ├── pages/                   # Dashboard, Patrimônios, Mapa, Monitoramento, Vandalismo, Sobre
│   │   └── types/index.ts
│   └── package.json
└── README.md
```

---

## 🚀 Como executar

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows (Linux/macOS: source .venv/bin/activate)

pip install -r requirements.txt
playwright install chromium       # captura de prints e vídeo contínuo

copy .env.example .env            # e preencha as credenciais
python -m app.main
# API:  http://localhost:8000
# Docs: http://localhost:8000/docs
```

Os pesos `yolo26n.pt` e `yolo26n-pose.pt` são baixados automaticamente pelo Ultralytics na primeira execução.

### Frontend

```bash
cd frontend
npm install
npm run dev
# http://localhost:5173
```

Para apontar para outro backend, defina `VITE_API_BASE` (ex.: `VITE_API_BASE=http://servidor:8000`).

---

## ⚙️ Configuração (`backend/.env`)

| Variável | Padrão | Descrição |
|---|---|---|
| `API_BASE_URL`, `API_EMAIL`, `API_PASSWORD`, `API_KEY` | — | Acesso à API de câmeras |
| `STREAM_BASE_URL`, `STREAM_KEY`, `VIDEO_PAGE_BASE_URL` | — | Streams e páginas de vídeo |
| `CORS_ORIGINS` | `http://localhost:5173,…` | Origens liberadas para o frontend |
| `YOLO_MODEL` / `POSE_MODEL` | `yolo26n.pt` / `yolo26n-pose.pt` | Pesos dos modelos |
| `CONFIDENCE_THRESHOLD` | `0.35` | Confiança mínima do YOLO |
| `BACKGROUND_MONITOR_ENABLED` | `true` | Varredura contínua das câmeras dos patrimônios |
| `BACKGROUND_MONITOR_INTERVAL_SECONDS` | `20` | Intervalo da varredura |
| `LIVE_CAPTURE_CODES` | `000056` | Câmeras com vídeo contínuo (separadas por vírgula) |
| `LIVE_CAPTURE_FPS` / `LIVE_ANALYSIS_FPS` | `4` / `2` | Frames lidos / analisados por segundo |
| `SURFACE_SUSPECT_SECONDS` | `4` | Tempo junto à superfície para virar "suspeito" |
| `SURFACE_CHANGE_MIN_FRAC` | `0.015` | Fração da superfície alterada que conta como mudança |
| `EVIDENCE_PRE_SECONDS` / `EVIDENCE_POST_SECONDS` | `15` / `5` | Duração do clipe de evidência |
| `NOTIFY_COOLDOWN_SECONDS` | `300` | Intervalo mínimo entre notificações iguais |
| `PERSON_LOITERING_ALERT_SECONDS` | `600` | Permanência que gera alerta preventivo |
| `HF_TOKEN` | — | Token do Hugging Face (opcional) |
| `OCTAVISION_WEBHOOK_TOKEN` | — | Token do webhook OctaVision |

Os patrimônios monitorados e suas câmeras fixas ficam em `PATRIMONIOS`, em [backend/app/config.py](backend/app/config.py).

---

## 📡 Principais endpoints

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/health` | Saúde da API e status dos modelos |
| `POST` | `/api/auth/login` | Autenticação na API de câmeras |
| `GET` | `/api/cameras` | Lista de câmeras (com coordenadas) |
| `POST` | `/api/cameras/by-codes` | Câmeras por códigos |
| `GET` | `/api/cameras/{code}/stream` | URL do stream |
| `GET` | `/api/dashboard/stats` | Estatísticas do dashboard |
| `GET` | `/api/dashboard/patrimonios` | Patrimônios monitorados |
| `GET` | `/api/monitor/multi?codes=…` | Print + IA de várias câmeras (até 16) |
| `POST` | `/api/monitor/snapshot/{code}` | Print sem IA |
| `POST` | `/api/monitor/change/{code}/reference` | Define imagem de referência |
| `GET` | `/api/monitor/change/{code}` | Compara com a referência (SSIM) |
| `GET`/`PUT`/`DELETE` | `/api/monitor/zone/{code}` | Zona monitorada |
| `GET`/`PUT`/`DELETE` | `/api/monitor/statue/{code}` | Contorno da estátua |
| `GET` | `/api/monitor/live-capture/status` | Situação do vídeo contínuo (FPS, idade do último frame, RAM/CPU) |
| `GET` | `/api/monitor/live-analysis/{code}/stream.mjpg` | Frames analisados em tempo real (MJPEG) |
| `GET` | `/api/monitor/surface-events` | Eventos de superfície (pichação/alteração) |
| `GET` | `/api/alerts` | Alertas (filtros: `since`, `camera_code`, `level`, `after_id`, `notify`) |
| `POST` | `/api/vandalism/hf-predict` | Classificação com modelo Hugging Face |
| `POST` | `/api/webhooks/octavision` | Receptor de eventos OctaVision |

A documentação completa fica em `/docs` (Swagger).

---

## 🤖 Modelos

| Modelo | Uso |
|---|---|
| **YOLO26n** (Ultralytics) | Pessoas, veículos e objetos de risco (80 classes COCO, traduzidas) + rastreamento ByteTrack |
| **YOLO26n-pose** | Pontos do corpo (mãos, quadril, pés) para detectar interação com a estátua |
| **KzRyan/Burglary_and_Vandalism** | CNN-Transformer (ResNet18 + Transformer): `normal`, `burglary`, `vandalism` · [Hugging Face](https://huggingface.co/KzRyan/Burglary_and_Vandalism) |
| **dolphinium/damaged-building-detection** | YOLOv5 (RescueNet) para danos estruturais · [Hugging Face](https://huggingface.co/dolphinium/damaged-building-detection) |

O COCO não tem classes para spray, martelo ou barra de metal. Detectar esses objetos exigiria um modelo treinado para isso ou de vocabulário aberto.

---

## 🔭 Próximos passos em estudo

**Reidentificação do suspeito nas câmeras do perímetro (ReID por aparência, não reconhecimento facial).** Ideia em avaliação:

1. Ao ocorrer um alerta, guardar recortes da pessoa envolvida, usando o ID do ByteTrack.
2. Gerar uma assinatura de aparência com **OSNet** (via BoxMOT) e uma descrição textual com **CLIP**.
3. Procurar pessoas parecidas nas câmeras do raio durante alguns minutos, filtrando pela distância e pelo tempo de caminhada.
4. Emitir um alerta de "possível suspeito" no sino e mostrar a trilha no Mapa.

O resultado seria sempre uma sugestão para o operador confirmar ou descartar.

Pontos em aberto:
- captura mais frequente nas câmeras do perímetro após um alerta;
- calibração com imagens reais;
- validação jurídica e retenção limitada dos dados.

---

## 🛠️ Stack

| Camada | Tecnologia |
|---|---|
| Backend | FastAPI + Uvicorn, Playwright (Chrome headless) |
| Visão computacional | Ultralytics YOLO26 + ByteTrack, OpenCV, PyTorch |
| IA auxiliar | Hugging Face Hub |
| Frontend | React 18 + TypeScript + Vite |
| Estilos | TailwindCSS, fonte Inter, ícones Lucide |
| Gráficos | Recharts |
| Mapas | Leaflet + React-Leaflet + marker cluster (base CARTO Voyager / OpenStreetMap) |
| Vídeo | HLS (hls.js), MJPEG, player da Tixxi |

---

## 📄 Licença

MIT — COR · Prefeitura da Cidade do Rio de Janeiro
