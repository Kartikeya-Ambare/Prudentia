from chat_service.engine.client import EngineClient, EngineError, EngineUnavailable
from chat_service.engine.fake import FakeEngine
from chat_service.engine.http import HttpEngine


def make_engine(cfg) -> EngineClient:
    """engine.mode in config.yaml picks the implementation. Default: fake."""
    if str(cfg.engine.mode).lower() == "http":
        return HttpEngine(cfg.engine.base_url, timeout=float(getattr(cfg.engine, "timeout_seconds", 60)))
    return FakeEngine()


__all__ = ["EngineClient", "EngineError", "EngineUnavailable", "FakeEngine", "HttpEngine", "make_engine"]
