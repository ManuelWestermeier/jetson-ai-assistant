"""
Tool-Implementierungen, die das LLM per Function-Calling aufrufen kann:
Websuche (DuckDuckGo), Headless-Browser (Playwright) und Langzeit-Gedächtnis.
"""

import asyncio
import json

from ddgs import DDGS
from playwright.async_api import async_playwright

import memory

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Durchsucht das Web nach aktuellen Informationen. Nutzen bei "
                "Fragen zu aktuellen Ereignissen, Fakten nach dem Trainingsstand "
                "oder wenn Unsicherheit besteht."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Suchanfrage"},
                    "max_results": {
                        "type": "integer",
                        "description": "Anzahl Ergebnisse (Standard 5)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browse_page",
            "description": (
                "Ruft eine konkrete URL mit einem echten (headless) Browser auf, "
                "rendert JavaScript und gibt den sichtbaren Textinhalt zurück. "
                "Nutzen, um einen Treffer aus web_search im Detail zu lesen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Vollständige URL"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": (
                "Speichert eine Tatsache dauerhaft im Langzeit-Gedächtnis, damit "
                "sie in zukünftigen Unterhaltungen abrufbar ist. Nutzen, wenn der "
                "Nutzer explizit etwas gemerkt haben will oder eine wichtige, "
                "dauerhafte Information teilt."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {"type": "string", "description": "Zu speichernder Fakt, in einem klaren, eigenständigen Satz"},
                },
                "required": ["fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": (
                "Durchsucht das Langzeit-Gedächtnis nach relevanten, früher "
                "gespeicherten Fakten zu einem Thema."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Wonach gesucht werden soll"},
                },
                "required": ["query"],
            },
        },
    },
]


async def _web_search(query: str, max_results: int = 5) -> str:
    def _sync_search():
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))

    results = await asyncio.to_thread(_sync_search)
    if not results:
        return "Keine Ergebnisse gefunden."
    lines = []
    for r in results:
        lines.append(f"- {r.get('title')}\n  URL: {r.get('href')}\n  {r.get('body')}")
    return "\n".join(lines)


async def _browse_page(url: str, max_chars: int = 6000) -> str:
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            page = await browser.new_page()
            await page.goto(url, timeout=25000, wait_until="domcontentloaded")
            text = await page.inner_text("body")
            await browser.close()
            text = " ".join(text.split())
            if len(text) > max_chars:
                text = text[:max_chars] + " …[gekürzt]"
            return text or "Seite hat keinen lesbaren Textinhalt geliefert."
    except Exception as e:
        return f"Fehler beim Laden der Seite: {e}"


async def execute_tool(name: str, arguments: dict) -> str:
    try:
        if name == "web_search":
            return await _web_search(
                arguments.get("query", ""), int(arguments.get("max_results", 5) or 5)
            )
        if name == "browse_page":
            return await _browse_page(arguments.get("url", ""))
        if name == "remember":
            fact = arguments.get("fact", "")
            if not fact:
                return "Kein Fakt übergeben."
            await memory.remember(fact)
            return f"Gespeichert: {fact}"
        if name == "recall":
            facts = await memory.recall(arguments.get("query", ""))
            if not facts:
                return "Keine passenden Erinnerungen gefunden."
            return "\n".join(f"- {f}" for f in facts)
        return f"Unbekanntes Tool: {name}"
    except Exception as e:
        return f"Fehler bei Tool '{name}': {e}"


def parse_tool_arguments(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}
