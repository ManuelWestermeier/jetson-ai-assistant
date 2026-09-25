"""
Persistentes Gedächtnis: Konversationsverlauf + Langzeit-Fakten mit
semantischer Suche über Ollama-Embeddings (nomic-embed-text).
"""

import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Optional

import httpx

DB_PATH = Path(__file__).parent.parent / "data" / "app.db"
OLLAMA_URL = "http://127.0.0.1:11434"
EMBED_MODEL = "nomic-embed-text"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at REAL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        );

        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            embedding TEXT NOT NULL,
            created_at REAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
        """
    )
    conn.commit()
    conn.close()


async def embed(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
        )
        r.raise_for_status()
        return r.json()["embedding"]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def ensure_conversation(conversation_id: str) -> None:
    conn = _connect()
    conn.execute(
        "INSERT OR IGNORE INTO conversations (id, title, created_at) VALUES (?, ?, ?)",
        (conversation_id, "Neue Unterhaltung", time.time()),
    )
    conn.commit()
    conn.close()


def add_message(conversation_id: str, role: str, content: str) -> None:
    conn = _connect()
    conn.execute(
        "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (conversation_id, role, content, time.time()),
    )
    conn.commit()
    conn.close()


def get_history(conversation_id: str, limit: int = 40) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE conversation_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (conversation_id, limit),
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def list_conversations() -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT id, title, created_at FROM conversations ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


async def remember(fact: str) -> None:
    vec = await embed(fact)
    conn = _connect()
    conn.execute(
        "INSERT INTO memories (content, embedding, created_at) VALUES (?, ?, ?)",
        (fact, json.dumps(vec), time.time()),
    )
    conn.commit()
    conn.close()


async def recall(query: str, top_k: int = 5) -> list[str]:
    conn = _connect()
    rows = conn.execute("SELECT content, embedding FROM memories").fetchall()
    conn.close()
    if not rows:
        return []
    qvec = await embed(query)
    scored = [
        (_cosine(qvec, json.loads(r["embedding"])), r["content"]) for r in rows
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for score, c in scored[:top_k] if score > 0.5]
