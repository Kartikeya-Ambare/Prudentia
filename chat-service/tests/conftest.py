import json

import pytest

from chat_service.config import load_config
from chat_service.engine.fake import FakeEngine
from chat_service.guardrails.scope_gate import ScopeGate
from chat_service.pipeline import ChatPipeline
from chat_service.session import SessionStore

GATE = ScopeGate(log=False)


class ScriptedLLM:
    """Stands in for Ollama. Records every call; role is inferred from the schema."""

    def __init__(self, intent="provide_inputs", fund=None, slots=None, judge="off_topic", forbid=False):
        self.intent, self.fund, self.slots, self.judge, self.forbid = intent, fund, slots, judge, forbid
        self.calls = []

    def __call__(self, model, system, user, schema):
        if self.forbid:
            raise AssertionError(f"model was called: {system[:40]!r} / {user!r}")
        self.calls.append((system, user))
        props = schema["properties"]
        if "intent" in props:
            intent = self.intent(user) if callable(self.intent) else self.intent
            return json.dumps({"intent": intent, "fund_name": self.fund})
        if "label" in props:
            return json.dumps({"label": self.judge})
        base = {"amount": None, "years": None, "risk": None, "classes": None, "remove_classes": None, "risk_shift": None}
        base.update(self.slots or {})
        return json.dumps(base)


@pytest.fixture
def cfg():
    c = load_config()
    c.chat.min_interval_seconds = 0
    return c


@pytest.fixture
def make_pipe(cfg):
    def make(llm=None, engine=None, text_fn=None, polish=False, **kw):
        cfg.chat.polish = polish
        store = SessionStore(cfg.chat.session_ttl_minutes, cfg.chat.max_turns, 0)
        return ChatPipeline(cfg, engine=engine or FakeEngine(), chat_fn=llm or ScriptedLLM(), text_fn=text_fn,
                            gate=GATE, store=store, **kw)
    return make
