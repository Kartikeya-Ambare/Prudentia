"""Single entry point for 'should this message reach the LLM at all?'.

screen(message, awaiting) ->
  1. structural checks (empty / too long / non-Latin script)         [format, not topic]
  2. state-aware slot answer ("3 saal" right after 'kitne saal?')      [parse-based, not keywords]
  3. semantic scope gate (trained on scope_policy.yaml)               [tier 1, policy is data]
  4. if unsure and a judge is given: PolicyJudge reads the written definitions [tier 2, fail-closed]
Returns Screen.action in {"allow", "unsure", "block"}; only allow/unsure may call the intent LLM.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from chat_service.guardrails.chat_guardrails import (
    MAX_CHARS, REFUSALS, _ADVICE, _INJECTION, _NON_LATIN, _SIP, _SUSPICIOUS, _UNSUPPORTED,
    classes_in, looks_like_slot_answer, normalise, words_to_digits,
)
import re

# "<stock/share> bech/kharid..." (verb after the noun, the order _ADVICE does not cover)
_SELL_BUY = re.compile(
    r"\b(stocks?|shares?)\b.{0,15}\b(bech|kharid|sell|buy)\w*"
    r"|\b(which|konsa|kaunsa|kaun\s?sa)\s+(mutual\s+fund|fund|stock|share|mf)s?\s+(should|shall|to\s+(buy|pick|choose)|lu\b|lun\b|lena|kharid)"
    r"|multibagger|\b(share|stock)s?\s+(batao|suggest|recommend)", re.I)
_ADVICE_MORE = re.compile(
    r"\b(is|are|was)\b.{0,40}\b(good|bad|worth|safe)\b.{0,12}\b(buy|investment|invest|stock|share|bet|pick)\b"
    r"|\b(undervalued|overvalued|penny\s+stocks?)\b|\bgood\s+(stock|share)s?\b"
    r"|\b(sell|bech\w*)\b.{0,10}\b(karun|karu|ya|or)\b.{0,15}\b(hold|sell|bech\w*|rakh\w*)\b"
    r"|\b(double|triple|teen\s+guna|dugna)\b.{0,30}\b(tarika|kaise|how|way|trick)\b|\bpaisa\s+(jaldi\s+)?(double|dugna)\b"
    r"|\b(right|good|best)\s+time\s+to\s+(buy|invest|enter|sell)\b|\bshould\s+i\s+(invest|buy|sell)\s+in\b"
    r"|\b(recommend|suggest)\w*\b.{0,25}\b(stocks?|shares?|funds?|mutual\s+funds?|mf)\b"
    r"|\b(give|share|send|get|need|want|tell)\b.{0,15}\b(me\s+)?(a\s+|one\s+|some\s+|any\s+)?(tips?|hot\s+tip|suggestions?)\b"
    r"|\bpromis\w*\b.{0,25}\b(returns?|profit|gains?|\d+\s*%)", re.I)
# 'the best stock', 'top 3 funds', 'which fund has the best returns': a pick, unless it is about the user's own plan
_BEST_PICK = re.compile(
    r"\b(best|top|hottest|greatest)\s+(performing\s+|performer\s+)?(\d+\s+|three\s+|five\s+|ten\s+)?(stocks?|shares?|mutual\s+funds?|funds?|mf)\b"
    r"|\bwhich\s+(mutual\s+fund|fund|stock|share|mf)s?\b.{0,30}\b(best|highest|top|better|good|most)\b", re.I)
_ABOUT_PLAN = re.compile(r"\b(my|this|the|your)\s+(plan|portfolio|allocation|result)\b|\byou\s+(picked|chose|selected|recommended)\b|\bin\s+my\b", re.I)
# hacking, passwords and other security asks: never answered
_SECURITY = re.compile(r"\b(hack\w*|crack\w*|steal\w*|phish\w*|password\w*|passcode|otp|cvv|credentials?|login\s+details|"
                       r"bypass\s+(security|login|auth\w*)|exploit\w*|malware|ransom\w*|ddos|brute\s?force)\b", re.I)
# asking about other users / the previous conversation / internal configuration
_ACTIONS_OUTSIDE_APP = re.compile(
    r"\b(send|email|mail|whatsapp|text)\s+(me|my|this|the)\b.{0,25}\b(email|mail|plan|pdf|report|message|whatsapp)\b|\bemail\s+me\b"
    r"|\b(pay|transfer|wire)\b.{0,20}\b(bill|money|rs|rupees|friend|account|amount\s+to)\b|\b(delete|close|deactivate)\s+(my\s+)?account\b", re.I)
_OTHERS = re.compile(
    r"\b(other|another|previous|last|dusre|doosre)\s+(user|users|customer|customers|person|people|client|logon)\b"
    r"|\bsomeone\s+else'?s?\s+(plan|portfolio|data|account|profile)\b|\b(user|users)'?s?\s+(portfolio|plan|data)\b"
    r"|\bprofile\s*id\b.{0,30}\b(someone|other|another)\b|\b(database|db)\s+(contents?|dump|records?)\b|\bshow\s+(me\s+)?the\s+database\b"
    r"|\bapi\s*keys?\b|\b(your|the)\s+(config|configuration|source\s+code|model\s+name)\b|\bwhich\s+model\s+are\s+you\b", re.I)
# abuse / profanity (English + Hinglish): refused, never answered
_ABUSE = re.compile(
    r"\bf+\W?[u*]+\W?c+k\w*|\bshit\b|\bbitch\w*|\bidiot\b|\bstupid\b|\buseless\b|\bgarbage\b|\bmoron\b|\bdumb\b|\bscrew\s+you\b"
    r"|\b(chutiya|chutiye|madarchod|bhenchod|behenchod|bhosd\w*|gandu|harami|kamina|kutta|kutte|saala|saale|bekaar|bakwaas)\b|\bshut\s+up\b|\bswear\s+at\b|\bhate\s+(you|this)\b",
    re.I)

from chat_service import parse, replies
from chat_service.guardrails.policy_judge import PolicyJudge
from chat_service.guardrails.scope_gate import ScopeGate

_gate: ScopeGate | None = None


def is_plan_edit(text: str) -> bool:
    """Unambiguous edits of the plan (remove/add an asset class, risk %, years, shift money, choose banks, undo). They name an
    asset class, a unit or a bank, so the trained gate need not be asked (it is unsure about 5-word commands)."""
    ops = parse.parse_class_ops(text)
    return bool(ops["remove"] or (ops["add"] and ops["explicit"]) or parse.parse_risk_pct(text) is not None
                or parse.parse_years(text) is not None or parse.parse_move(text) or parse.parse_banks(text)
                or parse.RESTORE.search(text) or parse.parse_amount_delta(text) is not None
                or parse.parse_years_delta(text) is not None or parse.vague_change(text))


# 'i have 2 lakh rupees what should i do with it': a sum of money plus a saving/investing word starts a plan
_INVEST_WORDS = re.compile(r"\b(invest\w*|save|saving|savings|grow|park|paisa|paise|money|rupees?|lakhs?|lacs?|crores?|rs\.?)\b|₹", re.I)
# 'mutual fund ka return kitna hai' / 'what is the return on stocks': a question about the plan's per-class return
_CLASS_RETURN = re.compile(
    r"\b(stocks?|funds?|mutual\s+funds?|mf|fds?|fixed\s+deposits?|banks?)\s+(ka|ki|ke|of)\s+(expected\s+)?returns?\b"
    r"|\b(what|how\s+much|kitna|kya)\b.{0,25}\breturns?\b.{0,20}\b(stocks?|funds?|mutual\s+funds?|mf|fds?|banks?)\b"
    r"|\breturns?\b.{0,12}\b(kitna|kitne|kya)\b", re.I)


def get_gate() -> ScopeGate:
    global _gate
    if _gate is None:
        _gate = ScopeGate()
    return _gate


@dataclass
class Screen:
    action: str                 # allow | unsure | block
    category: str
    message: str | None         # fixed refusal when blocked
    cleaned: str


def screen(message: str, awaiting: Iterable[str] | None = None, gate: ScopeGate | None = None,
           judge: PolicyJudge | None = None) -> Screen:
    cleaned = normalise(message)
    if not cleaned:
        return Screen("block", "empty", REFUSALS["empty"], cleaned)
    if len(cleaned) > MAX_CHARS:
        return Screen("block", "too_long", REFUSALS["too_long"], cleaned)
    if _NON_LATIN.search(cleaned):
        return Screen("block", "unsupported_language", REFUSALS["unsupported_language"], cleaned)
    scan = words_to_digits(cleaned)          # injection is screened BEFORE the slot-answer shortcut
    if _INJECTION.search(scan):
        return Screen("block", "injection", REFUSALS["injection"], cleaned)
    if _SUSPICIOUS.search(scan):
        return Screen("block", "suspicious", REFUSALS["suspicious"], cleaned)
    # tier 0: high-precision category patterns (SIP / stock tips / assets the app does not cover)
    if _SIP.search(scan):
        return Screen("block", "sip_unsupported", REFUSALS["sip_unsupported"], cleaned)
    if _ADVICE.search(scan) or _SELL_BUY.search(scan) or _ADVICE_MORE.search(scan) \
            or (_BEST_PICK.search(scan) and not _ABOUT_PLAN.search(scan)):
        return Screen("block", "no_tips", REFUSALS["no_tips"], cleaned)
    if _ACTIONS_OUTSIDE_APP.search(scan):
        return Screen("block", "unsupported_topic", REFUSALS["unsupported_topic"], cleaned)
    if _OTHERS.search(scan) or _SECURITY.search(scan):
        return Screen("block", "injection", REFUSALS["injection"], cleaned)
    if _ABUSE.search(scan):
        return Screen("block", "abusive", REFUSALS["off_topic"], cleaned)
    if _UNSUPPORTED.search(scan):
        return Screen("block", "unsupported_topic", REFUSALS["unsupported_topic"], cleaned)
    if replies.glossary_answer(cleaned):                              # 'what is diversification?': a term this app explains
        return Screen("allow", "in", None, cleaned)
    if _CLASS_RETURN.search(scan):
        return Screen("allow", "in", None, cleaned)
    aw = set(awaiting or ())
    if "move_amount" in aw and parse.parse_move_amount(scan):          # 'all' / 'half' / '10%' / '5000' after 'how much?'
        return Screen("allow", "slot_answer", None, cleaned)
    if aw & {"move_source", "move_dest"} and len(classes_in(cleaned)) == 1:
        return Screen("allow", "slot_answer", None, cleaned)
    if looks_like_slot_answer(cleaned, awaiting or ()):
        return Screen("allow", "slot_answer", None, cleaned)
    d = (gate or get_gate()).decide(cleaned)
    if is_plan_edit(scan) and d.action != "block":           # a confident 'off-topic/creative' verdict still wins
        return Screen("allow", "plan_edit", None, cleaned)
    if d.action == "block" and d.label == "off_topic" and parse.parse_amount(scan) is not None and _INVEST_WORDS.search(scan):
        return Screen("allow", "plan_edit", None, cleaned)
    if d.action == "unsure" and judge is not None:          # tier 2: LLM reads the written policy
        j = judge.judge(cleaned)
        return Screen("allow" if j.label == "in" else "block", j.label, j.refusal, cleaned)
    return Screen(d.action, d.label, d.refusal, cleaned)
