"""Loads config.yaml once. Model names, limits and engine mode live there, never in code."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"


def _ns(d):
    if isinstance(d, dict):
        return SimpleNamespace(**{k: _ns(v) for k, v in d.items()})
    return d


def load_config(path: Path = CONFIG_PATH) -> SimpleNamespace:
    cfg = _ns(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
    # deployment overrides without editing the file: CHAT_ENGINE_MODE=http, CHAT_ENGINE_URL=http://host:8000
    if os.environ.get("CHAT_ENGINE_MODE"):
        cfg.engine.mode = os.environ["CHAT_ENGINE_MODE"]
    if os.environ.get("CHAT_ENGINE_URL"):
        cfg.engine.base_url = os.environ["CHAT_ENGINE_URL"]
    if os.environ.get("CHAT_OLLAMA_HOST"):                      # e.g. http://ollama:11434 when Ollama runs in its own container
        cfg.chat.ollama_host = os.environ["CHAT_OLLAMA_HOST"]
    return cfg


@lru_cache(maxsize=1)
def get_config() -> SimpleNamespace:
    return load_config()
