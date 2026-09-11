---
title: Biskate Analytics NFL Odds API
emoji: 🏈
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# 🏈 Biskate Analytics — NFL Odds EV & Player Props Intelligence

Plataforma de alta precisão quantitativa para precificação, análise de Expected Value (+EV) e recomendação inteligente de apostas em mercados de **Player Props** da NFL (Rushing, Passing e Receiving Yards).

O sistema integra dados oficiais da NFL (`nflreadpy`), modelos probabilísticos treinados via **XGBoost Quantile Regression**, raspagem automatizada de linhas e odds (Betclic via Playwright), dimensionamento dinâmico de risco (Critério de Kelly fracionário com penalidades de cauda) e inteligência generativa via **Google Gemini Flash** com Scout de notícias e depth charts em tempo real.

---

## 🏛️ Estrutura e Organização do Repositório

O projeto segue os mais rigorosos padrões da indústria para repositórios de Machine Learning e Fullstack:

```text
nfl-odds/
├── archive/                     # Cópias e protótipos legados preservados
│   └── frontend-vite-backup/    # Protótipo inicial em Vite/React
│
├── assets/                      # Recursos visuais e branding
│   └── branding/                # Logos e monogramas vetoriais (SVG)
│
├── data/                        # Artefatos de dados e modelos treinados
│   ├── depth_charts_2026_2027/  # Mapeamentos e depth charts 2026-2027
│   ├── *.parquet                # Parquets de features, odds e value bets
│   ├── *.joblib                 # Pesos dos modelos XGBoost treinados
│   ├── *.json                   # Caches de IA e notícias (ai_summaries, news)
│   └── nfl_odds.db              # Banco SQLite de histórico de apostas
│
├── docs/                        # Documentação técnica e especificações
│   ├── DESIGN.md                # Arquitetura detalhada do sistema e specs
│   ├── FEATURES.md              # Fórmulas e documentação de feature engineering
│   ├── DEPTH_CHARTS_2026_2027.md# Notas de elenco e depth charts ofensivos
│   └── VALIDATION_ROADMAP.md    # Roadmap de auditoria e validação de modelos
│
├── frontend/                    # Aplicação Web (Next.js 16 + React 19 + TailwindCSS)
│   ├── src/app/                 # Páginas e layout com design system Dark/Gold
│   ├── src/components/          # Componentes de interface (PropCard, Filtros, Modais)
│   ├── public/                  # Logos dos times da NFL e ícones estáticos
│   └── package.json             # Dependências e scripts do frontend
│
├── notebooks/                   # Jupyter Notebooks de EDA e exploração
│   └── pilot.ipynb              # Notebook piloto de testes e exploração
│
├── scripts/                     # Scripts de automação, CLI e utilitários
│   ├── dev.sh                   # Script para subir Backend (:8000) e Frontend (:3000)
│   ├── share.sh                 # Compartilhamento do servidor via Cloudflare Tunnel
│   ├── run_pipeline.py          # Execução manual da pipeline de predição
│   ├── run_scraper.py           # Raspador das linhas de apostas
│   ├── ev_backtest.py           # Backtest de rentabilidade e ROI histórico
│   ├── download_logos.py        # Download dos escudos oficiais da NFL para o frontend
│   ├── regenerate_all.py        # Regeneração em lote dos resumos via Gemini
│   ├── reproduce_audit.py       # Reprodução da auditoria estatística do modelo
│   └── exploratory/             # Scripts de teste, depuração e exploração isolados
│
├── src/                         # Código-fonte do pacote Python (`nfl_odds`)
│   └── nfl_odds/
│       ├── ai/                  # Integração com Gemini Flash e Scout de notícias
│       ├── betting/             # Cálculo de EV e Dynamic Sizing (Kelly Criterion)
│       ├── dashboard/           # Backend FastAPI (`api.py`) e Streamlit (`app.py`)
│       ├── data/                # Carregamento de dados da NFL, DB e Depth Charts
│       ├── features/            # Engenharia de atributos e patch Week 1
│       ├── models/              # Treinamento e inferência dos modelos XGBoost
│       ├── odds/                # Scraper do Betclic e ingestão de linhas
│       └── pipeline.py          # Pipeline ponta a ponta orquestrada
│
├── tests/                       # Suíte de testes automatizados (Pytest)
│   ├── __init__.py
│   └── test_dynamic_sizing.py   # Testes unitários do dimensionamento de risco
│
├── pipeline.py                  # Ponto de entrada CLI raiz (atalho para nfl_odds.pipeline)
├── pyproject.toml               # Configuração do projeto uv, dependências e pytest
├── uv.lock                      # Trava de versões determinística
├── .env.example                 # Modelo de variáveis de ambiente
└── README.md                    # Documentação principal
```

---

## 🚀 Como Começar

### 1. Pré-requisitos
- Python `>= 3.12`
- Gerenciador [uv](https://docs.astral.sh/uv/) instalado
- Node.js `>= 18` e npm

### 2. Configuração do Ambiente

Clone o repositório e configure as variáveis de ambiente:
```bash
# Copie o arquivo de exemplo
cp .env.example .env
```

Preencha no seu `.env` a chave da API do Gemini (`GEMINI_API_KEY`) e as credenciais necessárias.

Instale as dependências de backend via `uv`:
```bash
uv sync
```

Instale as dependências do frontend:
```bash
npm install --prefix frontend
```

---

## 💻 Executando o Projeto

### Modo de Desenvolvimento Completo (Backend + Frontend)
Para rodar simultaneamente a API FastAPI (`http://localhost:8000`) e a interface Next.js (`http://localhost:3000`):
```bash
bash scripts/dev.sh
```

### Executar a Pipeline de Modelagem e +EV
Para treinar os modelos XGBoost, extrair probabilidades, calcular o Expected Value (+EV) e gerar resumos de IA para as oportunidades:
```bash
# Via executável direto:
uv run python pipeline.py --live

# Ou via comando registrado no pyproject.toml:
uv run nfl-odds --live
```

### Coletar Novas Odds do Bookmaker
Para raspar as linhas mais recentes de apostas (usando os links definidos em `data/links.txt`):
```bash
uv run python scripts/run_scraper.py
```

### Rodar os Testes Unitários
Para validar a lógica de cálculo de risco, sizing e filtros de EV:
```bash
uv run pytest
```

---

## 📊 Módulos do Sistema

| Módulo | Localização | Responsabilidade |
|---|---|---|
| **Data Engine** | [`src/nfl_odds/data/`](src/nfl_odds/data/) | Ingestão de play-by-play, snap counts, injuries e rosters oficiais via `nflreadpy`. |
| **Feature Engineering** | [`src/nfl_odds/features/`](src/nfl_odds/features/) | Cálculo de médias móveis, métricas avançadas (WOPR, EPA, PROE) e patch de início de temporada. |
| **Machine Learning** | [`src/nfl_odds/models/`](src/nfl_odds/models/) | Modelagem quantílica e temporal com XGBoost para distribuição empírica de jardas. |
| **EV & Sizing** | [`src/nfl_odds/betting/`](src/nfl_odds/betting/) | Avaliação de valor esperado (+EV), Critério de Kelly fracionário e blindagem contra armadilhas. |
| **Odds Ingestion** | [`src/nfl_odds/odds/`](src/nfl_odds/odds/) | Web scraping assíncrono via Playwright Stealth e parsing das linhas de mercado. |
| **AI Intelligence** | [`src/nfl_odds/ai/`](src/nfl_odds/ai/) | Geração de relatórios com Google Gemini Flash analisando matchup, notícias e profundidade. |
| **API & Dashboard** | [`src/nfl_odds/dashboard/`](src/nfl_odds/dashboard/) & [`frontend/`](frontend/) | API RESTful com FastAPI e dashboard interativo moderno construído com Next.js 16 e React 19. |

---

## 📖 Documentação Detalhada

Para se aprofundar nos fundamentos teóricos e matemáticos do projeto:
- 📐 [**Design & Arquitetura do Sistema**](docs/DESIGN.md)
- 🧮 [**Especificação das Features & Fórmulas**](docs/FEATURES.md)
- 📋 [**Depth Charts Ofensivos 2026-2027**](docs/DEPTH_CHARTS_2026_2027.md)
- 🗺️ [**Roadmap de Validação e Auditoria**](docs/VALIDATION_ROADMAP.md)
