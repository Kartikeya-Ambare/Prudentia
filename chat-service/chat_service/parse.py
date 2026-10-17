"""Deterministic parsers for the slots and rebalance moves. These run BEFORE any LLM extractor: when the
user's own words contain the value, code reads it (cheaper, and it cannot invent anything).
The LLM is only asked when the rules found nothing.
"""
from __future__ import annotations

import re
from typing import Optional

from chat_service.guardrails.chat_guardrails import (
    classes_in, normalise, risk_from_words, words_to_digits, years_in,
)

# ------------------------------------------------------------------------------ amount
_AMT = re.compile(
    r"(?P<neg>(?<![\w.,])[-\u2212]\s*|\bminus\s+)?(?P<cur>(?<![a-z])(?:₹|rs\.?|inr))?\s*(?P<num>\d+(?:,\d{2,3})*(?:\.\d+)?)\s*"
    r"(?P<unit>k|lakhs?|lacs?|l|crores?|cr|hazaa?r|hajar|thousand)?(?![a-z])", re.I)
_MULT = {"k": 1e3, "thousand": 1e3, "hazaar": 1e3, "hazar": 1e3, "hajar": 1e3, "lakh": 1e5, "lakhs": 1e5,
         "lac": 1e5, "lacs": 1e5, "l": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7}
_NOT_AMOUNT_TAIL = re.compile(r"^\s*(%|percent|pratishat|prati\s?shat|saal|saalon|sal|year|years|yr|yrs|varsh|y\b|mahine|months?)", re.I)
_CHANGE_CUE = re.compile(r"\b(from|to|se|instead|badal\w*)\b", re.I)            # 'from 5 years to 10 years': the last value is the new one
_CORRECTION = re.compile(r"\b(nahi|nahin|nhi|no|not|actually|sorry|i\s+mean|matlab|oops|galat|correction)\b", re.I)


def _candidates(text: str, allow_bare: bool) -> list[float]:
    t = words_to_digits(normalise(text))
    out: list[float] = []
    for m in _AMT.finditer(t):
        if not m.group("unit") and _NOT_AMOUNT_TAIL.match(t[m.end():]):     # '5 years' is not an amount, '5 lakh years 5' is
            continue
        val = float(m.group("num").replace(",", ""))
        unit = m.group("unit")
        if unit:
            val *= _MULT[unit.lower()]
        elif not (m.group("cur") or val >= 1000 or allow_bare):
            continue
        out.append(round(-val if m.group("neg") else val, 2))
    return out


_AMOUNT_CUE = re.compile(r"\b(amount|capital|principal|corpus|budget)\b\s*(?:to|=|:|of|is|ko|hai)?\s*(?:rs\.?\s*|₹|inr)?\s*"
                         r"(?P<num>\d[\d,]*(?:\.\d+)?)(?!\s*(?:%|percent|saal|sal|years?|yrs?|lakhs?|lacs?|crores?|cr|k\b))", re.I)


def parse_amount(text: str, allow_bare: bool = False) -> Optional[float]:
    """Rupee amount in the text. Several different amounts count only when a correction marker is present
    ('5 lakh, nahi 6 lakh' -> the LAST one); otherwise None (ambiguous, ask)."""
    c = _candidates(text, allow_bare)
    if not c:
        cue = _AMOUNT_CUE.search(text)                         # 'amount 100': the word says that bare number is rupees
        if cue:
            c = [float(cue.group("num").replace(",", ""))]
    if not c:
        return None
    if len(set(c)) == 1:
        return c[0]
    return c[-1] if (_CORRECTION.search(text) or _CHANGE_CUE.search(text)) else None


# ------------------------------------------------------------------------------ years
def parse_years(text: str, allow_bare: bool = False) -> Optional[float]:
    t = words_to_digits(normalise(text))
    ys = [m for m in re.findall(r"(\d+(?:\.\d+)?)\s*(?:saalon|saal|sal|varsh|years?|yrs?|yr|y)(?![a-z])", t, re.I)]
    vals = [round(float(v), 2) for v in ys]
    if not vals:
        vals = [round(float(v), 2) for v in re.findall(
            r"\b(?:years?|saal|sal|horizon|varsh)\s*(?:to|=|:|ko)?\s*(\d+(?:\.\d+)?)\b(?!\s*(?:%|percent|lakh|lac|k\b|cr))", t, re.I)]
    if not vals and allow_bare:
        m = re.fullmatch(r"\s*(\d{1,2}(?:\.\d)?)\s*", t)
        if m:
            vals = [round(float(m.group(1)), 2)]
    if not vals:
        return None
    if len(set(vals)) == 1:
        return vals[0]
    return vals[-1] if (_CORRECTION.search(text) or _CHANGE_CUE.search(text)) else None


# ------------------------------------------------------------------------------ relative changes ('add 2 lakh', '2 more years')
_UP_V = re.compile(r"\b(increase|raise|add|top\s*up|extend|badha\w*|jod\w*|aur\s+(?:daal|dal|add|jod)\w*)\b", re.I)
_DOWN_V = re.compile(r"\b(decrease|reduce|lower|cut|ghata\w*|kam\s+kar\w*|shorten)\b", re.I)
_UNIT_MORE = re.compile(r"(?:\d|lakhs?|lacs?|crores?|\bk|rupees?|rs\.?)\s+(more|extra|aur|less|kam)\b", re.I)
_ABS_TO = re.compile(r"\b(?:to|ko|=)\s*(?:rs\.?\s*|₹)?\d", re.I)


def _sign(text: str) -> int:
    up, down = bool(_UP_V.search(text)), bool(_DOWN_V.search(text))
    return 1 if up and not down else -1 if down and not up else 0


def parse_amount_delta(text: str) -> Optional[float]:
    """'amount badhao 2 lakh' / 'add 1 lakh more' -> +200000 / +100000; 'reduce the amount by 50000' -> -50000.
    None when the text sets an absolute amount ('make it 6 lakh', 'increase it to 8 lakh')."""
    a = parse_amount(text)
    sign = _sign(text)
    um = _UNIT_MORE.search(text)
    if not sign and um:
        sign = -1 if um.group(1).lower() in ("less", "kam") else 1
    if a is None or not sign or (_ABS_TO.search(text) and not re.search(r"\bby\b", text, re.I)):
        return None
    return sign * a


def parse_years_delta(text: str) -> Optional[float]:
    """'add 2 more years' / '3 saal aur' -> +2 / +3; 'reduce by 2 years' -> -2. None for an absolute number of years."""
    t = words_to_digits(normalise(text))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(more\s+|extra\s+|additional\s+|aur\s+)?(?:saalon|saal|sal|varsh|years?|yrs?|yr)(?![a-z])", t, re.I)
    if not m:
        m = re.search(r"\b(?:years?|yrs?|saal|sal)\s+(?:by|ko)\s+()(\d+(?:\.\d+)?)", t, re.I)
        if m:
            sign = _sign(t)
            return sign * float(m.group(2)) if sign else None
    sign = _sign(t) or (1 if m and m.group(2) else 0)
    if not m or not sign or (_ABS_TO.search(t) and not re.search(r"\bby\b", t, re.I)):
        return None
    return sign * float(m.group(1))


_VAGUE_VERB = re.compile(r"\b(increase|raise|extend|badha\w*|decrease|reduce|lower|shorten|ghata\w*|kam\s+kar\w*)\b", re.I)


def vague_change(text: str) -> Optional[str]:
    """'years badha do' / 'increase the amount' with no number: which input the user wants changed ('years' or 'amount')."""
    t = normalise(text)
    if not _VAGUE_VERB.search(t) or re.search(r"\d", words_to_digits(t)) or re.search(r"\b(risk|stocks?|funds?|fds?|mf)\b", t, re.I):
        return None
    if re.search(r"\b(years?|saal|sal|horizon|duration|period)\b", t, re.I):
        return "years"
    if re.search(r"\b(amount|capital|principal|investment|rupees?|paisa|paise)\b", t, re.I):
        return "amount"
    return None


# ------------------------------------------------------------------------------ questions
_Q_START = re.compile(r"^\s*(is|are|was|were|does|do|did|will|would|should|can|could|how|what|why|which|kya|kaun|kyun|kaise)\b", re.I)
_REQUEST = re.compile(r"\b(please|plz|pls|make|keep|change|set|want|need|put|take|reduce|lower|raise|increase|decrease|switch|turn|"
                      r"can\s+you|could\s+you|would\s+you|karo|kar\s+do|banao|chahiye)\b", re.I)


def is_question(text: str) -> bool:
    """A question about the plan ('is my money safe?'), as opposed to a request to change it ('make it safer')."""
    t = normalise(text)
    return bool(_Q_START.match(t) or t.endswith("?")) and not _REQUEST.search(t)


_RISK_BARE = re.compile(r"\b(low|moderate|medium|high|conservative|aggressive|balanced|kam|madhyam)\b"
                        r"(?!\s+(growth|returns?|yield|interest|rated|cost|fees?|price|priced))", re.I)
_RISK_BARE_MAP = {"low": "low", "kam": "low", "conservative": "low", "moderate": "moderate", "medium": "moderate",
                  "madhyam": "moderate", "balanced": "moderate", "high": "high", "aggressive": "high"}


def parse_risk_bare(text: str) -> Optional[str]:
    """'5 lakh 5 years moderate': a risk level without the word 'risk'. Only used while the amount or years are in the same message."""
    m = _RISK_BARE.search(text)
    return _RISK_BARE_MAP[m.group(1).lower()] if m else None


# ------------------------------------------------------------------------------ risk
_RISK_EXTRA = re.compile(r"\b(conservative|aggressive|balanced|safest|safe)\b", re.I)
_DONT_KNOW_RISK = re.compile(r"pata\s+nahi|nahi\s+pata|pata\s+nhi|not\s+sure|don'?t\s+know|dont\s+know|no\s+idea|samajh\s+nahi|confused", re.I)
RISK_SCORE = {"low": 20, "moderate": 50, "high": 80}
RISK_ORDER = ["low", "moderate", "high"]


def risk_to_score(label: str) -> int:
    """The ONE mapping from the user's risk word to the engine's risk_score."""
    return RISK_SCORE[label]


def parse_risk(text: str) -> Optional[str]:
    r = risk_from_words(text)
    if r:
        return r
    m = _RISK_EXTRA.search(text)
    if m and re.match(r"\s*(is|are|does|do|kya|what|how|why|can)\b", text, re.I):
        return None                                          # a question about 'safe', not a risk answer
    if m:
        w = m.group(1).lower()
        return "high" if w == "aggressive" else "moderate" if w == "balanced" else "low"
    return None


def risk_unknown(text: str) -> bool:
    return bool(_DONT_KNOW_RISK.search(text))


_RELATIVE = re.compile(r"\b(thoda|thodi|thode|bit|little|slightly|somewhat|aur|more|less|safer|riskier|lower|higher|"
                       r"increase|decrease|reduce|raise|boost|bump|cut)\b", re.I)
_SAFER_W = re.compile(r"\b(safe|safer|safest|kam|kum|low|lower|less|conservative|ghat\w*|reduce|decrease|secure)\b", re.I)
_RISKIER_W = re.compile(r"\b(zyada|jyada|jyaada|high|higher|more|aggressive|riskier|risky|badh\w*|increase)\b", re.I)
_RISKISH = re.compile(r"\b(risk\w*|safe\w*|aggressive|conservative|secure)\b", re.I)


def parse_risk_shift(text: str) -> Optional[str]:
    """'thoda safe karo' / 'make it safer' -> 'safer'; 'thoda aggressive banao' -> 'riskier'. Relative changes only."""
    t = normalise(text)
    if not _RISKISH.search(t) or is_question(t):          # 'is my money safe?' asks; it does not change the plan
        return None
    relative =bool(_RELATIVE.search(t)) or bool(re.search(r"\b(safer|riskier|safe|aggressive)\b", t, re.I))
    if not relative:
        return None
    if re.search(r"\b(safer|safe|safest|secure|less\s+risk\w*|kam\s+risk\w*|lower\s+risk|(reduce|decrease|cut|lower)\s+(the\s+|my\s+)?risk)\b|"
                 r"\brisk\W+(?:\w+\W+){0,2}?(kam|kum|ghat\w*|less|lower)\b", t, re.I) \
            and not re.search(r"\b(riskier|aggressive)\b", t, re.I):
        return "safer"
    if re.search(r"\b(riskier|risky|aggressive|more\s+risk\w*|zyada\s+risk\w*|jyada\s+risk\w*|higher\s+risk|(increase|raise|boost|bump(\s+up)?)\s+(the\s+|my\s+)?risk)\b|"
                 r"\brisk\W+(?:\w+\W+){0,2}?(zyada|jyada|badh\w*|more|higher)\b", t, re.I):
        return "riskier"
    return None


def shift_risk(current: Optional[str], shift: str) -> Optional[str]:
    if current not in RISK_ORDER:
        return None
    i = RISK_ORDER.index(current) + (-1 if shift == "safer" else 1)
    return RISK_ORDER[max(0, min(2, i))]


# ------------------------------------------------------------------------------ classes
_REMOVE = re.compile(r"\b(hata\w*|hatao|nikal\w*|remove|exclude|drop|without|mat\s+rakho|nahi\s+chahiye|nhi\s+chahiye|"
                     r"band\s+karo|skip|avoid|na\s+rakho|chhod\w*)\b", re.I)
_ADD = re.compile(r"\b(add|also|bhi|include|jodo|jod\s+do|shamil|aur\s+add)\b", re.I)
_ONLY = re.compile(r"\b(only|sirf|bas|just|keval|solely)\b|\b(put|keep)\s+(everything|all)\s+(in|into)\b|\ball\s+(in|into)\b", re.I)
_ALL = re.compile(r"\b(sab|all|teeno|everything|anything|koi\s+bhi|thoda\s+thoda)\b", re.I)


def parse_class_ops(text: str) -> dict:
    """{'only': set, 'add': set, 'remove': set, 'explicit': bool}; at most one set non-empty. Mentions are asset-class words in the text."""
    t = normalise(text)
    mentioned = classes_in(t)
    ops = {"only": set(), "add": set(), "remove": set(), "explicit": True}
    if not mentioned:
        if _ALL.search(t):
            ops["only"] = {"stocks", "mf", "fd"}
            ops["explicit"] = False    # a bare "all" is not a plan change (it is usually the answer to "how much?")
        return ops
    if _REMOVE.search(t):
        ops["remove"] = mentioned
    elif _ONLY.search(t):
        ops["only"] = mentioned
    elif _ADD.search(t):
        ops["add"] = mentioned
    else:
        ops["only"] = mentioned
        ops["explicit"] = False        # bare mention: the caller decides if it means anything in context
    return ops


# ------------------------------------------------------------------------------ rebalance move
_CL = (r"(stocks?|shares?|equit(?:y|ies)|mutual\s+funds?|mfs?|funds?|fds?|fixed\s+deposits?|deposits?|bank|savings)")
_CLS_BUCKET = [(re.compile(r"stock|share|equit", re.I), "stock"),
               (re.compile(r"mutual|^mf|fund", re.I), "mf"),
               (re.compile(r"fd|fixed|deposit|bank|saving", re.I), "bank")]
_MOVE_A = re.compile(rf"(?:from\s+)?\b{_CL}\s+(?:se|to|into|->|→)\s+{_CL}\b", re.I)
_MOVE_B = re.compile(rf"\b{_CL}\s+(?:me|mein|ko|mai)\b.{{0,30}}?\b{_CL}\s+se\b", re.I)
_MOVE_C = re.compile(rf"\b{_CL}\b.{{0,18}}\b(kam|ghata\w*|reduce|decrease|less|lower)\b.{{0,18}}\b{_CL}\b.{{0,14}}\b(badha\w*|increase|more|zyada|higher)\b", re.I)
_MOVE_D = re.compile(rf"\b{_CL}\s+se\s+(?:rs\.?\s*|₹)?[\d,.]+\s*(?:k|lakhs?|lacs?|cr|crores?|%|percent)?\s+{_CL}\s+(?:me|mein|ko)\b", re.I)
_MOVE_E = re.compile(rf"\b(reduce|decrease|cut|lower)\s+{_CL}\b.{{0,18}}\b(increase|add|raise|boost)\s+{_CL}\b", re.I)
_MOVE_F = re.compile(rf"\b{_CL}\s+(?:me|mein)\s+se\b.{{0,25}}?\b{_CL}\s+(?:me|mein|ko)\b", re.I)
_MOVE_G = re.compile(rf"\bto\s+{_CL}\b.{{0,25}}?\bfrom\s+{_CL}\b", re.I)          # 'all money to stocks from mutual funds'
_MOVE_H = re.compile(rf"\b(?:take|pull|withdraw|draw|get)\b.{{0,40}}?\b(?:out\s+of|from)\s+{_CL}\b.{{0,40}}?"
                     rf"\b(?:put|move|add|invest|shift|transfer|keep|place|deposit|park)\b.{{0,25}}?\b(?:in|into|to|towards?)\s+{_CL}\b", re.I)
_MOVE_I = re.compile(rf"\b(?:put|invest|place|park|add)\b.{{0,30}}?\b(?:in|into|to)\s+{_CL}\b.{{0,25}}?\b(?:from|out\s+of)\s+{_CL}\b", re.I)
_LESS_W = r"(?:less|lower|reduce|decrease|cut|fewer|kam)"
_MORE_W = r"(?:more|higher|increase|raise|boost|zyada)"
_NOT_RISK = r"(?:(?!risk).){0,12}?"
_LESS_MORE = re.compile(rf"\b{_LESS_W}\s+{_CL}\b.{{0,25}}?\b{_MORE_W}\s+{_CL}\b", re.I)
_MORE_LESS = re.compile(rf"\b{_MORE_W}\s+{_CL}\b.{{0,25}}?\b{_LESS_W}\s+{_CL}\b", re.I)
_LESS_ONE = re.compile(rf"(?<!\bno\s)(?<!\bnot\s)\b{_LESS_W}\s+{_NOT_RISK}\b{_CL}\b|\b{_CL}\s+(?:kam|ghata\w*)\b", re.I)
_MORE_ONE = re.compile(rf"(?<!\bno\s)(?<!\bnot\s)\b{_MORE_W}\s+{_NOT_RISK}\b{_CL}\b|\b{_CL}\s+(?:badha\w*|zyada)\b", re.I)
_ALL_TO = re.compile(rf"\b(?:all|everything|entire|whole|sab|saara|sara|poora|pura)\s+(?:of\s+)?(?:my\s+|the\s+)?(?:money|paisa|paise|amount|savings|funds|holdings)?\s*(?:to|into|in)\s+{_CL}\b(?!\s*(?:,|&|\+|\band\b|\baur\b)\s*{_CL})", re.I)
_QUESTION_START = re.compile(r"^\s*(what|why|which|how|who|when|is|are|was|does|do|did|kya|kaun|kyun|kaise)\b", re.I)
_ALL_MONEY = re.compile(r"\b(all|everything|entire|whole|sab|saara|sara|poora|pura|sabhi)\b", re.I)
_MOVE_VERB = re.compile(r"\b(move|shift|transfer|switch|convert|swap)\b", re.I)
_MOVE_CUE = re.compile(r"\b(move|shift|transfer|rebalance|daal\w*|dal\s?do|badal\w*|convert|switch|swap|bhej\w*|take|pull|withdraw|park)\b", re.I)
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent|pratishat|prati\s?shat)", re.I)


def _bucket(word: str) -> Optional[str]:
    w = word.strip().lower()
    for rx, b in _CLS_BUCKET:
        if rx.search(w):
            return b
    return None


_SEP = r"(?:,|&|\+|\band\b|\baur\b)"
_MOVE_MULTI_SRC = re.compile(rf"(?:from\s+)?\b{_CL}\s*{_SEP}\s*{_CL}\s+(?:se|to|into|->|→)\s+{_CL}\b", re.I)
_MOVE_MULTI_HI = re.compile(rf"\b{_CL}\s*{_SEP}\s*{_CL}\s+(?:dono\s+)?(?:ka|ke|ki)\s+(?:sab\s+|saara\s+|sara\s+|poora\s+|pura\s+|sabhi\s+)?"
                            rf"(?:paisa|paise|money|amount)?\s*(?:\w+\s+){{0,2}}?{_CL}\s+(?:me|mein|mai|ko)\b", re.I)   # 'fd aur stocks ka sab paisa mf me daalo'
_MOVE_MULTI_DST = re.compile(rf"\b{_CL}\s+(?:se|to|into|->|→)\s+{_CL}\s*{_SEP}\s*{_CL}\b", re.I)


def parse_move(text: str) -> dict:
    """{'from','to','pct','amount'} (values may be None); 'sources' lists every source when money comes from two classes
    and 'multi_dest' is True when it should go to two (not supported: one move at a time). Empty dict if this is not a
    move request."""
    t = words_to_digits(normalise(text))
    mm = _MOVE_MULTI_SRC.search(t) or _MOVE_MULTI_HI.search(t)
    if mm:
        srcs = [b for b in (_bucket(mm.group(1)), _bucket(mm.group(2))) if b]
        dst = _bucket(mm.group(3))
        if len(set(srcs)) == 2 and dst and dst not in srcs:
            pm = _PCT.search(t)
            pct = float(pm.group(1)) if pm else None
            amt = None
            if pct is None:
                c = _candidates(t, allow_bare=True)
                amt = c[-1] if c else None
            out = {"from": srcs[0], "sources": srcs, "to": dst, "pct": pct, "amount": amt}
            if pct is None and amt is None:                  # two sources with no amount: all of both (the user said so by naming two)
                out["all"] = True
            return out
    md = _MOVE_MULTI_DST.search(t)
    if md:
        dsts = [b for b in (_bucket(md.group(2)), _bucket(md.group(3))) if b]
        src = _bucket(md.group(1))
        if src and len(set(dsts)) == 2 and src not in dsts:
            return {"from": src, "to": None, "pct": None, "amount": None, "multi_dest": True}
    m = _MOVE_A.search(t)
    src = dst = None
    mg = _MOVE_G.search(t)
    mh, mi = _MOVE_H.search(t), _MOVE_I.search(t)
    if mh:                                               # 'take 25000 out of FD and put it in mutual funds'
        src, dst = _bucket(mh.group(1)), _bucket(mh.group(2))
    elif mi:                                             # 'put 5000 into stocks from FD'
        dst, src = _bucket(mi.group(1)), _bucket(mi.group(2))
    elif m:
        src, dst = _bucket(m.group(1)), _bucket(m.group(2))
    elif mg:
        dst, src = _bucket(mg.group(1)), _bucket(mg.group(2))
    else:
        m2 = _MOVE_B.search(t)
        m3 = _MOVE_C.search(t)
        m4 = _MOVE_D.search(t)
        m6 = _MOVE_F.search(t)
        if m6 and not (m2 or m4):
            src, dst = _bucket(m6.group(1)), _bucket(m6.group(2))
        elif m4:
            src, dst = _bucket(m4.group(1)), _bucket(m4.group(2))
        elif m2:
            dst, src = _bucket(m2.group(1)), _bucket(m2.group(2))
        elif m3:
            src, dst = _bucket(m3.group(1)), _bucket(m3.group(3))
        else:
            m5 = _MOVE_E.search(t)
            if m5:
                src, dst = _bucket(m5.group(2)), _bucket(m5.group(4))
    soft = False                                          # 'less stocks more fd' / 'more mutual funds': a move without the verb
    if not (src and dst):
        mj, mk = _LESS_MORE.search(t), _MORE_LESS.search(t)
        if mj:
            src, dst, soft = _bucket(mj.group(1)), _bucket(mj.group(2)), True
        elif mk:
            dst, src, soft = _bucket(mk.group(1)), _bucket(mk.group(2)), True
    if not src and not dst:
        ma = _ALL_TO.search(t)
        if ma:                                           # 'all money to fd': everything held elsewhere goes to that class
            dst, soft = _bucket(ma.group(1)), True
    if not (src or dst) and not _QUESTION_START.match(t):
        ml, mm = _LESS_ONE.search(t), _MORE_ONE.search(t)
        if ml and not mm:
            src, soft = _bucket(ml.group(1) or ml.group(2)), True
        elif mm and not ml:
            dst, soft = _bucket(mm.group(1) or mm.group(2)), True
    if not (src or dst) and _MOVE_VERB.search(t):       # only one end named: 'move 10% to stocks' / 'move 5000 from fd'
        mt = re.search(rf"\bto\s+{_CL}\b", t, re.I) or re.search(rf"\b{_CL}\s+(?:me|mein|ko|mai)\b", t, re.I)
        mf = re.search(rf"\bfrom\s+{_CL}\b", t, re.I) or re.search(rf"\b{_CL}\s+se\b", t, re.I)
        dst = _bucket(mt.group(1)) if mt else None
        src = _bucket(mf.group(1)) if mf else None
    if not (src and dst) and not (soft or _MOVE_CUE.search(t)):
        return {}
    if not (src or dst) :
        return {}
    pm = _PCT.search(t)
    pct = float(pm.group(1)) if pm else None
    amount = None
    if pct is None:
        stripped = t
        c = _candidates(stripped, allow_bare=True)
        amount = c[-1] if c else None
    out = {"from": src, "to": dst, "pct": pct, "amount": amount}
    if pct is None and amount is None and (src or dst) and _ALL_MONEY.search(t):
        out["all"] = True                                    # 'move all money from mutual funds to stocks'
        if dst and not src:                                  # 'move everything to FD': from every other class
            others = [b for b in ("stock", "mf", "bank") if b != dst]
            out["from"], out["sources"] = others[0], others
    elif pct is None and amount is None and (src or dst):
        if _HALF.search(t):
            out["fraction"] = 0.5                            # 'shift half of my FD to stocks'
        elif _QUARTER.search(t):
            out["fraction"] = 0.25
    return out


# ------------------------------------------------------------------------------ setting the split ('33 33 33', '70% in fd')
_SPLIT_WORD = re.compile(r"\b(split|ratio|allocation|distribution|divide|divided|distribute|baanto|bant\w*|breakdown)\b", re.I)
_EQUAL = re.compile(r"\b(equal|equally|even|evenly|barabar|samaan|sama)\b", re.I)
_TRIPLE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*%?\s*(?:/|,|:|-|\s)\s*(\d+(?:\.\d+)?)\s*%?\s*(?:/|,|:|-|\s)\s*(\d+(?:\.\d+)?)\s*%?(?![\d.])")
_CLASS_PCT = re.compile(rf"\b{_CL}\s*(?:to|=|:|at|ko|ho|@|-)?\s*(\d+(?:\.\d+)?)\s*(?:%|percent)|"
                        rf"(\d+(?:\.\d+)?)\s*(?:%|percent)\s*(?:of\s+(?:it|my\s+money|the\s+plan|everything)\s+)?(?:in|into|to|on|me|mein|mai)\s+{_CL}\b", re.I)
_KEY_OF = {"stock": "stocks", "mf": "mf", "bank": "fd"}


def parse_split(text: str) -> dict:
    """The user is setting the split between the asset classes. {} if not; otherwise one of
    {'equal': True} | {'weights': {'stocks': 50, 'mf': 30, 'fd': 20}, 'complete': True} (all three given, in the plan's order
    when they are bare numbers) | {'weights': {'fd': 70}, 'complete': False} (the rest is shared by the others)."""
    t = words_to_digits(normalise(text))
    if re.search(r"\brisk\b", t, re.I) or parse_move(t) or _REMOVE.search(t):
        return {}
    if _QUESTION_START.match(t) or re.search(r"\b(what\s+if|if\s+i|safe|safer|should|would|better|good)\b", t, re.I):
        return {}                                          # a question or a what-if is answered, not applied
    if _EQUAL.search(t) and (_SPLIT_WORD.search(t) or classes_in(t)):
        return {"equal": True}
    m = _TRIPLE.search(t)
    if m and (_SPLIT_WORD.search(t) or "%" in t or re.search(r"\b(percent|pratishat)\b", t, re.I)):
        a, b, c = (float(m.group(i)) for i in (1, 2, 3))
        if 98 <= a + b + c <= 102 and not re.search(r"\b(years?|saal|lakhs?|lacs?|crores?)\b", t, re.I):
            return {"weights": {"stocks": a, "mf": b, "fd": c}, "complete": True}
    found: dict[str, float] = {}
    for mm in _CLASS_PCT.finditer(t):
        cls, val = (mm.group(1), mm.group(2)) if mm.group(1) else (mm.group(4), mm.group(3))
        b = _bucket(cls)
        if b:
            found[_KEY_OF[b]] = float(val)
    if not found or any(not 0 <= v <= 100 for v in found.values()):
        return {}
    return {"weights": found, "complete": len(found) == 3}


_HALF = re.compile(r"\b(half|aadha|adha|aadhe|adhe)\b", re.I)
_QUARTER = re.compile(r"\b(quarter|chauthai|chauthaai)\b", re.I)
_ALL_ONLY = re.compile(r"^\W*(?:the\s+)?(?:all|everything|entire|whole|sab|saara|sara|poora|pura|sabhi|sab\s+kuch|"
                       r"all\s+of\s+it|all\s+the\s+money|all\s+money|whole\s+amount|the\s+lot|full)\W*$", re.I)


def parse_move_amount(text: str) -> dict:
    """The answer to 'how much should I move?': {'all': True} | {'pct': x} | {'amount': x}; {} when it is not an answer.
    A bare number below 1,000 is ambiguous (percent or rupees?) and is not accepted."""
    t = words_to_digits(normalise(text))
    if _ALL_ONLY.match(t):
        return {"all": True}
    if _HALF.search(t):
        return {"fraction": 0.5}            # half of what the source holds (not half of the whole portfolio)
    if _QUARTER.search(t):
        return {"fraction": 0.25}
    pm = _PCT.search(t)
    if pm and 0 < float(pm.group(1)) <= 100:
        return {"pct": float(pm.group(1))}
    c = [v for v in _candidates(t, allow_bare=False) if v > 0]
    return {"amount": c[-1]} if c else {}


# ------------------------------------------------------------------------------ explicit risk %
_RISK_PCT_A = re.compile(
    r"\brisk\w*\s*(?:level|score|percent|%|to|=|:|of|ko|at|hai|rakho|kar\s*do)?\s*(?:to\s+|=\s*|:\s*)?"
    r"(\d{1,3}(?:\.\d+)?)(?![\d,])\s*(?:%|percent|pratishat|prati\s?shat)?(?!\s*(?:lakh|lac|k\b|cr|crore|saal|sal|year|yr|hazaar))", re.I)
_RISK_PCT_B = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(?:%|percent|pratishat|prati\s?shat)\s*(?:risk|jokhim)", re.I)


def parse_risk_pct(text: str, allow_bare: bool = False) -> Optional[float]:
    """'risk 35%', 'risk to 70', '65 percent risk' -> 35 / 70 / 65. Not range-checked here (caller rejects >100).
    allow_bare: the bot just asked for the risk, so a lone '35%' is the answer."""
    t = words_to_digits(normalise(text))
    if allow_bare:
        b = re.fullmatch(r"(\d{1,3}(?:\.\d+)?)\s*(?:%|percent|pratishat)", t, re.I)
        if b:
            return float(b.group(1))
    m = _RISK_PCT_B.search(t) or _RISK_PCT_A.search(t)
    return float(m.group(1)) if m else None


# ------------------------------------------------------------------------------ banks (FD)
# Order matters: longer / more specific names are matched and removed from the text first.
_BANK_ALIASES: list[tuple[str, str]] = [
    ("unionbank", r"union\s+bank(?:\s+of\s+india)?"), ("iob", r"\biob\b|indian\s+overseas(?:\s+bank)?"),
    ("centralbk", r"central\s+bank(?:\s+of\s+india)?"), ("indianb", r"indian\s+bank\b"),
    ("bankindia", r"\bboi\b|bank\s+of\s+india"), ("bankbaroda", r"\bbob\b|bank\s+of\s+baroda|baroda"),
    ("sbin", r"\bsbi\b|state\s+bank(?:\s+of\s+india)?"), ("pnb", r"\bpnb\b|punjab\s+national(?:\s+bank)?"),
    ("hdfcbank", r"\bhdfc(?:\s+bank)?\b"), ("icicibank", r"\bicici(?:\s+bank)?\b"),
    ("axisbank", r"\baxis(?:\s+bank)?\b"), ("kotakbank", r"\bkotak(?:\s+mahindra)?(?:\s+bank)?\b"),
    ("canbk", r"\bcanara(?:\s+bank)?\b"), ("ucobank", r"\buco(?:\s+bank)?\b"),
    ("idfcfirstb", r"\bidfc(?:\s+first)?(?:\s+bank)?\b"), ("indusindbk", r"\bindusind(?:\s+bank)?\b"),
    ("equitas_sfb", r"\bequitas(?:\s+(?:small\s+finance\s+)?bank)?\b"),
    ("suryoday_sfb", r"\bsuryoday(?:\s+(?:small\s+finance\s+)?bank)?\b"),
    ("ujjivan_sfb", r"\bujjivan(?:\s+(?:small\s+finance\s+)?bank)?\b"),
]
_BANK_WORD = re.compile(r"\b(banks?|fds?|fixed\s+deposits?|deposits?)\b", re.I)
_BANK_AUTO = re.compile(r"\b(auto(?:matic(?:ally)?)?|top\s*5|best\s*5|default|recommended)\b.{0,30}\bbanks?\b|"
                        r"\bbanks?\b.{0,30}\b(auto(?:matic(?:ally)?)?|top\s*5|best\s*5|default|recommended|pehle\s+jaise)\b", re.I)
_BANK_QUESTION = re.compile(r"\?|\b(kaunse|kaunsa|kon\s?se|which|kyu|kyun|why|how\s+much|how\s+(does|do|is|are)|kaise|kitna|kitne|what)\b", re.I)
_BANK_ACTION = re.compile(r"\b(chun\w*|choose|select\w*|use|only|sirf|bas|keval|rakho|rakh|lagao|lagana|karo|kar\s+do|set|pick|"
                          r"change|badal\w*|instead|replace|add|jodo|daal\w*|hata\w*|hatao|remove|exclude|drop|nikal\w*|mat)\b", re.I)
_BANK_ALIAS_ACTION = re.compile(r"\b(remove|hata\w*|hatao|nikal\w*|add|jodo|jod\s+do|use|only|sirf|rakho|chun\w*|choose|select|exclude|"
                                r"drop|include|set|replace)\b", re.I)
_NOT_BANK_CONTEXT = re.compile(r"\b(funds?|caps?|mfs?|mutual|schemes?|stocks?|shares?|sectors?|compare|vs|versus|nifty|prudential|"
                               r"bluechip|midcap|smallcap|largecap|flexi|elss)\b", re.I)
_UNKNOWN_BANK = re.compile(r"\b([a-z][a-z&.]{2,}(?:\s+[a-z][a-z&.]{2,})?)\s+(?:small\s+finance\s+)?bank\b", re.I)
_NOT_A_BANK_NAME = {"the", "my", "this", "that", "fd", "fds", "fixed", "deposit", "deposits", "in", "ke", "ka", "ki", "liye", "me",
                    "mein", "from", "of", "any", "other", "all", "only", "sirf", "ye", "wo", "mere", "mera", "apna", "koi",
                    "aur", "and", "or", "kaunse", "which", "best", "top", "auto", "automatic", "default", "use", "choose",
                    "select", "rakho", "chuno", "add", "remove", "hata", "do", "karo", "kar", "set", "for", "with", "and",
                    "stocks", "stock", "mutual", "fund", "funds", "hdfc", "icici", "axis", "kotak", "sbi", "state", "union",
                    "indian", "central", "overseas", "punjab", "national", "canara", "uco", "pnb", "boi", "bob", "small",
                    "finance", "private", "public", "sector", "psu", "bhi", "lagao", "lagana", "chahiye"}


def parse_banks(text: str) -> dict:
    """FD bank choice from the user's own words. Returns one of
      {"mode": "auto"}                          'banks auto kar do', 'top 5 banks wapas'
      {"mode": "set"|"add"|"remove", "ids": [...]}   known banks named ('SBI aur HDFC me FD rakho')
      {"unknown": ["xyz"]}                      a '<name> bank' that is not on the list (with an action cue)
      {}                                        not a bank choice (including questions like 'kaunse banks chune')
    """
    t = normalise(text).lower()
    if _BANK_AUTO.search(t) and not _BANK_QUESTION.search(t):
        return {"mode": "auto"}
    if not _BANK_WORD.search(t):
        # 'remove HDFC', 'add Axis': a bank's name with an action and no 'bank' / 'FD' word. Only for short messages that do not
        # talk about funds or stocks, since HDFC, SBI, Axis and Kotak are also fund houses.
        named = any(re.search(rx, t, re.I) for _, rx in _BANK_ALIASES)
        if not (named and _BANK_ALIAS_ACTION.search(t) and not _NOT_BANK_CONTEXT.search(t) and len(t.split()) <= 7):
            return {}
    if _BANK_QUESTION.search(t) or not _BANK_ACTION.search(t):
        return {}
    ids, rest = [], t
    for bid, rx in _BANK_ALIASES:
        if re.search(rx, rest, re.I):
            ids.append(bid)
            rest = re.sub(rx, " ", rest, flags=re.I)
    mode = "remove" if _REMOVE.search(t) else "add" if _ADD.search(t) else "set"
    unknown = []
    for m in _UNKNOWN_BANK.finditer(rest):
        words = [w for w in m.group(1).split() if w not in _NOT_A_BANK_NAME]   # 'aur qwerty bank' -> 'qwerty'
        if words:
            unknown.append(" ".join(words))
    if ids and unknown:                       # never apply half of a request: refuse and list the valid banks
        return {"unknown": unknown}
    if ids:
        return {"mode": mode, "ids": ids}
    if unknown:
        return {"unknown": unknown}
    asking = re.search(r"\bbanks\b", t) and re.search(r"\b(chun\w*|choose|select\w*|pick|set|change|badal\w*|use)\b", t)
    return {"mode": "ask"} if asking and mode == "set" and not re.search(r"\d", t) else {}


# ------------------------------------------------------------------------------ restore
RESTORE = re.compile(r"\b(pehle\s+wal[aei]|previous|purana|pichla|undo|revert|restore|go\s+back)\b|wapas\s+(do|kar|laga)", re.I)
