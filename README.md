# 🏛️ Visão Patrimônios v2.0

**Sistema de Visão Computacional para Monitoramento de Patrimônios Públicos do Rio de Janeiro**

CO-RIO — Coordenadoria de Operações e Resiliência

---

## 📋 Visão Geral

Sistema profissional com **separação frontend/backend** para monitoramento inteligente de patrimônios públicos utilizando múltiplos modelos de IA:

- **YOLO11n** — Detecção de objetos em tempo real (80 classes COCO)
- **KzRyan/Burglary_and_Vandalism** (Hugging Face) — CNN-Transformer Híbrido para classificação de vandalismo
- **dolphinium/damaged-building-detection** (Hugging Face) — YOLOv5 para detecção de danos estruturais

---

## 🏗️ Arquitetura

```
vision-ai-patrimonios/
├── backend/                    # FastAPI (Python)
│   ├── app/
│   │   ├── main.py            # Entrypoint FastAPI
│   │   ├── config.py          # Configurações centralizadas
│   │   ├── api/               # Rotas REST
│   │   │   ├── auth.py        # Autenticação
│   │   │   ├── cameras.py     # Câmeras
│   │   │   ├── detection.py   # Detecção YOLO
│   │   │   ├── vandalism.py   # Vandalismo + HF
│   │   │   └── dashboard.py   # Dashboard
│   │   ├── models/            # Modelos de IA
│   │   │   ├── detector.py    # YOLO detector
│   │   │   ├── vandalism.py   # Análise heurística
│   │   │   ├── hf_model.py    # Wrapper Hugging Face
│   │   │   └── hf_hybrid.py   # Arquitetura CNN-Transformer
│   │   ├── services/          # Serviços
│   │   │   ├── camera_service.py
│   │   │   └── detection_service.py
│   │   └── schemas/           # Pydantic schemas
│   ├── requirements.txt
│   └── .env
├── frontend/                   # React + TypeScript + Vite
│   ├── src/
│   │   ├── App.tsx
│   │   ├── api/client.ts      # Cliente HTTP
│   │   ├── components/        # Sidebar, Header
│   │   ├── pages/             # Dashboard, Patrimônios, Mapa, Detector, Vandalismo, Sobre
│   │   └── types/index.ts     # Tipos TypeScript
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

---

## 🚀 Como Executar

### Backend

```bash
# 1. Criar ambiente virtual
cd backend
python -m venv .venv
.venv\Scripts\activate

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar .env (já existe com valores padrão)

# 4. Executar servidor
python -m app.main
# Acessar: http://localhost:8000
# Documentação: http://localhost:8000/docs
```

### Frontend

```bash
# 1. Instalar dependências
cd frontend
npm install

# 2. Executar em modo dev
npm run dev
# Acessar: http://localhost:5173
```

---

## 🤖 Modelos Hugging Face Integrados

### 1. KzRyan/Burglary_and_Vandalism
- **Tipo:** CNN-Transformer Híbrido
- **Backbone:** ResNet18 + Transformer Encoder
- **Tamanho:** 138 MB
- **Classes:** `normal`, `burglary`, `vandalism`
- **Uso:** Classificação de vídeos/imagens para detecção de vandalismo
- **Link:** [Hugging Face](https://huggingface.co/KzRyan/Burglary_and_Vandalism)

### 2. dolphinium/damaged-building-detection
- **Tipo:** YOLOv5
- **Dataset:** RescueNet
- **Uso:** Detecção de danos estruturais em construções/monumentos
- **Link:** [Hugging Face](https://huggingface.co/dolphinium/damaged-building-detection)

---

## 🔬 Transfer Learning

Os modelos do Hugging Face podem ser fine-tunados para o domínio específico:

```python
# Exemplo de fine-tuning com o modelo CNN-Transformer
from app.models.hf_hybrid import build_model

model = build_model({
    "num_classes": 3,  # normal, burglary, vandalism
    "backbone": "resnet18",
    "pretrained": True,  # Carrega pesos pré-treinados
})

# Fine-tune com dataset local de patrimônios cariocas
# ...
```

---

## 📡 Endpoints da API

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/health` | Health check |
| `POST` | `/api/auth/login` | Autenticação |
| `GET` | `/api/cameras` | Lista câmeras |
| `GET` | `/api/cameras/{code}` | Detalhes da câmera |
| `POST` | `/api/detect` | Detecção YOLO |
| `POST` | `/api/detect/full` | Pipeline completo (YOLO + HF) |
| `POST` | `/api/vandalism/analyze` | Análise heurística de vandalismo |
| `POST` | `/api/vandalism/hf-predict` | Predição com modelo HF |
| `GET` | `/api/vandalism/hf-models` | Info dos modelos HF |
| `GET` | `/api/dashboard/stats` | Estatísticas do dashboard |

---

## 🛠️ Stack Tecnológica

| Camada | Tecnologia |
|--------|------------|
| **Backend** | FastAPI + Uvicorn |
| **Frontend** | React 18 + TypeScript |
| **Build** | Vite |
| **Estilos** | TailwindCSS |
| **Mapas** | Leaflet + React-Leaflet |
| **Gráficos** | Recharts |
| **CV** | YOLO (Ultralytics) + OpenCV |
| **IA** | PyTorch + Hugging Face Hub |
| **API** | REST + Swagger/OpenAPI |

---

## 📄 Licença

MIT — CO-RIO

# Instalar dependências
pip install -r requirements.txt

# Executar o dashboard
streamlit run app.py
```

## 📋 Funcionalidades

- **📊 Dashboard** → KPIs e visão geral do sistema de câmeras
- **🗺️ Mapa Interativo** → Visualização geográfica de todas as 10.000+ câmeras
- **🔍 Detector IA** → Identificação automática de patrimônios via YOLO
- **📈 Análise Regional** → Distribuição e densidade por região

## 🔧 Tecnologias

- Streamlit (Interface)
- YOLOv11 / Ultralytics (Visão Computacional)
- Folium + Plotly (Mapas e Gráficos)
- API REST (Câmeras do Rio)

## 📁 Estrutura

```
vision-ai-patrimonios/
├── app.py          # Aplicação Streamlit principal
├── api_client.py   # Cliente HTTP para API de câmeras
├── detector.py     # Módulo de visão computacional (YOLO)
├── config.py       # Configurações e constantes
├── requirements.txt
└── .env            # Credenciais da API
```
