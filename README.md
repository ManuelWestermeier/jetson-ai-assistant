# Jetson Orin Nano — Lokaler KI-Assistent

Vollständig lokaler Chat-Assistent für Jetson Orin Nano (8 GB), mit:

- **LLM:** `qwen3:4b` über [Ollama](https://ollama.com) (austauschbar via `LLM_MODEL`)
- **Websuche:** DuckDuckGo (`ddgs`), keine API-Keys nötig
- **Headless-Browser:** Playwright/Chromium — rendert JS, liest Seiteninhalt
- **Gedächtnis:** SQLite (Verlauf) + Langzeit-Fakten mit Embedding-Suche (`nomic-embed-text`)
- **UI:** Eigenständige Chat-Oberfläche mit Streaming, im Browser unter `http://<jetson-ip>:8000`

## Nutzung

```bash
unzip jetson-ai-assistant.zip
cd jetson-ai-assistant
bash install_and_run.sh
```

Das Skript ist idempotent — erneuter Aufruf installiert nichts doppelt und startet nur neu.

Danach im Browser öffnen: `http://<jetson-ip>:8000` (IP wird beim Start ausgegeben).

## Konfiguration

| Variable     | Standard     | Bedeutung                          |
|--------------|--------------|-------------------------------------|
| `LLM_MODEL`  | `qwen3:4b`   | Ollama-Modellname für das Chat-LLM  |
| `PORT`       | `8000`       | Port des Web-Servers                |

Beispiel mit anderem Modell:

```bash
LLM_MODEL=gemma3:4b bash install_and_run.sh
```

## Architektur

```
Browser (UI, SSE-Streaming)
   │  HTTP
   ▼
FastAPI-Server (server/app.py)
   │  Agent-Loop: bis zu 5 Tool-Iterationen pro Anfrage
   ├─→ Ollama (127.0.0.1:11434) — LLM + Embeddings
   ├─→ tools.py → DuckDuckGo-Suche, Playwright-Browser
   └─→ memory.py → SQLite (data/app.db): Verlauf + Langzeit-Fakten
```

## Hinweise für den Jetson

- GPU-Beschleunigung durch Ollama hängt von der installierten Ollama-Version ab;
  ohne CUDA-Unterstützung läuft das 4B-Modell auf der CPU spürbar langsamer,
  bleibt aber nutzbar.
- Playwright-Chromium benötigt beim ersten Start `--with-deps` (im Skript enthalten),
  das zieht diverse `apt`-Pakete nach — Internetzugang während der Installation nötig.
- Persistente Daten liegen in `data/app.db` — vor Neuinstallation sichern, falls
  das Gedächtnis erhalten bleiben soll.
- Dienst dauerhaft laufen lassen: `install_and_run.sh` als systemd-Unit oder in
  `tmux`/`screen` starten, statt es im Vordergrund zu belassen.

## Tools, die das LLM aufrufen kann

| Tool          | Zweck                                                    |
|---------------|-----------------------------------------------------------|
| `web_search`  | Aktuelle Informationen aus dem Web holen                  |
| `browse_page` | Konkrete URL mit Headless-Browser laden und Text lesen    |
| `remember`    | Fakt dauerhaft im Langzeit-Gedächtnis speichern            |
| `recall`      | Gespeicherte Fakten zu einem Thema abrufen                 |
