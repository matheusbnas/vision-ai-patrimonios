# 🏛️ Visão Computacional - Patrimônios do Rio

Sistema de visão computacional para monitoramento de patrimônios públicos
da cidade do Rio de Janeiro, utilizando as câmeras da CO-RIO.

## 🚀 Como Executar

```bash
# Ativar ambiente virtual
.venv\Scripts\activate

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
