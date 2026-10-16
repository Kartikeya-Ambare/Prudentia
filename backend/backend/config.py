"""Loads config.yaml, substituting ${VAR} placeholders from the environment/.env.

Every other module imports `get_config()` instead of parsing config.yaml itself,
so there is exactly one place that knows about the file's location and the
${VAR} substitution rule.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


class ConfigNode:
    """Thin attribute-access wrapper over a nested dict, read-only."""

    def __init__(self, data: dict):
        object.__setattr__(self, "_data", data)

    def __getattr__(self, name: str) -> Any:
        try:
            value = self._data[name]
        except KeyError as exc:
            raise AttributeError(f"No config key '{name}'") from exc
        if isinstance(value, dict):
            return ConfigNode(value)
        return value

    def __getitem__(self, name: str) -> Any:
        return self.__getattr__(name)

    def get(self, name: str, default: Any = None) -> Any:
        try:
            return self.__getattr__(name)
        except AttributeError:
            return default

    def to_dict(self) -> dict:
        return self._data

    def __repr__(self) -> str:
        return f"ConfigNode({self._data!r})"


def _substitute_env(value: Any) -> Any:
    if isinstance(value, str):
        def repl(m: re.Match) -> str:
            return os.environ.get(m.group(1), "")
        return _VAR_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


@lru_cache(maxsize=1)
def get_config(config_path: str | Path | None = None) -> ConfigNode:
    load_dotenv(REPO_ROOT / ".env")
    path = Path(config_path) if config_path else REPO_ROOT / "config.yaml"
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return ConfigNode(_substitute_env(raw))


def repo_path(*parts: str) -> Path:
    """Resolve a path relative to the repo root, so scripts work regardless of cwd."""
    return REPO_ROOT.joinpath(*parts)
