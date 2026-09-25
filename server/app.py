"""
Lokaler KI-Assistent für Jetson Orin Nano.
FastAPI-Server: dient die Chat-UI aus, orchestriert Ollama (LLM) mit
Tool-Calling (Websuche, Headless-Browser, Gedächtnis) und persistiert
Verlauf + Langzeit-Fakten in SQLite.
"""

import json
import os
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import memory
import tools

OLLAMA_URL = "http://127.0.0.1:11434"
MODEL = os.environ.get("LLM_MODEL", "qwen3:4b")
MAX_TOOL_ITERATIONS = 5

SYSTEM_PROMPT = (
    "Du bist ein hilfreicher, lokal auf einem Jetson Orin Nano laufender "
    "KI-Assistent. Du hast Zugriff auf Websuche, einen Headless-Browser und "
    "ein Langzeit-Gedächtnis über Tools. Nutze web_search für aktuelle oder "
    "unsichere Fakten, browse_page um eine konkrete Seite im Detail zu lesen, "
    "remember um dir wichtige, dauerhafte Informationen über den Nutzer zu "
    "merken, und recall um vorher gemerkte Informationen abzurufen. Antworte "
    "prägnant, korrekt und auf Deutsch, außer der Nutzer schreibt in einer "
    "anderen Sprache."
)

app = FastAPI(title="Jetson Local AI Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = Path(__file__).parent.parent / "web"


@app.on_event("startup")
async def on_startup():
    memory.init_db()


@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str


@app.get("/api/conversations")
async def api_list_conversations():
    return memory.list_conversations()


@app.get("/api/conversations/{conversation_id}")
async def api_get_conversation(conversation_id: str):
    return memory.get_history(conversation_id, limit=500)


async def _ollama_chat_once(messages: list[dict], use_tools: bool) -> dict:
    payload = {"model": MODEL, "messages": messages, "stream": False}
    if use_tools:
        payload["tools"] = tools.TOOL_DEFINITIONS
    async with httpx.AsyncClient(timeout=300.0) as client:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        r.raise_for_status()
        return r.json()


async def _ollama_chat_stream(messages: list[dict]):
    payload = {"model": MODEL, "messages": messages, "stream": True}
    async with httpx.AsyncClient(timeout=300.0) as client:
        async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=payload) as r:
            async for line in r.aiter_lines():
                if line.strip():
                    yield json.loads(line)


async def _run_agent_loop(conversation_id: str, user_message: str):
    memory.ensure_conversation(conversation_id)
    memory.add_message(conversation_id, "user", user_message)

    history = memory.get_history(conversation_id, limit=40)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    tool_trace = []

    for _ in range(MAX_TOOL_ITERATIONS):
        result = await _ollama_chat_once(messages, use_tools=True)
        msg = result.get("message", {})
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            break

        messages.append(msg)
        for call in tool_calls:
            fn = call.get("function", {})
            name = fn.get("name")
            args = tools.parse_tool_arguments(fn.get("arguments", {}))
            yield {"type": "tool_call", "name": name, "arguments": args}
            tool_result = await tools.execute_tool(name, args)
            tool_trace.append({"name": name, "arguments": args, "result": tool_result})
            yield {"type": "tool_result", "name": name, "result": tool_result}
            messages.append(
                {"role": "tool", "content": tool_result, "name": name or ""}
            )
    else:
        yield {"type": "info", "text": "Maximale Anzahl an Tool-Aufrufen erreicht."}

    full_text = ""
    async for chunk in _ollama_chat_stream(messages):
        piece = chunk.get("message", {}).get("content", "")
        if piece:
            full_text += piece
            yield {"type": "token", "text": piece}
        if chunk.get("done"):
            break

    memory.add_message(conversation_id, "assistant", full_text)
    yield {"type": "done"}


@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    conversation_id = req.conversation_id or str(uuid.uuid4())

    async def event_stream():
        yield f"data: {json.dumps({'type': 'conversation_id', 'id': conversation_id})}\n\n"
        async for event in _run_agent_loop(conversation_id, req.message):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
