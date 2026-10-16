"""Ollama access. Every call is schema-constrained (`format=<JSON schema>`), temperature 0, thinking off.

chat_fn(model, system, user, schema) -> raw JSON text. It is injected everywhere so tests need no Ollama.
"""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

KEEP_ALIVE = "30m"          # keep the model loaded between messages (Ollama unloads after 5 idle minutes by default)
ChatFn = Callable[[str, str, str, dict], str]
TextFn = Callable[[str, str], str]          # (model, prompt) -> text; used only by the optional polish


def make_chat_fn(host: str, timeout: float = 60.0) -> ChatFn:
    def call(model: str, system: str, user: str, schema: dict) -> str:
        import ollama
        r = ollama.Client(host=host, timeout=timeout).chat(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            format=schema, options={"temperature": 0.0, "num_ctx": 2048}, think=False, keep_alive=KEEP_ALIVE,
        )
        return r.message.content
    return call


def warm_up(host: str, model: str) -> None:
    """Load the model into memory so the first real message is not slow. Never raises (Ollama may be down)."""
    try:
        import ollama
        ollama.Client(host=host, timeout=120).chat(model=model, messages=[{"role": "user", "content": "hi"}],
                                                   options={"num_predict": 1}, keep_alive=KEEP_ALIVE)
    except Exception as exc:
        logger.info("model warm-up skipped: %s", exc)


def make_text_fn(host: str, timeout: float = 60.0) -> TextFn:
    def call(model: str, prompt: str) -> str:
        import ollama
        r = ollama.Client(host=host, timeout=timeout).generate(
            model=model, prompt=prompt, options={"temperature": 0.0, "num_ctx": 2048}, think=False, keep_alive=KEEP_ALIVE)
        return r.response.strip()
    return call


def health(host: str, models: list[str]) -> dict:
    """{'ollama_reachable': bool, 'models': {name: present}}"""
    try:
        import ollama
        have = {m.model for m in ollama.Client(host=host, timeout=5).list().models}
    except Exception as exc:
        logger.info("ollama health check failed: %s", exc)
        return {"ollama_reachable": False, "models": {m: False for m in models}}
    return {"ollama_reachable": True,
            "models": {m: (m in have or f"{m}:latest" in have) for m in models}}
