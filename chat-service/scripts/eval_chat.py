"""Run the REAL pipeline (real Ollama, FakeEngine) over an eval file and report.

  python -m scripts.eval_chat                                  # dev set (tests/eval_prompts.jsonl), full pipeline
  python -m scripts.eval_chat --file tests/eval_heldout.jsonl
  python -m scripts.eval_chat --mode raw|gate|full             # ablation arm
  python -m scripts.eval_chat --ablation                       # all three arms on dev + held-out

Modes: raw  = no gate, no judge (every message goes straight to the intent LLM; its 'unsupported' label counts as a block)
       gate = trained gate only (unsure goes on to the intent LLM)
       full = gate + LLM policy judge on unsure (the shipped pipeline)

Metrics (per file):
  false-block rate = expected allow but blocked          leak rate = expected block but answered
  unsure rate      = gate unsure (judge asked in `full`)   intent acc. = response intent == expected (allow cases)
  slot acc.        = every expected slot present in response params
  latency p50/p95  = seconds per scored message (setup turns not counted)
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

from chat_service.config import load_config
from chat_service.engine.fake import FakeEngine
from chat_service.guardrails.scope_gate import ScopeGate
from chat_service.llm.ollama import make_chat_fn
from chat_service.pipeline import ChatPipeline
from chat_service.session import SessionStore

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "tests" / "eval_prompts.jsonl"
HELD = ROOT / "tests" / "eval_heldout.jsonl"
HELD2 = ROOT / "tests" / "eval_heldout2.jsonl"
HELD3 = ROOT / "tests" / "eval_heldout3.jsonl"


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def make_pipeline(mode: str, cfg, gate: ScopeGate) -> ChatPipeline:
    chat_fn = make_chat_fn(cfg.chat.ollama_host, cfg.chat.request_timeout_seconds)
    store = SessionStore(cfg.chat.session_ttl_minutes, 10_000, 0)
    return ChatPipeline(cfg, engine=FakeEngine(), chat_fn=chat_fn, gate=gate, store=store,
                        use_gate=mode != "raw", use_judge=mode == "full")


def slots_ok(expected: dict, params: dict) -> bool:
    for k, v in expected.items():
        got = params.get(k)
        if k == "classes":
            if sorted(got or []) != sorted(v):
                return False
        elif got != v:
            return False
    return True


def run(path: Path, mode: str, cfg, gate: ScopeGate, verbose: bool = True) -> tuple[dict, list[dict]]:
    pipe = make_pipeline(mode, cfg, gate)
    rows, lat = [], []
    for i, case in enumerate(load(path)):
        sid = f"{path.stem}-{mode}-{i}"
        for m in case.get("setup", []):
            pipe.handle(sid, m)
        t0 = time.perf_counter()
        resp, tr = pipe.handle_traced(sid, case["message"])
        dt = time.perf_counter() - t0
        lat.append(dt)
        blocked = bool(resp.get("blocked"))
        exp_allow = case["expected_action"] == "allow"
        row = {
            "message": case["message"], "category": case["category"], "expected_action": case["expected_action"],
            "expected_intent": case["expected_intent"], "got_intent": resp["intent"], "blocked": blocked,
            "block_category": resp.get("category") or "", "gate_action": tr.gate or "", "path": tr.path,
            "llm_calls": len(tr.calls), "judge_called": any(c["role"] == "judge" for c in tr.calls),
            "harmless": (not blocked) and resp.get("result") is None and resp["intent"] in ("clarify", "provide_inputs", "rebalance"),
            "false_block": exp_allow and blocked, "leak": (not exp_allow) and not blocked,
            "intent_ok": (resp["intent"] == case["expected_intent"]) if exp_allow else "",
            "slots_ok": slots_ok(case["expected_slots"], resp.get("params", {})) if "expected_slots" in case else "",
            "seconds": round(dt, 2), "reply": resp["reply"].replace("\n", " | ")[:200],
        }
        rows.append(row)
        if verbose and (row["false_block"] or row["leak"] or row["intent_ok"] is False or row["slots_ok"] is False):
            tag = "FALSE-BLOCK" if row["false_block"] else "LEAK" if row["leak"] else \
                "BAD-INTENT" if row["intent_ok"] is False else "BAD-SLOTS"
            print(f"  [{tag}] ({row['category']}) {case['message']!r} -> {row['got_intent']} {row['path']} {row['block_category']}",
                  file=sys.stderr)
    return summarise(rows, lat), rows


def pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else float("nan")


def wilson(k: int, n: int, z: float = 1.96) -> str:
    """95% Wilson interval for k/n, as 'lo-hi' percent."""
    if n == 0:
        return "n/a"
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return f"{100 * max(0, c - h):.1f}-{100 * min(1, c + h):.1f}"


def summarise(rows: list[dict], lat: list[float]) -> dict:
    allow = [r for r in rows if r["expected_action"] == "allow"]
    block = [r for r in rows if r["expected_action"] == "block"]
    sl = [r for r in rows if r["slots_ok"] != ""]
    s = sorted(lat)
    return {
        "n": len(rows), "n_allow": len(allow), "n_block": len(block),
        "false_block_%": pct(sum(r["false_block"] for r in allow), len(allow)),
        "leak_%": pct(sum(r["leak"] for r in block), len(block)),
        "unsure_%": pct(sum(r["gate_action"] == "unsure" or r["judge_called"] for r in rows), len(rows)),
        "leak_harmless_%": pct(sum(r["leak"] and r["harmless"] for r in block), len(block)),
        "intent_acc_%": pct(sum(r["intent_ok"] is True for r in allow), len(allow)),
        "slot_acc_%": pct(sum(r["slots_ok"] is True for r in sl), len(sl)),
        "p50_s": round(statistics.median(s), 2), "p95_s": round(s[min(len(s) - 1, int(0.95 * len(s)))], 2),
        "false_block_95ci": wilson(sum(r["false_block"] for r in allow), len(allow)),
        "leak_95ci": wilson(sum(r["leak"] for r in block), len(block)),
        "intent_acc_95ci": wilson(sum(r["intent_ok"] is True for r in allow), len(allow)),
        "avg_llm_calls": round(sum(r["llm_calls"] for r in rows) / len(rows), 2),
    }


def write_csv(rows: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(DEV))
    ap.add_argument("--mode", default="full", choices=["raw", "gate", "full"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--ablation", action="store_true")
    ap.add_argument("--json", default=None, help="also dump summary JSON here")
    a = ap.parse_args()
    cfg = load_config()
    cfg.chat.min_interval_seconds = 0
    gate = ScopeGate(log=False)
    results = {}
    if a.ablation:
        for name, path in (("heldout3", HELD3), ("heldout2", HELD2), ("heldout1", HELD), ("dev", DEV)):
            for mode in ("raw", "gate", "full"):
                summ, rows = run(path, mode, cfg, gate, verbose=False)
                results[f"{name}/{mode}"] = summ
                write_csv(rows, ROOT / "data" / f"eval_{name}_{mode}.csv")
                print(f"{name:9}{mode:5} " + "  ".join(f"{k}={v}" for k, v in summ.items()), flush=True)
    else:
        path = Path(a.file)
        summ, rows = run(path, a.mode, cfg, gate)
        out = Path(a.out) if a.out else ROOT / "data" / f"eval_{path.stem}_{a.mode}.csv"
        write_csv(rows, out)
        results[f"{path.stem}/{a.mode}"] = summ
        print(json.dumps(summ, indent=2))
        print("saved", out)
    if a.json:
        Path(a.json).write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
