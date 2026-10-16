"""Semantic scope gate: decides, BEFORE any LLM call, whether a message is worth sending to the LLM.

Design (same idea as Anthropic's constitutional classifiers, scaled down):
  * The policy lives in DATA (scope_policy.yaml: a purpose statement + labelled examples), not in code.
  * A small, fast, trained classifier reads the message and outputs a class + probability.
  * Confident 'in'  -> ALLOW  (goes on to the intent LLM)
    Confident other -> BLOCK  (fixed refusal template for that class, zero LLM calls)
    Not confident   -> UNSURE (goes to the intent LLM, which has an out_of_scope option)
  * New behaviour = add examples to the YAML and retrain (seconds). No regex/keyword edits.
  * Blocked/unsure messages are appended to a JSONL log so you can label them and grow the policy.

Backends: 'tfidf' (default; char n-grams, so Hinglish spellings work; no downloads, no Ollama)
          'ollama' (embeddings via Ollama + logistic regression; same interface, optional upgrade)
Format-level checks (empty, too long, invisible chars) are structural, not topical, and live in chat_guardrails.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

HERE = Path(__file__).parent
POLICY_PATH = HERE / "scope_policy.yaml"
MODEL_PATH = HERE / "scope_gate.joblib"
LOG_PATH = HERE.parents[1] / "data" / "gate_log.jsonl"   # <chat root>/data

ALLOW_T = 0.70   # P(in) needed to allow without asking anything else
BLOCK_T = 0.60   # P(top non-in class) needed to block outright


@dataclass
class GateDecision:
    action: str            # "allow" | "block" | "unsure"
    label: str             # predicted class
    confidence: float
    refusal: str | None    # fixed template when action == "block"
    probs: dict


def load_policy(path: Path = POLICY_PATH) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _build_pipeline() -> Pipeline:
    feats = FeatureUnion([
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=1)),
        ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True, token_pattern=r"(?u)\b\w+\b")),
    ])
    return Pipeline([("f", feats), ("clf", LogisticRegression(C=20, max_iter=2000, class_weight="balanced"))])


def train(policy_path: Path = POLICY_PATH, model_path: Path = MODEL_PATH):
    policy = load_policy(policy_path)
    X, y = [], []
    for label, rows in policy["examples"].items():
        for r in rows:
            X.append(_norm(str(r)))
            y.append(label)
    pipe = _build_pipeline().fit(X, y)
    joblib.dump({"pipe": pipe, "templates": policy["refusal_templates"]}, model_path)
    return pipe


class ScopeGate:
    def __init__(self, model_path: Path = MODEL_PATH, log: bool = True):
        if not Path(model_path).exists():
            train(model_path=model_path)
        blob = joblib.load(model_path)
        self.pipe, self.log = blob["pipe"], log
        self.templates = load_policy()["refusal_templates"]     # wording lives in the YAML, so it can change without retraining

    def decide(self, message: str) -> GateDecision:
        p = self.pipe.predict_proba([_norm(message)])[0]
        classes = list(self.pipe.classes_)
        probs = {c: float(v) for c, v in zip(classes, p)}
        top = max(probs, key=probs.get)
        if top == "in" and probs["in"] >= ALLOW_T:
            d = GateDecision("allow", "in", probs["in"], None, probs)
        elif top != "in" and probs[top] >= BLOCK_T:
            d = GateDecision("block", top, probs[top], self.templates[top], probs)
        else:
            d = GateDecision("unsure", top, probs[top], None, probs)
        if self.log and d.action != "allow":
            self._log(message, d)
        return d

    def _log(self, message: str, d: GateDecision) -> None:
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"t": time.time(), "message": message[:300], "action": d.action,
                                    "label": d.label, "conf": round(d.confidence, 3)}, ensure_ascii=False) + "\n")
        except OSError:
            pass


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "train":
        train(); print("trained ->", MODEL_PATH)
    else:
        g = ScopeGate(log=False)
        for line in sys.argv[1:]:
            d = g.decide(line); print(f"{d.action:7} {d.label:16} {d.confidence:.2f}  {line}")
