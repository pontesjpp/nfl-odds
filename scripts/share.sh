#!/usr/bin/env bash
set -e

echo "========================================================"
echo "🏈 NFL ODDS - Compartilhar com Amigos (Túnel HTTPS Seguro)"
echo "========================================================"

# Diretório raiz do projeto
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# 1. Garantir que o binário do cloudflared existe
CLOUDFLARED_BIN="$HOME/.local/bin/cloudflared"
if [ ! -f "$CLOUDFLARED_BIN" ]; then
    echo "-> Baixando Cloudflare Tunnel (gratuito e sem cadastro)..."
    mkdir -p "$HOME/.local/bin"
    curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o "$CLOUDFLARED_BIN"
    chmod +x "$CLOUDFLARED_BIN"
fi

# Função de limpeza ao sair (Ctrl+C)
cleanup() {
    echo ""
    echo "-> Encerrando servidores e túnel..."
    if [ -n "$BACK_PID" ]; then kill "$BACK_PID" 2>/dev/null || true; fi
    if [ -n "$FRONT_PID" ]; then kill "$FRONT_PID" 2>/dev/null || true; fi
    if [ -n "$TUNNEL_PID" ]; then kill "$TUNNEL_PID" 2>/dev/null || true; fi
    echo "✓ Tudo finalizado com sucesso."
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 2. Iniciar Back-end FastAPI se não estiver rodando
if ! ss -tulpn 2>/dev/null | grep -q ":8000 "; then
    echo "-> [1/3] Iniciando Back-end (FastAPI :8000)..."
    uv run uvicorn nfl_odds.dashboard.api:app --port 8000 > /tmp/nfl_backend.log 2>&1 &
    BACK_PID=$!
    sleep 2
else
    echo "-> [1/3] Back-end já ativo na porta 8000."
fi

# 3. Iniciar Front-end Next.js se não estiver rodando
if ! ss -tulpn 2>/dev/null | grep -q ":3000 "; then
    echo "-> [2/3] Iniciando Front-end (Next.js :3000)..."
    (cd frontend && npm run dev > /tmp/nfl_frontend.log 2>&1) &
    FRONT_PID=$!
    sleep 3
else
    echo "-> [2/3] Front-end já ativo na porta 3000."
fi

# 4. Criar o Túnel HTTPS com Cloudflare
echo "-> [3/3] Gerando link público HTTPS para seus amigos..."
echo ""
echo "========================================================"
echo "Aguarde o link oficial abaixo (termina em .trycloudflare.com):"
echo "Envie esse link no WhatsApp/Telegram para seus amigos!"
echo "Pressione Ctrl+C para encerrar quando quiser."
echo "========================================================"
echo ""

"$CLOUDFLARED_BIN" tunnel --protocol http2 --http-host-header localhost:3000 --url http://localhost:3000
