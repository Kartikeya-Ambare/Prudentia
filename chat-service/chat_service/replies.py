"""Fixed reply templates (English only) and the static glossary. No model writes any of this text.

Users may TYPE English or Hinglish (the parsers understand both); every reply the service produces is English."""
from __future__ import annotations

import re
from typing import Optional

DISCLAIMER = "Illustrative allocation, not SEBI-registered investment advice."
BUCKET_LABEL = {"stock": "Stocks", "mf": "Mutual Funds", "bank": "FD"}
CLASS_LABEL = {"stocks": "Stocks", "mf": "Mutual Funds", "fd": "FD"}


def inr(x: float) -> str:
    """Indian digit grouping: 500000 -> '₹5,00,000'."""
    n = int(round(x))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-" if n < 0 else "") + "₹" + s


def num(x: float) -> str:
    return f"{x:g}"


def years_text(y: float) -> str:
    return f"{num(y)} {'year' if y == 1 else 'years'}"


def asof_text(d) -> str:
    """The plan API sends {stocks: date, mf: date}; the old /allocate sent one string."""
    if isinstance(d, dict):
        vals = {k: v for k, v in d.items() if v}
        if len(set(vals.values())) == 1:
            return next(iter(vals.values()))
        return ", ".join(f"{k} {v}" for k, v in vals.items()) or "unknown"
    return str(d)


# ------------------------------------------------------------------------------ messages with fields
M: dict[str, str] = {
    "last_class": "A plan needs at least one asset class (stocks, mutual funds or FD), so I can't remove the last one.",
    "class_absent": "{c} isn't in your plan, so there is nothing to remove.",
    "conflict": "That message asks for conflicting changes to the {what}, so I changed nothing. Please send one change at a time.",
    "amount_nonpos": "The amount can't be zero or negative.",
    "risk_range": "Risk must be between 0% and 100% (low is 20, moderate is 50 and high is 80).",
    "bank_unknown": "I don't have a bank called '{name}'. You can pick from: {names}.",
    "bank_ask": ("Which banks would you like for the FD? For example, 'use SBI and HDFC for the FD'. "
                 "Available banks: {names}. Or say 'banks auto' and I will pick the best five."),
    "bank_no_fd": "Your plan has no FD right now, so there are no banks to pick. Say 'add FD' first.",
    "bank_last": "At least one bank has to stay in the plan.",
    "no_money_in": "There is no money in {c} right now, so nothing can be moved out of it.",
    "need_plan": "Let's create a plan first. Tell me the amount, the number of years and your risk level, and then I can do that.",
    "rejected": "That change couldn't be applied: {detail}",
    "years_rounded": "Years are whole numbers here, so {a} became {b}.",
    "engine_down": "The allocation service isn't available right now. Please try again in a bit.",
    "no_change": "Nothing changed. What would you like to change? For example, 'make it 10 years' or 'remove FD'.",
    "not_sure": "I wasn't sure about: {what}.",
    "risk_capped": "Your risk is already {moved}, so it can't go any further.",
    "risk_level": "Your risk level is {label}.",
}


def t(key: str, lang: Optional[str] = None, **kw) -> str:   # `lang` kept for call-site compatibility; replies are English only
    return M[key].format(**kw)


# ------------------------------------------------------------------------------ intake questions
ASK = {
    "amount": "How much would you like to invest? For example, 5 lakh.",
    "years": "For how many years? For example, 3 years.",
    "risk": "How much risk are you comfortable with: low, moderate or high, or a number like 35%? "
            "If you're not sure, just say so.",
}
SLOT_ORDER = ("amount", "years", "risk")


def ask_for(missing: list[str], lang: Optional[str] = None) -> tuple[str, list[str]]:
    """At most 2 questions per turn, always in the order amount -> years -> risk."""
    todo = [m for m in SLOT_ORDER if m in missing][:2]
    return " ".join(ASK[m] for m in todo), todo


def limit_msg(slot: str, lim, lang: Optional[str] = None, nonpositive: bool = False) -> str:
    if slot == "amount":
        head = (M["amount_nonpos"] + " ") if nonpositive else ""
        return (head + f"The amount must be between {inr(lim.amount_min)} and {inr(lim.amount_max)}. "
                "Please include a unit, for example 5 lakh or 50000. " + ASK["amount"])
    return f"Years must be between {lim.years_min} and {lim.years_max}. " + ASK["years"]


# ------------------------------------------------------------------------------ risk scenarios
SCENARIOS = [
    ("Let's do three quick questions to gauge your comfort with risk. First: imagine your 1 lakh investment drops to "
     "80,000 within a month. What would you do? A) Sell everything  B) Wait and hold  C) Buy more"),
    ("Second: which return profile do you prefer? A) A fixed 7%  B) Somewhere between 5% and 12%  "
     "C) Anywhere from -10% to +25%, with bigger ups and downs"),
    ("Third: will you need this money in the next 2 to 3 years? A) Yes, definitely  B) Maybe  "
     "C) No, it is for the long term"),
]
_L = {"a": 0, "1": 0, "b": 1, "2": 1, "c": 2, "3": 2}
_KW = [  # keyword answers: English and Hinglish are both understood
    [(r"bech|sell|nikal|exit", 0), (r"wait|ruk|hold|dekh", 1), (r"aur\s+kharid|buy|more|kharid", 2)],
    [(r"pakka|fixed|guarantee", 0), (r"5.*12|range|beech|between", 1), (r"-?\s*10|25|utaar|zyada|bigger", 2)],
    [(r"haan|yes|zaroor|definitely|chahiye\s+hoga", 0), (r"shayad|maybe|possibly", 1), (r"nahi|no\b|long|goal|retire", 2)],
]


def parse_scenario_answer(step: int, text: str) -> Optional[int]:
    t = text.strip().lower()
    m = re.fullmatch(r"(?:option\s*)?([abc123])[).]?", t)
    if m:
        return _L[m.group(1)]
    for rx, pts in _KW[step]:
        if re.search(rx, t):
            return pts
    return None


def risk_from_points(points: int) -> str:
    return "low" if points <= 2 else "moderate" if points <= 4 else "high"


RISK_RETRY = "Sorry, I didn't get that. Please choose A, B or C."
RISK_FALLBACK = "That's okay. Just tell me directly: is your risk low, moderate or high?"

# ------------------------------------------------------------------------------ misc templates
CLARIFY_GENERIC = "Could you say a little more? For example, '5 lakh, 3 years, low risk' or 'make it 10 years'."
LLM_DOWN = "Sorry, I couldn't understand that. Please keep it simple, for example '5 lakh, 3 years, low risk'."
NEED_ALLOCATION = M["need_plan"]
MAX_TURNS = "This conversation has reached its limit. Please start a new chat."
CONFIRM_ASK = "Do you still want to go ahead? (yes / no)"
CONFIRM_DECLINED = "Okay, I haven't made that change. Your previous plan is unchanged."
NOTHING_PENDING = "There is nothing waiting for your confirmation."
NOTHING_TO_RESTORE = "There is no earlier plan to go back to."
RESTORED = "I have restored your previous plan."
NO_CHANGE = M["no_change"]
ENGINE_DOWN = M["engine_down"]
FUND_ASK = "Which mutual fund would you like to see the sector allocation for? Please type the fund name."
FUND_UNKNOWN = "I couldn't find the fund '{name}'. Please check the spelling or pick one of these: {known}."
FUND_NO_DATA = "Sector data for {name} isn't available right now."
MOVE_UNCLEAR = ("Where should the money move from and to, and how much? For example, 'move 10% from stocks to FD' "
                "or 'move 5000 from stocks to FD'.")
SAME_BUCKET = "The source and destination are the same, so nothing will move."
ASK_APP = ("I can explain terms such as mutual fund, FD, large, mid and small cap, risk score and expected return. "
           "Which one would you like to know about?")


# ------------------------------------------------------------------------------ allocation reply
def allocation_reply(res: dict, risk_label: str, changes: list[str] | None = None) -> str:
    """A short lead for the plan card the frontend draws from `result`: no breakdown, no projections, no disclaimer."""
    lead = f"Here is your plan for {inr(res['amount'])} over {years_text(res['years'])} at {risk_label} risk."
    if changes:
        lead = "Updated: " + "; ".join(changes) + ". " + lead
    notes = " ".join(f"Note: {w}" for w in res.get("warnings") or [])
    return lead + (" " + notes if notes else "")


# ------------------------------------------------------------------------------ glossary
_DEF_CUE = re.compile(r"\b(kya\s+(hota|hai|hain|hoti)|what\s+(is|are|does|do)|matlab|meaning|farak|difference|"
                      r"define|explain|samjha\w*|means?|kise\s+kehte)\b", re.I)
_MINE = re.compile(r"\b(my|mera|meri|mere|apna|apni|isme|iska|iski|this|is\s+portfolio|hamara)\b", re.I)

GLOSSARY: list[tuple[str, str, str]] = [
    ("mutual fund", r"mutual\s+funds?|\bmfs?\b",
     "A mutual fund pools money from many investors, and a fund manager invests it in stocks or bonds. "
     "You get units, and their value moves up and down with the market."),
    ("FD", r"\bfds?\b|fixed\s+deposits?",
     "An FD (fixed deposit) is money you keep with a bank for a fixed period at a fixed interest rate. "
     "It carries low risk, and the return is usually lower than stocks."),
    ("large cap", r"large\s*caps?",
     "Large cap means shares or funds of big, established companies. They usually swing less and grow steadily."),
    ("mid cap", r"mid\s*caps?",
     "Mid cap means mid-sized companies. They can grow faster than large caps, but they carry more risk."),
    ("small cap", r"small\s*caps?",
     "Small cap means small companies. They have the most room to grow, along with the biggest ups and downs."),
    ("risk score", r"risk\s+(score|level|thermometer)",
     "The risk score is a number from 0 to 100 showing how much ups and downs you can handle. Here low is 20, "
     "moderate is 50 and high is 80. A higher score means more of your money goes into stocks."),
    ("P5/P95", r"\bp\s?5\b|\bp\s?95\b|\bp5\s*/\s*p95\b",
     "P5 and P95 describe a range of possible results. P5 is a bad case (only 5 times in 100 would the result be lower) "
     "and P95 is a good case (only 5 times in 100 would it be higher). It is an estimate, not a guarantee."),
    ("expected return", r"expected\s+returns?|expected\s+value",
     "Expected return is the modelled average yearly return. The actual return can be lower or higher."),
]


_NOT_GLOSSARY = re.compile(r"\b(sectors?|exposed|exposure|holdings?|allocation|portfolio|split|drift\w*|rebalanc\w*)\b", re.I)


GLOSSARY.append(("scenarios", r"\b(bear|bull|base)\s+case\b|\bscenarios?\b",
                 "Bear, base and bull are three modelled scenarios for your plan: a weak market, an average market and a strong market. "
                 "They are estimates of what could happen, not guarantees."))

# common questions asked without a 'what is' cue (answered with fixed, non-advisory text)
EXTRA_QA: list[tuple[str, str]] = [
    (r"\bis\s+(an?\s+)?(fd|fixed\s+deposit)s?\s+(safe|risky|secure)|\b(fd|fixed\s+deposit)s?\s+(safe|surakshit)\s+(hai|hota|hoti)\b",
     "An FD is generally considered low risk: it pays a fixed interest rate that is known in advance. The trade-off is that returns "
     "are usually lower than stocks, and breaking an FD early can cost you some interest. Tell me your risk level and I will build a plan."),
    (r"\b(market|stocks?|shares?)\s+(falls?|fell|crash\w*|goes?\s+down|drops?)\b|\bplan\s+loses\b|\blos(e|ing)\s+(money|value)\b|\bgir\s+jaye|\bgirta\b|\bnuksan\b",
     "If markets fall, the stocks and mutual funds in your plan can lose value too, sometimes for a long time. FDs keep their fixed interest. "
     "The Bear, Base and Bull scenarios in your plan show a range of possible outcomes; they are estimates, not guarantees. "
     "A lower risk level puts more of your money in FDs."),
]


def glossary_answer(text: str) -> Optional[str]:
    for rx, ans in EXTRA_QA:
        is_question = "?" in text or re.match(r"\s*(is|are|what|kya|how|will|does|can)\b", text, re.I)
        if re.search(rx, text, re.I) and is_question:
            return ans
    if not _DEF_CUE.search(text) or _MINE.search(text) or _NOT_GLOSSARY.search(text):
        return None
    hits = [ans for _, rx, ans in GLOSSARY if re.search(rx, text, re.I)]
    if not hits:
        return None
    return "\n\n".join(hits[:3])
