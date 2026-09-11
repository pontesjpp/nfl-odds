FROM python:3.12-slim

# Instalar dependências básicas de sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Instalar o gerenciador de pacotes uv
RUN pip install --no-cache-dir uv

# Configurar usuário não-root (UID 1000 exigido pelo Hugging Face Spaces)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Copiar arquivos de dependências com permissão do usuário
COPY --chown=user:user pyproject.toml uv.lock ./

# Instalar dependências Python do projeto
RUN uv sync --frozen --no-dev

# Copiar código-fonte, dados e modelos
COPY --chown=user:user src/ src/
COPY --chown=user:user data/ data/
COPY --chown=user:user pipeline.py pipeline.py

# Porta padrão do Hugging Face Spaces: 7860
ENV PORT=7860
EXPOSE 7860

# Inicializar o servidor FastAPI com Uvicorn
CMD ["sh", "-c", "uv run uvicorn nfl_odds.dashboard.api:app --host 0.0.0.0 --port ${PORT:-7860}"]
