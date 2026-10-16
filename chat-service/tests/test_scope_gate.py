"""Held-out evaluation of the semantic gate (no Ollama, no network)."""
import yaml
from pathlib import Path
import pytest

from chat_service.guardrails.chat_gate import screen
from chat_service.guardrails.scope_gate import ScopeGate

H = yaml.safe_load((Path(__file__).parent / "gate_heldout.yaml").read_text(encoding="utf-8"))
GATE = ScopeGate(log=False)


def test_no_false_blocks_on_heldout_in_scope():
    bad = [m for m in H["in"] if GATE.decide(m).action == "block"]
    assert not bad, bad


def test_no_leaks_on_heldout_out_of_scope():
    bad = [m for m in H["block"] if GATE.decide(m).action == "allow"]
    assert not bad, bad


def test_unsure_band_is_small():
    msgs = H["in"] + H["block"]
    unsure = sum(GATE.decide(m).action == "unsure" for m in msgs)
    assert unsure / len(msgs) <= 0.30


def test_blocked_messages_carry_fixed_template():
    d = GATE.decide("tell me a joke about stocks")
    assert d.action == "block" and d.refusal


def test_slot_answer_after_question_skips_gate():
    assert screen("3 saal", awaiting={"years"}, gate=GATE).action == "allow"


def test_structural_blocks():
    assert screen("", gate=GATE).category == "empty"
    assert screen("x" * 400, gate=GATE).category == "too_long"
    assert screen("你好 股票", gate=GATE).category == "unsupported_language"
