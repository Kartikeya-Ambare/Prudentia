"""POST /api/chat pipeline.

 1. screen (structure -> injection -> slot answer -> trained scope gate -> LLM policy judge only if unsure; fail closed)
    blocked => fixed template, NO other model call
 2. deterministic shortcuts (confirm yes/no, risk-scenario answers, restore, glossary, rebalance-move rules)
 3. intent LLM (schema-constrained, user text only inside <user_message>)         [call 1]
 4. slots: rules first; slot LLM only if the rules found nothing                    [call 2]
    every LLM-extracted slot must be backed by the user's own words (slots_have_evidence), else clarify
 5. handlers build replies from engine results by template. Optional polish never sees user text.
"""
from __future__ import annotations

import copy
import logging
import re
import threading
from types import SimpleNamespace
from typing import Any, Optional

from chat_service import parse, prefs, replies
from chat_service.conflicts import find_conflict
from chat_service.config import get_config
from chat_service.engine.client import EngineClient, EngineError, EngineRejected, resolve_fund_name
from chat_service.guardrails.chat_gate import Screen, screen
from chat_service.guardrails.chat_guardrails import (
    MAX_CHARS, REFUSALS, _DOMAIN, _MONEY_CUE, _NON_LATIN, classes_in, normalise, reply_is_grounded, slots_have_evidence,
)
from chat_service.guardrails.policy_judge import PolicyJudge
from chat_service.guardrails.scope_gate import ScopeGate
from chat_service.llm import extract
from chat_service.llm.ollama import ChatFn, TextFn
from chat_service.session import Session, SessionStore

logger = logging.getLogger(__name__)

# words that tie a message to this app even when the shared _DOMAIN pattern misses them
_APP_CUE = re.compile(r"\b(plan|portfolio|risk|invest\w*|nivesh|paisa|paise|savings?|money|scenario|bear|bull|base\s+case|"
                      r"amount|allocation|stocks?|funds?|fds?|deposits?|banks?)\b", re.I)
_YES = re.compile(r"^(yes|y|haan|haa|han|ha|ok|okay|theek|thik|chalega|kar\s+do|karo|confirm|sure|done)\b[\w\s.!]{0,15}$", re.I)
_NO = re.compile(r"^(no|n|nahi|nahin|nhi|cancel|mat\s+karo|rehne\s+do|stop)\b[\w\s.!]{0,15}$", re.I)
_ALSO = re.compile(r"\b(also|too|as\s+well|bhi|same|again|similarly)\b", re.I)
_RESTORE = parse.RESTORE
_FUND_STOP = {"fund", "funds", "mutual", "mf", "scheme", "plan", "direct", "growth", "the"}
_SECTOR_ALIASES = {
    "Financial Services": ["financial", "financials", "banking", "finance", "bank", "banks"],
    "Information Technology": ["information technology", "it", "tech", "technology", "software"],
    "Healthcare": ["healthcare", "health", "pharma"], "Energy": ["energy", "oil"],
    "Automobile": ["automobile", "auto", "automotive"], "Consumer Goods": ["consumer goods", "fmcg", "consumer"],
    "Consumer Discretionary": ["consumer discretionary", "consumer"], "Industrials": ["industrials", "industrial"],
    "Materials": ["materials", "material"], "Others": ["others"],
}


class _Trace:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.gate: Optional[str] = None
        self.category: Optional[str] = None
        self.path: str = ""


class ChatPipeline:
    def __init__(self, cfg=None, engine: Optional[EngineClient] = None, chat_fn: Optional[ChatFn] = None,
                 text_fn: Optional[TextFn] = None, gate: Optional[ScopeGate] = None,
                 judge: Optional[PolicyJudge] = None, store: Optional[SessionStore] = None,
                 use_gate: bool = True, use_judge: bool = True):
        self.cfg = cfg or get_config()
        c = self.cfg.chat
        if engine is None:
            from chat_service.engine import make_engine
            engine = make_engine(self.cfg)
        self.engine = engine
        if chat_fn is None:
            from chat_service.llm.ollama import make_chat_fn
            chat_fn = make_chat_fn(c.ollama_host, c.request_timeout_seconds)
        self._raw_chat = chat_fn
        self.text_fn = text_fn
        self.use_gate, self.use_judge = use_gate, use_judge
        self.gate = gate
        self.judge = judge if judge is not None else PolicyJudge(
            getattr(c, "judge_model", None) or c.intent_model, c.ollama_host, chat_fn=self._chat)
        self.store = store or SessionStore(c.session_ttl_minutes, c.max_turns, getattr(c, "min_interval_seconds", 1.0))
        self._tl = threading.local()

    # ------------------------------------------------------------------ plumbing
    @property
    def trace(self) -> _Trace:
        t = getattr(self._tl, "t", None)
        if t is None:
            t = self._tl.t = _Trace()
        return t

    def _chat(self, model: str, system: str, user: str, schema: dict) -> str:
        role = "intent" if system is extract.INTENT_SYSTEM else "slots" if system is extract.SLOT_SYSTEM else "judge"
        self.trace.calls.append({"role": role, "model": model, "system": system, "user": user})
        return self._raw_chat(model, system, user, schema)

    def handle_traced(self, session_id: str, message: str, profile_id: Optional[str] = None) -> tuple[dict, _Trace]:
        resp = self.handle(session_id, message, profile_id)
        return resp, self.trace

    # ------------------------------------------------------------------ entry point
    def handle(self, session_id: str, message: str, profile_id: Optional[str] = None) -> dict:
        self._tl.t = _Trace()
        s = self.store.get(session_id)
        self.store.touch(s)                                    # raises RateLimited
        if profile_id and not s.profile_id:
            s.profile_id = profile_id
        if self.store.over_limit(s):
            return self._blocked(s, replies.MAX_TURNS, "max_turns")

        if not any(a in ("confirm", "risk_scenario") for a in s.awaiting):
            chit = replies.smalltalk(message, has_plan=bool(s.result or s.profile_id), awaiting=bool(s.awaiting))   # hi / thanks / bye / who are you / help
            if chit:
                self.trace.path = "smalltalk"
                return self._resp(s, chit + self._reprompt(s), "smalltalk")

        scr = self._screen(message, s)
        self.trace.gate, self.trace.category = scr.action, scr.category
        if scr.action == "block":
            self.trace.path = "blocked"
            return self._blocked(s, self._refusal(s, scr.category, scr.message), scr.category)
        text = scr.cleaned
        aw = list(s.awaiting)

        if "confirm" in aw:
            if _YES.match(text):
                return self._confirm(s, True)
            if _NO.match(text):
                return self._confirm(s, False)
            s.pending, s.awaiting = None, []                  # user moved on
            aw = []
        if "risk_scenario" in aw:
            return self._scenario_answer(s, text)
        if any(a.startswith("move_") for a in aw):               # the bot asked 'how much?' / 'from where?' / 'to where?'
            follow = self._move_followup(s, text, aw)
            if follow is not None:
                return follow
            aw = [a for a in aw if not a.startswith("move_")]    # the user moved on to something else
        clash = find_conflict(text)
        if clash:
            self.trace.path = "conflict"
            return self._resp(s, replies.t("conflict", what=clash), "clarify")
        if _RESTORE.search(text):
            self.trace.path = "restore"
            return self._restore(s) if s.history else self._resp(s, replies.NOTHING_TO_RESTORE, "modify_inputs")
        gl = replies.glossary_answer(text)
        if gl:
            self.trace.path = "glossary"
            return self._resp(s, gl, "ask_app")
        move = parse.parse_move(text)
        if move:
            self.trace.path = "rule_move"
            if not (move.get("all") or move.get("pct") is not None or move.get("amount") is not None) \
                    and _ALSO.search(text) and s.last_move:        # 'and from MF to stocks also': same amount as last time
                move = {**move, **{k: v for k, v in s.last_move.items() if k in ("all", "pct", "amount")}}
            return self._rebalance(s, move)
        bank_choice = parse.parse_banks(text)
        if bank_choice:
            self.trace.path = "rule_banks"
            return self._banks(s, bank_choice)

        slot_turn = scr.category == "slot_answer" and any(a in replies.SLOT_ORDER for a in aw)
        if slot_turn:
            self.trace.path = "slot_answer"
            return self._inputs(s, text, aw)
        if self.use_gate:                                      # raw ablation arm skips every deterministic shortcut
            ruled = self._rule_intent(s, text)
            if ruled:
                self.trace.path = f"rule:{ruled}"
                return self._dispatch(s, text, ruled, None, aw)
        it = extract.extract_intent(self._chat, self.cfg.chat.intent_model, text)
        if it is None:
            self.trace.path = "intent_failed"
            return self._resp(s, replies.LLM_DOWN, "clarify")
        self.trace.path = f"intent:{it['intent']}"
        if it["intent"] in ("ask_result", "explain_allocation", "rebalance_check", "ask_app") \
                and not (_DOMAIN.search(text) or _MONEY_CUE.search(text) or _APP_CUE.search(text)):
            self.trace.path += "+no_domain_cue"                # model-picked answer intents need a finance word
            return self._blocked(s, self._refusal(s, "off_topic"), "llm_no_domain")
        return self._dispatch(s, text, it["intent"], it.get("fund_name"), aw)

    # ------------------------------------------------------------------ deterministic intent rules
    _R_DRIFT = re.compile(r"\bdrift\w*\b|rebalanc\w*\s+karna\s+pad\w*|\bout\s+of\s+(balance|line|sync)\b|\b(off|away\s+from)\s+(the\s+)?(target|original)\b|\bbalance\s+(bigad\w*|off)\b|rebalanc\w*.{0,25}\b(need|chahiye|zaroorat|should)\b|"
                          r"\b(need|chahiye|should|check|zaroorat)\b.{0,25}rebalanc\w*", re.I)
    _R_RESULT = re.compile(
        r"\b(worst|best)\s+case\b|\b(lowest|highest)\s+outcome\b|\bp\s?5\b|\bp\s?95\b|expected\s+returns?|data\s+kab|kab\s+ka\s+data|\bas\s+of\b|"
        r"\b(stocks?|fds?|mf|mutual\s+funds?|bank)\b.{0,25}\b(kitne|kitna|how\s+much|percent)\b|"
        r"\b(kitne|kitna|how\s+much)\b.{0,25}\b(stocks?|fds?|mf|mutual\s+funds?|bank)\b", re.I)
    _R_WHY = re.compile(r"\b(why|kyu|kyun|explain|samjhao|reason)\b", re.I)
    _R_ABOUT = re.compile(r"\b(allocation|portfolio|split|fds?|banks?|deposits?|stocks?|mutual|mf)\b", re.I)
    _R_BANKQ = re.compile(r"\b(banks?|deposits?|fds?)\b.{0,40}\b(kaunse|kaunsa|which|chune|chosen|select\w*|use\w*)\b|\b(kaunse|kaunsa|which|chune|chosen)\b.{0,40}\b(banks?|deposits?|fds?)\b", re.I)

    _R_COMPARE = re.compile(r"\b(compare|comparison|vs\.?|versus|tulna|farak|difference|dono)\b", re.I)
    _R_HISTORY = re.compile(r"\b(increas\w*|decreas\w*|badh\w*|ghat\w*|chang\w*|history|trend|pehle|previous|last\s+month|"
                            r"pichle|earlier|compared\s+to)\b", re.I)
    _R_VALUE = re.compile(r"\b(kitna|kitne|value|projected|worth|how\s+much|return|milega|amount|weight|percent)\b", re.I)

    def _find_funds(self, text: str) -> list[str]:
        try:
            names = self.engine.known_fund_names()
        except EngineError:
            return []
        words = set(re.findall(r"[a-z0-9]+", text.lower()))
        out = []
        for n in names:
            core = set(re.findall(r"[a-z0-9]+", n.lower())) - _FUND_STOP
            if core and core <= words:
                out.append(n)
        return out

    @staticmethod
    def _instrument_in(s: Session, text: str) -> Optional[dict]:
        if not s.result:
            return None
        words = set(re.findall(r"[a-z0-9]+", text.lower()))
        for i in s.result.get("instruments", []):
            core = set(re.findall(r"[a-z0-9]+", i["display_name"].lower())) - {"fund", "fixed", "deposit", "bank", "limited"}
            if i["label"].lower() in words or (core and core <= words):
                return i
        return None

    def _rule_intent(self, s: Session, text: str) -> Optional[str]:
        """Cheap, unambiguous intents decided by code. Everything else goes to the intent LLM."""
        funds = self._find_funds(text)
        if len(funds) >= 2 and not self._R_HISTORY.search(text):
            return "compare_funds"
        if (funds or s.last_fund) and self._R_HISTORY.search(text):
            return "sector_history"
        if self._R_COMPARE.search(text) and re.search(r"\b(funds?|mf)\b", text, re.I):
            return "compare_funds"
        if funds or self._find_fund(s, text, None)[0] is not None or re.search(r"\bsectors?\b", text, re.I) \
                and not prefs.parse_prefs(text):
            return "explain_mf_sector"
        if prefs.parse_prefs(text):
            return "modify_inputs" if s.result is not None else "provide_inputs"
        if self._instrument_in(s, text) and self._R_VALUE.search(text):
            return "ask_result"
        if self._R_DRIFT.search(text):
            return "rebalance_check"
        if self._R_RESULT.search(text):
            return "ask_result"
        if (self._R_WHY.search(text) and self._R_ABOUT.search(text)) or self._R_BANKQ.search(text):
            return "explain_allocation"
        if self._is_edit(text):
            return "modify_inputs" if s.result is not None else "provide_inputs"
        return None

    @staticmethod
    def _is_edit(text: str) -> bool:
        """An unambiguous plan edit: a rupee amount, years, a risk %, an add/remove of an asset class, a relative risk change."""
        ops = parse.parse_class_ops(text)
        return (parse.parse_amount(text) is not None or parse.parse_years(text) is not None
                or parse.parse_risk_pct(text) is not None or bool(ops["remove"] or (ops["add"] and ops["explicit"]))
                or parse.parse_risk_shift(text) is not None or parse.parse_risk(text) is not None)

    def _dispatch(self, s: Session, text: str, intent: str, fund_name: Optional[str], aw: list[str]) -> dict:
        it = {"fund_name": fund_name}
        if intent in ("provide_inputs", "modify_inputs"):
            return self._inputs(s, text, aw)
        if intent == "rebalance":
            return self._resp(s, replies.MOVE_UNCLEAR, "rebalance", missing=["move"])
        if intent == "explain_allocation":
            return self._explain_allocation(s, text)
        if intent == "explain_mf_sector":
            return self._mf_sector(s, text, it.get("fund_name"))
        if intent == "rebalance_check":
            return self._drift(s)
        if intent == "ask_result":
            return self._ask_result(s, text)
        if intent == "compare_funds":
            return self._compare(s, text)
        if intent == "sector_history":
            return self._history(s, text, fund_name)
        if intent == "ask_app":
            return self._resp(s, replies.ASK_APP, "ask_app")
        return self._blocked(s, self._refusal(s, "off_topic"), "llm_unsupported", intent="unsupported")

    # ------------------------------------------------------------------ refusals (English only)
    @staticmethod
    def _refusal(s: Session, category: Optional[str], default: Optional[str] = None) -> str:
        return default or REFUSALS["off_topic"]

    # ------------------------------------------------------------------ screening
    def _screen(self, message: str, s: Session) -> Screen:
        if not self.use_gate:                                  # ablation only: structure checks, nothing topical
            cleaned = normalise(message)
            if not cleaned:
                return Screen("block", "empty", REFUSALS["empty"], cleaned)
            if len(cleaned) > MAX_CHARS:
                return Screen("block", "too_long", REFUSALS["too_long"], cleaned)
            if _NON_LATIN.search(cleaned):
                return Screen("block", "unsupported_language", REFUSALS["unsupported_language"], cleaned)
            return Screen("allow", "in", None, cleaned)
        if self.gate is None:
            self.gate = ScopeGate()
        return screen(message, awaiting=s.awaiting, gate=self.gate, judge=self.judge if self.use_judge else None)

    # ------------------------------------------------------------------ response helpers
    def _params_out(self, s: Session) -> dict:
        p = {k: v for k, v in s.params.items() if v is not None}
        if p.get("risk") in parse.RISK_SCORE and "risk_score" not in p:
            p["risk_score"] = parse.risk_to_score(p["risk"])
        return p

    def _resp(self, s: Session, reply: str, intent: str, result: Optional[dict] = None, missing: Optional[list] = None,
              blocked: Optional[bool] = None, category: Optional[str] = None) -> dict:
        out: dict[str, Any] = {
            "reply": reply, "intent": intent, "params": self._params_out(s),
            "missing": missing if missing is not None else [a for a in s.awaiting if a in replies.SLOT_ORDER],
            "result": result, "session_id": s.session_id,
        }
        if blocked:
            out["blocked"], out["category"] = True, category
        return out

    def _blocked(self, s: Session, reply: str, category: Optional[str], intent: str = "unsupported") -> dict:
        return self._resp(s, reply, intent, missing=[], blocked=True, category=category)

    def _polish(self, source: str) -> str:
        """Optional LLM rewording. The model sees ONLY the template text (no user text) and the result must pass the
        grounding check (no new numbers, no advice); otherwise the template is used as is."""
        if not getattr(self.cfg.chat, "polish", False) or self.text_fn is None:
            return source
        try:
            out = self.text_fn(self.cfg.chat.explain_model,
                               "Rewrite this in friendly, plain English. Use ONLY the numbers given, add no new numbers, "
                               "no advice.\n\n" + source)
        except Exception as exc:
            logger.info("polish failed: %s", exc)
            return source
        return out if reply_is_grounded(out, source) else source

    # ------------------------------------------------------------------ state helpers
    @staticmethod
    def _risk_label(score: float) -> str:
        return min(parse.RISK_SCORE, key=lambda k: abs(parse.RISK_SCORE[k] - score))

    @staticmethod
    def _risk_text(params: dict) -> str:
        """'low' for the three preset scores, '35%' for an explicit one."""
        score, label = params.get("risk_score"), params.get("risk", "")
        if score is not None and parse.RISK_SCORE.get(label) != score:
            return f"{replies.num(score)}%"
        return label

    def _params_of(self, res: dict) -> dict:
        """The editable inputs of a plan, read back from the engine result (the engine is the source of truth)."""
        p: dict[str, Any] = {"amount": res["amount"], "years": res["years"], "risk": self._risk_label(res["risk_score"]),
                             "risk_score": res["risk_score"], "classes": list(res.get("classes") or ["stocks", "mf", "fd"]),
                             "banks": res.get("banks", "auto")}
        for k in ("sector_pref", "mf_category_pref"):
            if res.get(k):
                p[k] = list(res[k])
        if res.get("manual_split"):
            p["manual_split"] = dict(res["manual_split"])
        return p

    @staticmethod
    def _req_of(params: dict) -> dict:
        """Plan inputs in the engine's request keys (normalised so two param dicts can be compared)."""
        score = params.get("risk_score")
        if score is None:
            score = parse.risk_to_score(params["risk"])
        return {"amount": float(params["amount"]), "years": float(params["years"]), "risk_score": float(score),
                "classes": list(params.get("classes") or ["stocks", "mf", "fd"]),
                "sector_pref": sorted(params.get("sector_pref") or []),
                "mf_category_pref": sorted(params.get("mf_category_pref") or []),
                "banks": params.get("banks", "auto")}

    def _adopt(self, s: Session, res: dict) -> None:
        s.result, s.profile_id = res, res.get("profile_id", s.profile_id)
        s.params = self._params_of(res)

    def _ensure_loaded(self, s: Session) -> bool:
        if s.result is None and s.profile_id:
            try:
                got = self.engine.get_allocation(s.profile_id)
            except EngineError:
                return False
            if got:
                self._adopt(s, got["allocation_json"])
        return s.result is not None

    def _commit(self, s: Session, params: dict, res: dict) -> None:
        s.snapshot()
        s.params, s.result, s.profile_id = params, res, res.get("profile_id")
        s.awaiting, s.pending = [], None

    def _engine_error(self, s: Session, exc: EngineError, intent: str) -> dict:
        if isinstance(exc, EngineRejected):                     # the engine refused with a reason (HTTP 422)
            return self._resp(s, replies.t("rejected", detail=exc.detail or "-"), "clarify")
        logger.warning("engine call failed: %s", exc)
        return self._resp(s, replies.t("engine_down"), intent)

    # ------------------------------------------------------------------ confirm / restore
    def _confirm(self, s: Session, yes: bool) -> dict:
        self.trace.path = "confirm"
        pend = s.pending
        if not pend:
            s.awaiting = []
            return self._resp(s, replies.NOTHING_PENDING, "clarify")
        if not yes:
            if pend.get("revert") and self._pid(s):             # the edit was already saved by PATCH: put the old plan back
                try:
                    self.engine.update_plan(self._pid(s), pend["revert"])
                except EngineError as exc:
                    logger.warning("revert after declined confirm failed: %s", exc)
            s.pending, s.awaiting = None, []
            return self._resp(s, replies.CONFIRM_DECLINED, "modify_inputs")
        self._commit(s, pend["params"], pend["result"])
        return self._resp(s, replies.allocation_reply(s.result, self._risk_text(s.params), pend.get("changes")),
                          "modify_inputs" if pend.get("changes") else "provide_inputs", result=s.result)

    def _restore(self, s: Session) -> dict:
        params, res = s.history[-1]
        pid = self._pid(s)
        if pid:                                                 # the stored plan is the latest one: write the old inputs back
            try:
                out = self.engine.update_plan(pid, {**self._req_of(params), "manual_split": params.get("manual_split")})
            except EngineError as exc:
                return self._engine_error(s, exc, "modify_inputs")
            res = out["allocation"]
            params = self._params_of(res)
        s.history.pop()
        s.params, s.result, s.profile_id, s.awaiting, s.pending = params, res, res.get("profile_id"), [], None
        return self._resp(s, replies.RESTORED + " " + replies.allocation_reply(res, self._risk_text(params)),
                          "modify_inputs", result=res)

    # ------------------------------------------------------------------ risk scenarios
    def _scenario_answer(self, s: Session, text: str) -> dict:
        self.trace.path = "risk_scenario"
        sc = s.risk_scenario
        pts = replies.parse_scenario_answer(sc["step"], text)
        if pts is None:
            sc["retries"] = sc.get("retries", 0) + 1
            if sc["retries"] >= 2:                              # never guess: fall back to asking directly
                s.risk_scenario, s.awaiting = {}, ["risk"]
                return self._resp(s, replies.RISK_FALLBACK, "provide_inputs")
            return self._resp(s, replies.RISK_RETRY + " " + replies.SCENARIOS[sc["step"]], "provide_inputs")
        sc["points"] += pts
        sc["step"] += 1
        sc["retries"] = 0
        if sc["step"] < len(replies.SCENARIOS):
            return self._resp(s, replies.SCENARIOS[sc["step"]], "provide_inputs")
        label = replies.risk_from_points(sc["points"])
        s.risk_scenario, s.awaiting = {}, []
        return self._inputs(s, "", [], forced={"risk": label}, preface=replies.t("risk_level", label=label))

    # ------------------------------------------------------------------ inputs (provide / modify)
    def _extract_patch(self, s: Session, text: str, aw: list[str]) -> tuple[dict, list[str], bool]:
        """-> (patch, bad_fields, risk_unknown). Rules first; slot LLM only when the rules found nothing."""
        patch: dict[str, Any] = {}
        only_amount = "amount" in aw and "years" not in aw
        only_years = "years" in aw and "amount" not in aw
        a = parse.parse_amount(text, allow_bare=only_amount)
        y = parse.parse_years(text, allow_bare=only_years)
        if a is not None:
            patch["amount"] = a
        if y is not None:
            patch["years"] = y
        r = parse.parse_risk(text)
        rp = parse.parse_risk_pct(text, allow_bare="risk" in aw)
        shift = parse.parse_risk_shift(text) if s.params.get("risk") else None
        if rp is not None:
            patch["risk_pct"] = rp
        elif r and not (shift and s.params.get("risk")):
            patch["risk"] = r
        elif shift:
            patch["risk_shift"] = shift
        ops = parse.parse_class_ops(text)
        has_prior = s.result is not None
        if ops["remove"]:
            patch["remove_classes"] = sorted(ops["remove"])
        elif ops["add"]:
            patch["add_classes"] = sorted(ops["add"])
        elif ops["only"] and (ops["explicit"] or not has_prior) and not prefs.parse_prefs(text):
            patch["classes"] = sorted(ops["only"])
        for k, mv in prefs.parse_prefs(text).items():
            patch[k] = mv
        unknown = parse.risk_unknown(text) and ("risk" in aw or not s.params.get("risk"))
        if patch or unknown or not text:
            return patch, [], unknown
        # rules found nothing -> ask the slot LLM, then demand evidence for every value it returns
        got = extract.extract_slots(self._chat, self.cfg.chat.intent_model, text)
        if got is None:
            return {}, [], False
        slots = {"amount": got["amount"], "years": got["years"], "risk": got["risk"],
                 "classes": got["classes"] or None}
        ok, bad = slots_have_evidence({k: v for k, v in slots.items() if v is not None}, text, awaiting=aw)
        mentioned = classes_in(text)
        for k in ("amount", "years", "risk", "classes"):
            if k == "classes" and has_prior and not ops["explicit"]:
                continue                                        # 'to stocks from mutual funds' is not 'only stocks and funds'
            if slots[k] is not None and k not in bad:
                patch[k] = slots[k]
        if got["remove_classes"] and set(got["remove_classes"]) <= mentioned:
            patch["remove_classes"] = sorted(got["remove_classes"])
        elif got["remove_classes"]:
            bad.append("classes")
        if got["risk_shift"] and parse.parse_risk_shift(text) == got["risk_shift"]:
            patch["risk_shift"] = got["risk_shift"]
        elif got["risk_shift"]:
            bad.append("risk")
        return patch, sorted(set(bad)), False

    def _inputs(self, s: Session, text: str, aw: list[str], forced: Optional[dict] = None,
                preface: str = "") -> dict:
        lim = self.cfg.limits
        if s.result is None and s.profile_id and not s.params and not forced:
            self._ensure_loaded(s)                              # a saved allocation from the form: edits apply to it
        patch, bad, unknown = self._extract_patch(s, text, aw) if not forced else (dict(forced), [], False)
        if bad:                                                 # the model invented these: dropped
            self.trace.path += "+dropped_unsupported_slot"
            if s.result is None:                                # only worth mentioning while we are still collecting inputs
                preface = (preface + " " if preface else "") + replies.t("not_sure", what=", ".join(bad))
        if not patch and not forced and not aw and s.result is None \
                and not (_DOMAIN.search(text) or _MONEY_CUE.search(text) or _APP_CUE.search(text)):
            # the intent model said "inputs" but the message has no slot and no finance cue: not for this app
            self.trace.path += "+no_slots"
            return self._blocked(s, self._refusal(s, "off_topic"), "llm_no_slots")
        new = copy.deepcopy(s.params) or {}
        new.setdefault("classes", ["stocks", "mf", "fd"])
        changes: list[str] = []
        had_result = s.result is not None

        def note(label: str, old: Any, val: Any, fmt=str) -> None:
            if had_result and old != val:
                changes.append(f"{label} {fmt(old)} -> {fmt(val)}" if old is not None else f"{label} {fmt(val)}")

        if "amount" in patch:
            v = float(patch["amount"])
            if not lim.amount_min <= v <= lim.amount_max:
                s.awaiting = ["amount"]
                return self._resp(s, replies.limit_msg("amount", lim, nonpositive=v <= 0), "provide_inputs",
                                  missing=["amount"])
            note("amount", new.get("amount"), v, replies.inr)
            new["amount"] = v
        if "years" in patch:
            v = float(patch["years"])
            if not lim.years_min <= v <= lim.years_max:
                s.awaiting = ["years"]
                return self._resp(s, replies.limit_msg("years", lim), "provide_inputs", missing=["years"])
            note("years", new.get("years"), v, replies.num)
            new["years"] = v
        old_risk_text = self._risk_text(new) if new.get("risk") else None
        if "risk_pct" in patch:
            v = float(patch["risk_pct"])
            if not 0 <= v <= 100:
                s.awaiting = ["risk"]
                return self._resp(s, replies.t("risk_range"), "provide_inputs", missing=["risk"])
            new["risk"], new["risk_score"] = self._risk_label(v), v
            if had_result and old_risk_text and old_risk_text != self._risk_text(new):
                changes.append(f"risk {old_risk_text} -> {self._risk_text(new)}")
        elif "risk" in patch:
            new["risk"], new["risk_score"] = patch["risk"], parse.risk_to_score(patch["risk"])
            if had_result and old_risk_text and old_risk_text != self._risk_text(new):
                changes.append(f"risk {old_risk_text} -> {self._risk_text(new)}")
        elif "risk_shift" in patch:
            moved = parse.shift_risk(new.get("risk"), patch["risk_shift"])
            if moved is not None:
                if moved == new.get("risk") and parse.RISK_SCORE[moved] == new.get("risk_score", parse.RISK_SCORE[moved]):
                    preface = (preface + " " if preface else "") + replies.t("risk_capped", moved=moved)
                new["risk"], new["risk_score"] = moved, parse.risk_to_score(moved)
                if had_result and old_risk_text and old_risk_text != self._risk_text(new):
                    changes.append(f"risk {old_risk_text} -> {self._risk_text(new)}")
        cls_before = list(new["classes"])
        lab = replies.CLASS_LABEL
        if "classes" in patch:
            new["classes"] = [c for c in ("stocks", "mf", "fd") if c in patch["classes"]]
        if "add_classes" in patch:
            new["classes"] = [c for c in ("stocks", "mf", "fd") if c in set(new["classes"]) | set(patch["add_classes"])]
        if "remove_classes" in patch:
            gone = set(patch["remove_classes"])
            if had_result and not gone & set(cls_before):
                return self._resp(s, replies.t("class_absent", c=" / ".join(lab[c] for c in sorted(gone))), "clarify")
            left = [c for c in new["classes"] if c not in gone]
            if not left:
                return self._resp(s, replies.t("last_class"), "clarify")
            new["classes"] = left
        for k, label in (("sector_pref", "sectors"), ("mf_category_pref", "MF category")):
            if k in patch:
                mode, vals = patch[k]
                before = list(new.get(k) or [])
                new[k] = prefs.apply_pref(before, mode, vals)
                if had_result and new[k] != before:
                    show = lambda xs: ", ".join(prefs.SECTOR_LABEL.get(x, x) for x in xs) or "no restriction"
                    changes.append(f"{label}: {show(before)} -> {show(new[k])}")
        if new["classes"] != cls_before and had_result:
            removed = [lab[c] for c in cls_before if c not in new["classes"]]
            added = [lab[c] for c in new["classes"] if c not in cls_before]
            if removed:
                changes.append("removed " + ", ".join(removed))
            if added:
                changes.append("added " + ", ".join(added))

        s.params = {**s.params, **{k: v for k, v in new.items() if v is not None}} if not had_result else s.params
        if unknown and not new.get("risk"):
            s.risk_scenario = {"step": 0, "points": 0}
            s.awaiting = ["risk_scenario"]
            return self._resp(s, replies.SCENARIOS[0], "provide_inputs", missing=["risk"])

        missing = [k for k in replies.SLOT_ORDER if new.get(k) is None]
        if missing:
            q, todo = replies.ask_for(missing)
            s.awaiting = todo
            return self._resp(s, (preface + " " if preface else "") + q, "provide_inputs", missing=todo)
        if had_result and not changes and not forced and not preface:
            return self._resp(s, replies.t("no_change"), "modify_inputs")
        return self._apply(s, new, changes, preface)

    def _apply(self, s: Session, new: dict, changes: list[str], preface: str = "") -> dict:
        """Send the edited inputs to the engine: PATCH the stored plan when there is one (so the chat edits the same plan the
        forms edit), else create it."""
        had_result, pid = s.result is not None, self._pid(s)
        req = self._req_of(new)
        update = bool(had_result and pid)
        revert = None
        try:
            if update:
                old = self._req_of(s.params)
                patch = {k: v for k, v in req.items() if old.get(k) != v}
                if s.params.get("manual_split") and ("risk_score" in patch or "classes" in patch):
                    patch["manual_split"] = None                # a rebalanced split no longer fits: back to the risk-based one
                    changes.append("split reset to the risk-based one")
                revert = {**old, "manual_split": s.params.get("manual_split")}
                res = self.engine.update_plan(pid, patch)["allocation"]
            else:
                res = self.engine.allocate(req)
        except EngineError as exc:
            return self._engine_error(s, exc, "clarify")
        intent = "modify_inputs" if had_result else "provide_inputs"
        if abs(float(res["years"]) - float(new["years"])) > 1e-9:
            preface = (preface + " " if preface else "") + replies.t(
                "years_rounded", a=replies.num(new["years"]), b=replies.num(res["years"]))
        params = self._params_of(res)
        if res.get("requires_confirmation"):
            s.pending = {"params": params, "result": res, "changes": changes, "revert": revert}
            s.awaiting = ["confirm"]
            warn = " ".join(f"Heads up: {w}" for w in res.get("warnings") or [])
            head = ("Updated: " + "; ".join(changes) + ". ") if changes else ""
            return self._resp(s, (head + warn + " " + replies.CONFIRM_ASK).replace("  ", " "), intent, missing=[])
        self._commit(s, params, res)
        body = replies.allocation_reply(res, self._risk_text(params), changes)
        return self._resp(s, (preface + "\n" if preface else "") + body, intent, result=res, missing=[])

    # ------------------------------------------------------------------ banks (FD)
    def _banks(self, s: Session, choice: dict) -> dict:
        try:
            bank_list = self.engine.list_banks()
        except EngineError as exc:
            return self._engine_error(s, exc, "clarify")
        names = {b["id"]: b["display_name"] for b in bank_list}
        listing = ", ".join(names.values())
        if choice.get("unknown"):
            return self._resp(s, replies.t("bank_unknown", name=choice["unknown"][0], names=listing), "clarify")
        ids = choice.get("ids", [])
        missing_ids = [i for i in ids if i not in names]
        if missing_ids:                                         # known to the parser, not on this engine's list
            return self._resp(s, replies.t("bank_unknown", name=missing_ids[0], names=listing), "clarify")
        if choice["mode"] == "ask":
            return self._resp(s, replies.t("bank_ask", names=listing), "clarify")
        if not self._ensure_loaded(s):
            return self._resp(s, replies.t("need_plan"), "modify_inputs")
        if "fd" not in s.params.get("classes", []):
            return self._resp(s, replies.t("bank_no_fd"), "clarify")
        cur = s.params.get("banks", "auto")
        cur_ids = cur if isinstance(cur, list) else [i["label"] for i in s.result.get("instruments", [])
                                                      if i["bucket"] == "bank" and i["label"] in names]
        mode = choice["mode"]
        target: Any = ("auto" if mode == "auto" else ids if mode == "set"
                       else cur_ids + [i for i in ids if i not in cur_ids] if mode == "add"
                       else [i for i in cur_ids if i not in ids])
        if target == []:
            return self._resp(s, replies.t("bank_last"), "clarify")
        if target == cur:
            return self._resp(s, replies.t("no_change"), "modify_inputs")
        show = lambda b: "auto (best 5)" if b == "auto" else ", ".join(names.get(i, i) for i in b)
        return self._apply(s, {**s.params, "banks": target}, [f"banks: {show(cur)} -> {show(target)}"])

    # ------------------------------------------------------------------ rebalance / drift
    def _pid(self, s: Session) -> Optional[str]:
        return s.profile_id or (s.result or {}).get("profile_id")

    def _rebalance(self, s: Session, mv: dict) -> dict:
        pid = self._pid(s)
        if not pid:
            return self._resp(s, replies.t("need_plan"), "rebalance")
        lab = replies.BUCKET_LABEL
        if mv.get("multi_dest"):                                # 'from stocks to MF and FD': one destination at a time
            return self._resp(s, replies.MOVE_ONE_DEST, "rebalance", missing=["move"])
        srcs = list(mv.get("sources") or ([mv["from"]] if mv.get("from") else []))
        dst = mv.get("to")
        pct, amt, whole = mv.get("pct"), mv.get("amount"), bool(mv.get("all"))
        if not srcs or not dst:                                 # one end of the move is missing: ask for it, remember the rest
            if not srcs and not dst:
                return self._resp(s, replies.MOVE_UNCLEAR, "rebalance", missing=["move"])
            s.pending_move = {k: mv[k] for k in ("from", "sources", "to", "pct", "amount", "all") if mv.get(k) is not None}
            s.awaiting = ["move_dest" if srcs else "move_source"]
            return self._resp(s, replies.MOVE_ASK_DEST if srcs else replies.MOVE_ASK_SOURCE, "rebalance", missing=["move"])
        if (pct is not None and not 0 < pct <= 100) or (amt is not None and amt <= 0):
            return self._resp(s, replies.MOVE_UNCLEAR, "rebalance", missing=["move"])
        if dst in srcs:
            return self._resp(s, replies.SAME_BUCKET, "rebalance")
        if not (whole or pct is not None or amt is not None):   # how much? ('all', 10% or 5000)
            s.pending_move = {"from": srcs[0], "sources": srcs, "to": dst}
            s.awaiting = ["move_amount"]
            if len(srcs) > 1:
                ask = replies.MOVE_ASK_ALL_MULTI.format(src=" and ".join(lab[b] for b in srcs), dst=lab[dst])
            else:
                ask = replies.MOVE_ASK_AMOUNT.format(src=lab[srcs[0]], dst=lab[dst])
            return self._resp(s, ask, "rebalance", missing=["move"])
        if len(srcs) > 1 and not whole:                         # a percentage or amount cannot be split across two sources
            return self._resp(s, replies.MOVE_MULTI_PARTIAL, "rebalance", missing=["move"])

        self._ensure_loaded(s)
        moved: list[tuple[str, dict]] = []
        notes: list[str] = []
        snapped = False
        for src in srcs:
            held = None
            if s.result:
                held = (s.result.get("split_pct") or {}).get(src)
                if held is None:
                    held = (s.result["buckets"].get(src) or {}).get("weight_pct")
            if s.result and not held:
                if len(srcs) == 1:
                    return self._resp(s, replies.t("no_money_in", c=lab[src]), "rebalance")
                notes.append(f"{lab[src]} had no money, so I skipped it.")
                continue
            try:
                out = self.engine.rebalance(pid, src, dst, pct=float(held) if whole else pct, amount=None if whole else amt)
            except EngineError as exc:
                if moved:
                    notes.append(f"I couldn't move the money from {lab[src]}.")
                    break
                return self._engine_error(s, exc, "rebalance")
            if not snapped:
                s.snapshot()                                    # one undo step for the whole message
                snapped = True
            self._adopt(s, out["allocation"])                   # classes come from the result: a move can add or drop one
            moved.append((src, out))
        if not moved:
            return self._resp(s, replies.t("no_money_in", c=" or ".join(lab[b] for b in srcs)), "rebalance")
        s.awaiting, s.pending_move = [], None
        s.last_move = {"from": srcs[0], "to": dst, **({"all": True} if whole else {"pct": pct} if pct is not None else {"amount": amt})}
        res = moved[-1][1]["allocation"]
        head = "I moved " + " and ".join(f"{replies.inr(o['moved_amount'])} from {lab[b]}" for b, o in moved) + f" to {lab[dst]}."
        if len(moved) == 1 and moved[0][1].get("capped"):
            o = moved[0][1]
            head += (f" You asked for {replies.inr(o['requested_amount'])}, but {lab[moved[0][0]]} only had "
                     f"{replies.inr(o['moved_amount'])}.")
        if notes:
            head += " " + " ".join(notes)
        body = replies.allocation_reply(res, self._risk_text(s.params))
        return self._resp(s, head + " " + body, "rebalance", result=res, missing=[])

    def _move_followup(self, s: Session, text: str, aw: list[str]) -> Optional[dict]:
        """The bot asked for one missing piece of a move; read the answer and finish the move. None = not an answer."""
        pending, s.pending_move = s.pending_move, None
        s.awaiting = [a for a in s.awaiting if not a.startswith("move_")]
        if not pending:
            return None
        self.trace.path = "move_followup"
        if "move_amount" in aw:
            got = parse.parse_move_amount(text)
            return self._rebalance(s, {**pending, **got}) if got else None
        bucket_of = {"stocks": "stock", "mf": "mf", "fd": "bank"}
        found = [bucket_of[c] for c in classes_in(text)]
        if len(found) != 1:
            return None
        return self._rebalance(s, {**pending, ("from" if "move_source" in aw else "to"): found[0]})

    def _reprompt(self, s: Session) -> str:
        """After small talk in the middle of a question, ask the same question again."""
        slots = [a for a in s.awaiting if a in replies.SLOT_ORDER]
        if slots:
            return " " + replies.ask_for(slots)[0]
        pm, lab = s.pending_move, replies.BUCKET_LABEL
        if pm and "move_amount" in s.awaiting:
            return " " + replies.MOVE_ASK_AMOUNT.format(src=lab[pm["from"]], dst=lab[pm["to"]])
        if pm and "move_source" in s.awaiting:
            return " " + replies.MOVE_ASK_SOURCE
        if pm and "move_dest" in s.awaiting:
            return " " + replies.MOVE_ASK_DEST
        return ""

    def _drift(self, s: Session) -> dict:
        pid = self._pid(s)
        if not pid:
            return self._resp(s, replies.NEED_ALLOCATION, "rebalance_check")
        try:
            d = self.engine.check_drift(pid)
        except EngineError:
            return self._resp(s, replies.ENGINE_DOWN, "rebalance_check")
        if not d.get("found"):
            return self._resp(s, d.get("message", replies.NEED_ALLOCATION), "rebalance_check")
        if not d.get("drifted"):
            return self._resp(s, "Your allocation hasn't drifted in any meaningful way. " + replies.DISCLAIMER,
                              "rebalance_check")
        lines = "\n".join(f"{x['bucket']}: {replies.inr(x['before'])} to {replies.inr(x['after'])} "
                          f"({'+' if x['delta'] >= 0 else '-'}{replies.inr(abs(x['delta']))})"
                          for x in d["diff"] if abs(x["delta"]) > 1)
        return self._resp(s, "Your allocation has drifted:\n" + lines +
                          "\nTo rebalance, say for example 'move 5% from stocks to FD'.", "rebalance_check")

    # ------------------------------------------------------------------ explain / ask
    def _explain_allocation(self, s: Session, text: str = "") -> dict:
        if not self._ensure_loaded(s):
            return self._resp(s, replies.NEED_ALLOCATION, "explain_allocation")
        res, question = s.result, text
        body = res.get("explanation_text") or replies.allocation_reply(res, self._risk_text(s.params))
        body = self._polish(body)
        if re.search(r"\b(banks?|fds?|fixed\s+deposits?|deposits?)\b", question, re.I):
            banks = [i for i in res.get("instruments", []) if i["bucket"] == "bank"]
            if banks:
                body += "\nBanks chosen for the FD: " + ", ".join(
                    f"{b['display_name']} ({replies.num(b['weight_pct'])}%, {replies.inr(b['amount'])})" for b in banks) + "."
        if prefs_line := self._prefs_line(res):
            body += "\n" + prefs_line
        return self._resp(s, body + "\n" + replies.DISCLAIMER, "explain_allocation", result=res)

    @staticmethod
    def _prefs_line(res: dict) -> str:
        parts = []
        if res.get("sector_pref"):
            parts.append("sectors: " + ", ".join(prefs.SECTOR_LABEL.get(x, x) for x in res["sector_pref"]))
        if res.get("mf_category_pref"):
            parts.append("MF category: " + ", ".join(res["mf_category_pref"]))
        return ("Your preferences: " + "; ".join(parts) + ".") if parts else ""

    # ------------------------------------------------------------------ compare / history (tables answered by code)
    def _compare(self, s: Session, text: str) -> dict:
        funds = self._find_funds(text)
        if len(funds) < 2:
            return self._resp(s, "To compare, please name two mutual funds, for example 'HDFC Large Cap Fund vs SBI Small Cap Fund'.",
                              "compare_funds")
        rows = []
        try:
            for f in funds[:2]:
                r = self.engine.get_sector_allocation(f)
                if r is None:
                    return self._resp(s, replies.FUND_NO_DATA.format(name=f), "compare_funds")
                rows.append(r)
        except EngineError:
            return self._resp(s, replies.ENGINE_DOWN, "compare_funds")
        a, b = rows
        secs = sorted(set(a["sector_json"]) | set(b["sector_json"]),
                      key=lambda k: -max(a["sector_json"].get(k, 0), b["sector_json"].get(k, 0)))
        fmt = lambda d, k: f"{replies.num(d[k])}%" if k in d else "-"
        lines = [f"{k}: {fmt(a['sector_json'], k)} vs {fmt(b['sector_json'], k)}" for k in secs]
        top = lambda r: max(r["sector_json"].items(), key=lambda kv: kv[1])
        ta, tb = top(a), top(b)
        s.last_fund = a["fund_name"]
        out = (f"{a['fund_name']} vs {b['fund_name']} (as of {a.get('date') or b.get('date')}):\n" + "\n".join(lines) +
               f"\nLargest sector: {ta[0]} ({replies.num(ta[1])}%) in {a['fund_name']} and "
               f"{tb[0]} ({replies.num(tb[1])}%) in {b['fund_name']}.")
        return self._resp(s, out, "compare_funds")

    def _history(self, s: Session, text: str, llm_name: Optional[str]) -> dict:
        funds = self._find_funds(text)
        name = funds[0] if funds else s.last_fund
        if not name:
            return self._resp(s, replies.FUND_ASK, "sector_history")
        try:
            hist = self.engine.get_sector_history(name)
        except EngineError:
            return self._resp(s, replies.ENGINE_DOWN, "sector_history")
        if not hist or len(hist) < 2:
            return self._resp(s, f"Sector history for {name} isn't available yet (at least two dates are needed).", "sector_history")
        hist = sorted(hist, key=lambda r: r["date"])
        old, new = hist[-2], hist[-1]
        keys = set(old["sector_json"]) | set(new["sector_json"])
        delta = {k: round(new["sector_json"].get(k, 0) - old["sector_json"].get(k, 0), 2) for k in keys}
        up = sorted((kv for kv in delta.items() if kv[1] > 0), key=lambda kv: -kv[1])[:3]
        down = sorted((kv for kv in delta.items() if kv[1] < 0), key=lambda kv: kv[1])[:3]
        fmt = lambda xs: ", ".join(f"{k} ({v:+g} pts)" for k, v in xs) or "none"
        s.last_fund = name
        return self._resp(s, f"{name}, from {old['date']} to {new['date']}.\nIncreased: {fmt(up)}\nDecreased: {fmt(down)}", "sector_history")

    def _ask_result(self, s: Session, text: str) -> dict:
        if not self._ensure_loaded(s):
            return self._resp(s, replies.NEED_ALLOCATION, "ask_result")
        res, t = s.result, text.lower()
        n = replies.num
        inst = self._instrument_in(s, text)
        if inst:
            r = (f"{inst['display_name']} is {replies.inr(inst['amount'])} today ({n(inst['weight_pct'])}% of your portfolio)" +
                 (f" and is estimated at about {replies.inr(inst['projected_value'])} after {replies.years_text(res['years'])}." if inst.get("projected_value") else "."))
            return self._resp(s, r + "\n" + replies.DISCLAIMER, "ask_result", result=res)
        sc = res.get("scenarios")
        na = "That number isn't available right now."
        if re.search(r"worst|p\s?5|kharab|lowest|minimum|sabse\s+kam|bear", t):
            v, pr = res.get("p5_return_pct"), (res.get("projected") or {}).get("p5")
            if v is not None:
                r = f"In the worst case (P5), the return is about {n(v)}% a year" + (f", or about {replies.inr(pr)} after {replies.years_text(res['years'])}" if pr else "") + "."
            elif sc:
                r = (f"In the bear scenario, the return is about {n(round(sc['bear']['return_pct'], 1))}% a year, or about "
                     f"{replies.inr(sc['bear']['projected_value'])} after {replies.years_text(res['years'])}. "
                     "This is the forecast's bear case, not a guarantee.")
            else:
                r = na
        elif re.search(r"best|p\s?95|achha|accha|highest|maximum|bull", t):
            v, pr = res.get("p95_return_pct"), (res.get("projected") or {}).get("p95")
            if v is not None:
                r = f"In the best case (P95), the return is about {n(v)}% a year" + (f", or about {replies.inr(pr)} after {replies.years_text(res['years'])}" if pr else "") + "."
            elif sc:
                r = (f"In the bull scenario, the return is about {n(round(sc['bull']['return_pct'], 1))}% a year, or about "
                     f"{replies.inr(sc['bull']['projected_value'])} after {replies.years_text(res['years'])}. "
                     "This is the forecast's bull case, not a guarantee." + (" " + sc["note"] if sc.get("note") else ""))
            else:
                r = na
        elif re.search(r"expected|return|munafa|kitna\s+milega", t):
            v = res.get("expected_return_pct")
            r = na if v is None else f"The expected return is about {n(round(v, 1))}% a year. It is an estimate, not a guarantee."
        elif re.search(r"data\s+kab|as\s+of|date|kab\s+ka", t):
            r = f"The data is as of {replies.asof_text(res.get('data_as_of') or 'unknown')}."
        elif re.search(r"how\s+many\s+stocks|kitne\s+stocks", t):
            k = sum(1 for i in res.get("instruments", []) if i["bucket"] == "stock")
            r = f"Your plan holds {k} stocks."
        else:
            wanted = classes_in(t)
            bmap = {"stocks": "stock", "mf": "mf", "fd": "bank"}
            parts = []
            for c in ("stocks", "mf", "fd"):
                b = bmap[c]
                v = res["buckets"].get(b)
                if c in wanted and v:
                    parts.append(f"{replies.BUCKET_LABEL[b]} is {n(v['weight_pct'])}% of your plan ({replies.inr(v['amount'])}).")
            if parts:
                r = " ".join(parts)
            else:
                return self._resp(s, replies.allocation_reply(res, self._risk_text(s.params)), "ask_result", result=res)
        return self._resp(s, r + "\n" + replies.DISCLAIMER, "ask_result", result=res)

    # ------------------------------------------------------------------ MF sector (answered by code from the table)
    def _find_fund(self, s: Session, text: str, llm_name: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        """-> (resolved fund name or None, unknown_name_to_report or None). Evidence: the name must be in the text."""
        try:
            names = self.engine.known_fund_names()
        except EngineError:
            names = []
        words = set(re.findall(r"[a-z0-9]+", text.lower()))
        hits = []
        for n in names:
            core = set(re.findall(r"[a-z0-9]+", n.lower())) - _FUND_STOP
            if core and core <= words:
                hits.append(n)
        if len(hits) >= 1:
            return min(hits, key=lambda n: len(n)), None
        if llm_name:
            toks = set(re.findall(r"[a-z0-9]+", llm_name.lower())) - _FUND_STOP
            if toks and toks <= words:                          # the model may not invent a fund name
                return resolve_fund_name(llm_name, names), llm_name
        if re.search(r"\b(this|ye|is|isme|iska|us)\b", text.lower()) and s.last_fund:
            return s.last_fund, None
        return None, None

    def _mf_sector(self, s: Session, text: str, llm_name: Optional[str]) -> dict:
        name, unknown = self._find_fund(s, text, llm_name)
        if name is None and unknown is None:
            return self._resp(s, replies.FUND_ASK, "explain_mf_sector")
        if name is None:
            try:
                known = ", ".join(self.engine.known_fund_names())
            except EngineError:
                known = "-"
            return self._resp(s, replies.FUND_UNKNOWN.format(name=unknown, known=known), "explain_mf_sector")
        try:
            row = self.engine.get_sector_allocation(name)
        except EngineError:
            return self._resp(s, replies.ENGINE_DOWN, "explain_mf_sector")
        if row is None:
            return self._resp(s, replies.FUND_NO_DATA.format(name=name), "explain_mf_sector")
        s.last_fund = row["fund_name"]
        table: dict[str, float] = row["sector_json"]
        ordered = sorted(table.items(), key=lambda kv: -kv[1])
        t = text.lower()
        asof = f" (as of {row['date']})" if row.get("date") else ""
        asked = [sec for sec, al in _SECTOR_ALIASES.items() if sec in table and any(
            re.search(rf"\b{re.escape(a)}\b", t) for a in al)]
        if not asked:
            asked = [sec for sec in table if sec.lower() in t]
        if asked:
            sec = asked[0]
            rank = [k for k, _ in ordered].index(sec) + 1
            ans = f"In {row['fund_name']}, {sec} has a weight of {replies.num(table[sec])}%{asof}, which ranks #{rank} among its sectors."
        elif re.search(r"top|sabse\s+(zyada|jyada|bada)|largest|biggest|highest|main|most", t):
            sec, v = ordered[0]
            ans = f"The largest sector in {row['fund_name']} is {sec} at {replies.num(v)}%{asof}."
        else:
            rows = "\n".join(f"{k}: {replies.num(v)}%" for k, v in ordered)
            ans = f"Sector allocation of {row['fund_name']}{asof}:\n{rows}"
        if row.get("source_url"):
            ans += f"\nSource: {row['source_url']}"
        ans = self._polish(ans) if len(ordered) > 0 else ans
        return self._resp(s, ans, "explain_mf_sector")
