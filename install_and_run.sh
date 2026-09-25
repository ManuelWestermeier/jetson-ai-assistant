#!/usr/bin/env bash
#
# install_and_run.sh
# Ein-Datei-Setup + Start für den lokalen Jetson-KI-Assistenten.
# Installiert Ollama, Python-Abhängigkeiten und Playwright-Chromium,
# lädt Modelle herunter und startet den Server auf http://0.0.0.0:8000.
#
# Aufruf: bash install_and_run.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
LLM_MODEL="${LLM_MODEL:-qwen3:4b}"
EMBED_MODEL="nomic-embed-text"
PORT="${PORT:-8000}"

log() { echo -e "\033[1;36m[setup]\033[0m $1"; }
err() { echo -e "\033[1;31m[fehler]\033[0m $1" >&2; }

# ---------------------------------------------------------------------------
# 1. Systempakete
# ---------------------------------------------------------------------------
log "Prüfe Systempakete (python3, venv, curl)…"
if ! command -v python3 >/dev/null 2>&1 || ! python3 -m venv --help >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-venv python3-pip curl
fi
if ! command -v curl >/dev/null 2>&1; then
    sudo apt-get install -y curl
fi

# ---------------------------------------------------------------------------
# 2. Ollama installieren (falls nicht vorhanden) und als Dienst starten
# ---------------------------------------------------------------------------
if ! command -v ollama >/dev/null 2>&1; then
    log "Installiere Ollama…"
    curl -fsSL https://ollama.com/install.sh | sh
else
    log "Ollama bereits installiert."
fi

if ! pgrep -x "ollama" >/dev/null 2>&1; then
    log "Starte Ollama-Dienst im Hintergrund…"
    nohup ollama serve > "$SCRIPT_DIR/ollama.log" 2>&1 &
    sleep 4
fi

log "Warte auf Ollama-API…"
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

# ---------------------------------------------------------------------------
# 3. Modelle laden
# ---------------------------------------------------------------------------
log "Lade LLM '$LLM_MODEL' (kann beim ersten Mal einige Minuten dauern)…"
ollama pull "$LLM_MODEL"

log "Lade Embedding-Modell '$EMBED_MODEL'…"
ollama pull "$EMBED_MODEL"

# ---------------------------------------------------------------------------
# 4. Python-Umgebung
# ---------------------------------------------------------------------------
if [ ! -d "$VENV_DIR" ]; then
    log "Erstelle virtuelle Umgebung…"
    python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

log "Installiere Python-Abhängigkeiten…"
pip install --upgrade pip -q
pip install -r "$SCRIPT_DIR/server/requirements.txt" -q

log "Installiere Playwright-Chromium + Systemabhängigkeiten (benötigt sudo)…"
python -m playwright install --with-deps chromium

# ---------------------------------------------------------------------------
# 5. Server starten
# ---------------------------------------------------------------------------
mkdir -p "$SCRIPT_DIR/data"
IP_ADDR="$(hostname -I 2>/dev/null | awk '{print $1}')"

log "Starte Server…"
log "Erreichbar unter: http://localhost:${PORT}  (im lokalen Netz: http://${IP_ADDR:-<jetson-ip>}:${PORT})"

export LLM_MODEL
cd "$SCRIPT_DIR/server"
exec python -m uvicorn app:app --host 0.0.0.0 --port "$PORT"
