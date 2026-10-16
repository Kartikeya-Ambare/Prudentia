"""FastAPI app: POST /api/chat, GET /api/chat/health.  Run: uvicorn chat_service.main:app --port 8001"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from chat_service.config import get_config
from chat_service.llm.ollama import health as ollama_health
from chat_service.pipeline import ChatPipeline
from chat_service.schemas import ChatRequest, ChatResponse
from chat_service.session import RateLimited

logger = logging.getLogger(__name__)


def create_app(pipeline: Optional[ChatPipeline] = None, cfg=None) -> FastAPI:
    cfg = cfg or get_config()
    app = FastAPI(title="Prudentia Chat", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=list(cfg.service.allowed_origins),
                       allow_methods=["GET", "POST"], allow_headers=["*"])
    state: dict = {"pipeline": pipeline}
    if pipeline is None and cfg.engine.mode == "http":              # the real thing: load the model now, not on the first message
        import threading
        from chat_service.llm.ollama import warm_up
        threading.Thread(target=warm_up, args=(cfg.chat.ollama_host, cfg.chat.intent_model), name="model-warm-up", daemon=True).start()

    def pipe() -> ChatPipeline:
        if state["pipeline"] is None:
            state["pipeline"] = ChatPipeline(cfg)
        return state["pipeline"]

    @app.post("/api/chat", response_model=ChatResponse, response_model_exclude_none=True)
    def chat(req: ChatRequest):
        try:
            return pipe().handle(req.session_id, req.message, req.profile_id)
        except RateLimited:
            return JSONResponse(status_code=429, content={"detail": "Too many messages: max 1 per second per session."})
        except Exception:                                   # never leak internals to the browser
            logger.exception("chat pipeline error")
            return JSONResponse(status_code=500, content={"detail": "Chat service error."})

    @app.get("/api/chat/health")
    def chat_health():
        c = cfg.chat
        wanted = sorted({c.intent_model, getattr(c, "judge_model", c.intent_model), c.explain_model})
        h = ollama_health(c.ollama_host, wanted)
        h["engine_mode"] = cfg.engine.mode
        h["ok"] = h["ollama_reachable"] and all(h["models"].values())
        return h

    return app


app = create_app()
