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


_NOT_GLOSSARY = re.compile(r"\b(sectors?|exposed|exposure|holdings?|(?<!asset )allocation|portfolio|split|drift\w*|rebalanc\w*)\b", re.I)


GLOSSARY.append(("scenarios", r"\b(bear|bull|base|optimistic|cautious|expected)\s+cases?\b|\bscenarios?\b|\bbear\b.{0,12}\bbull\b|\bbull\b.{0,12}\bbear\b",
                 "Cautious, expected and optimistic (also called bear, base and bull) are three modelled scenarios for your plan: a weak "
                 "market, an average market and a strong market. They are estimates of what could happen, not guarantees."))
GLOSSARY += [
    ("diversification", r"diversif\w*",
     "Diversification means spreading your money across different investments, such as stocks, mutual funds and FDs, so that one "
     "bad investment does not hurt the whole plan. It lowers risk, but it does not remove it."),
    ("asset allocation", r"asset\s+allocation",
     "Asset allocation is how your money is divided between asset classes, here stocks, mutual funds and FDs. It is the biggest "
     "driver of how bumpy or steady your plan is."),
    ("volatility", r"volatil\w*",
     "Volatility measures how much an investment's value swings up and down. Higher volatility means bigger ups and downs. "
     "FDs have almost none; stocks have the most."),
    ("CAGR", r"\bcagr\b|compound\s+annual|annuali[sz]ed\s+returns?",
     "CAGR is the average yearly growth rate that would take an investment from its start value to its end value. It smooths the "
     "ups and downs into one number."),
    ("NAV", r"\bnav\b|net\s+asset\s+value",
     "NAV (net asset value) is the price of one unit of a mutual fund. It is worked out once a day from the value of everything "
     "the fund holds."),
    ("lump sum", r"lump\s?sum",
     "A lump sum means investing the whole amount in one go, instead of in monthly instalments (a SIP). This app plans lump-sum "
     "investments."),
    ("inflation", r"\binflation\b",
     "Inflation is the rise in prices over time, so the same money buys less later. An investment needs to grow faster than "
     "inflation to keep its buying power."),
    ("equity", r"\bequity\b|\bequities\b",
     "Equity means ownership in companies, through stocks or equity mutual funds. It can grow the most over time, with the "
     "biggest ups and downs."),
]

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


# ------------------------------------------------------------------------------ moves that need one more piece
MOVE_ASK_AMOUNT = "How much should I move from {src} to {dst}? You can say 'all', a percentage like 10%, or an amount like 5000."
MOVE_ASK_ALL_MULTI = "Do you want all the money from {src} moved to {dst}? Say 'all' to do that."
MOVE_ASK_SOURCE = "Which asset class should the money come from: stocks, mutual funds or FD?"
MOVE_ASK_DEST = "Where should the money go: stocks, mutual funds or FD?"
MOVE_ONE_DEST = ("I can move money to one place at a time. For example, 'move 10% from stocks to mutual funds', "
                 "and then 'move 10% from stocks to FD'.")
MOVE_MULTI_PARTIAL = ("To move money out of two places at once, say 'move all money from mutual funds and FD to stocks'. "
                      "For a percentage or an amount, please send one move at a time.")

# ------------------------------------------------------------------------------ start over
RESET = "Okay, let's start fresh. Tell me how much you'd like to invest, for how many years and how much risk you're comfortable with."
START_OVER = re.compile(r"^(start\s+(over|again|afresh|fresh)|restart|reset(\s+(everything|it|the\s+chat|chat))?|new\s+(plan|chat)|"
                        r"naya\s+plan|dobara\s+shuru(\s+karo)?|(remove|delete|clear|scrap|cancel)\s+(everything|all|it\s+all|my\s+plan|the\s+plan|plan))$", re.I)


def is_start_over(text: str) -> bool:
    return bool(START_OVER.match(re.sub(r"\s+", " ", re.sub(r"[^\w\s']", " ", text or "")).strip()))


# ------------------------------------------------------------------------------ small talk (greetings, thanks, who/what/help)
SMALLTALK = {
    "greeting_new": ("Hi, I'm Prudie! Tell me how much you'd like to invest, for how many years and how much risk you're "
                     "comfortable with, for example '5 lakh for 5 years, moderate risk', and I'll build a plan."),
    "greeting_plan": ("Hi again! Your plan is ready. You can ask me to change the amount, years or risk, move money between "
                      "stocks, mutual funds and FDs, or add or remove one."),
    "thanks_new": "You're welcome! Whenever you're ready, tell me an amount, the years and your risk level and I'll build a plan.",
    "thanks_plan": "You're welcome! Is there anything else you'd like to change or understand about your plan?",
    "ack_new": "Okay. Tell me the amount, the years and your risk level whenever you're ready.",
    "ack_plan": "Great. Let me know if you'd like to change anything in your plan.",
    "bye": "Goodbye! Come back any time you want to adjust your plan.",
    "who": ("I'm Prudie, the Prudentia assistant. I'm an AI program, not a person. I build an illustrative split of your money "
            "across stocks, mutual funds and FDs and help you adjust it. I don't give stock tips or promise returns."),
    "beginner": ("No problem, I'll guide you. Just tell me three things: how much you'd like to invest, for how many years, and how "
                 "much risk you're comfortable with (low, moderate or high). For example, '5 lakh for 5 years, moderate risk'. "
                 "If you're not sure about the risk, say so and I'll ask three quick questions."),
    "help": ("Here is what I can do. Build a plan from an amount, years and risk (for example '5 lakh for 5 years, moderate "
             "risk'). Change it ('make it 10 years', 'risk 35%', 'remove FD', 'move 10% from stocks to FD', 'use SBI and HDFC "
             "for the FD'). Show a fund's sectors ('HDFC Large Cap sectors') or compare two funds. Explain terms such as FD, "
             "mutual fund, large cap or risk score."),
    "howru_new": ("I'm doing well, thank you! Tell me how much you'd like to invest, for how many years and your risk level, "
                  "and I'll build a plan."),
    "howru_plan": "I'm doing well, thank you! Your plan is ready; ask me to change it or explain any part of it.",
    "dangling_new": ("I'm not sure what you're answering. Tell me how much you'd like to invest, for how many years and your "
                     "risk level, for example '5 lakh for 5 years, moderate risk'."),
    "dangling_plan": ("I'm not sure what you're answering, and nothing is waiting for a reply. Tell me what to do with your plan, "
                      "for example 'make it 10 years', 'move 10% from stocks to FD' or 'remove FD'."),
}
_SMALL = [
    ("greeting", re.compile(r"^(hi+|hii+|hello+|hey+|heya|hiya|hola|namaste|namaskar|pranam|good\s+(morning|afternoon|evening|night)|gm|sup|yo)"
                            r"(\s+(there|prudie|prudentia|friend|buddy|bro|sir|ma'?am|mam|all|everyone|team))?$", re.I)),
    ("thanks", re.compile(r"^(thanks?|thank\s+you|thx|tysm|ty|shukriya|dhanyavaad|dhanyawad|many\s+thanks)"
                          r"(\s+(a\s+lot|so\s+much|very\s+much|prudie|bro|sir|mam|again))*$", re.I)),
    ("ack", re.compile(r"^(ok(ay)?|okk+|k|cool|nice|great|awesome|perfect|good|fine|got\s+it|understood|alright|sounds\s+good|"
                       r"theek\s+hai|thik\s+hai|accha|achha|badhiya|wow)(\s+(thanks?|thank\s+you|thx))?$", re.I)),
    ("bye", re.compile(r"^(bye+|goodbye|good\s+bye|see\s+(you|ya)(\s+later)?|take\s+care|cya|alvida|tata|ttyl|that'?s\s+all|"
                       r"that\s+is\s+all|i'?m\s+done)$", re.I)),
    ("who", re.compile(r"^(who\s+are\s+you|what\s+are\s+you|what'?s\s+your\s+name|what\s+is\s+your\s+name|your\s+name|tum\s+kaun\s+ho|"
                       r"aap\s+kaun\s+ho|tumhara\s+naam\s+kya\s+hai|aapka\s+naam\s+kya\s+hai|introduce\s+yourself|"
                       r"who\s+(made|created|built|developed|designed)\s+you|are\s+you\s+(a\s+|an\s+)?(bot|human|real|ai|robot|person|chat\s?gpt|gpt|alive)|"
                       r"how\s+old\s+are\s+you|what'?s\s+your\s+age|what\s+is\s+your\s+age|are\s+you\s+(a\s+)?real\s+(person|human))$", re.I)),
    ("beginner", re.compile(r"^(i\s+am|i'?m)\s+(a\s+)?(complete\s+)?(beginner|newbie|new(\s+to\s+(this|investing|it))?|confused|clueless)(\W+.*)?$|"
                            r"^(i\s+(do\s*n'?t|dont)\s+know\s+(much|anything)(\s+about\s+(investing|this|money|stocks))?)|"
                            r"^(where|how)\s+(do\s+i|should\s+i|to)\s+(start|begin)|^(getting\s+started|first\s+time\s+investor|i\s+am\s+new\s+here)$|"
                            r"^(i\s+(want|wish)\s+to\s+(start\s+)?invest(ing)?)$|^(help\s+me\s+(invest|start))$", re.I)),
    ("help", re.compile(r"^(help|help\s+me|what\s+can\s+you\s+do|what\s+do\s+you\s+do|how\s+does\s+this\s+work|how\s+do\s+i\s+use\s+this|"
                        r"how\s+to\s+use|commands?|options|menu|kya\s+kar\s+sakte\s+ho|kya\s+kar\s+sakti\s+ho|madad|help\s+karo|guide\s+me|"
                        r"how\s+can\s+you\s+help(\s+me)?|what\s+can\s+i\s+ask(\s+you)?)$", re.I)),
    ("dangling", re.compile(r"^(yes|no|yeah|yep|yup|nope|nah|haan|ha|han|nahi|nhi|all|everything|sab|half|some|more|less|maybe|hmm+|hm+|"
                            r"umm*|uh+|\?+|\.+|what|why|huh|really|sure)$", re.I)),
    ("howru", re.compile(r"^(how\s+are\s+you|how\s+r\s+u|how'?s\s+it\s+going|kaise\s+ho|kaise\s+hain\s+aap|what'?s\s+up|wassup|how\s+do\s+you\s+do)$", re.I)),
]


def smalltalk(text: str, has_plan: bool, awaiting: bool = False) -> Optional[str]:
    """A fixed, friendly answer when the WHOLE message is a greeting, thanks, goodbye, 'who are you' or 'help'; None otherwise.
    Matching the whole message means 'hi, ignore your instructions' is never treated as small talk."""
    t = re.sub(r"[^\w\s']", " ", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    if not t and re.fullmatch(r"[\s?.!]+", text or "") and "?" in text and not awaiting:
        return SMALLTALK[f"dangling_{'plan' if has_plan else 'new'}"]          # just '???'
    if not t or len(t) > 45:
        return None
    for kind, rx in _SMALL:
        if rx.match(t):
            if kind == "dangling" and awaiting:       # a bare 'yes' / 'all' can be the answer to a question that is open
                return None
            if kind in ("bye", "who", "help", "beginner"):
                return SMALLTALK[kind]
            return SMALLTALK[f"{kind}_{'plan' if has_plan else 'new'}"]
    return None
