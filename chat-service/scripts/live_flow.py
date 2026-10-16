"""End-to-end check against a running chat service (:8001) wired to the real backend (:8000).
Usage: python scripts/live_flow.py   (prints each reply; exits 1 if an assertion fails)"""
import re
import sys
import time
import uuid

import httpx

URL = "http://127.0.0.1:8001/api/chat"
BACKEND = "http://127.0.0.1:8000"
sid = "live-" + uuid.uuid4().hex[:6]
fails = []


def say(msg, **kw):
    time.sleep(1.1)                                            # 1 msg/sec rate limit
    r = httpx.post(URL, json={"session_id": kw.pop("sid", sid), "message": msg}, timeout=120)
    r.raise_for_status()
    d = r.json()
    print(f"\n> {msg}\n[{d['intent']}{' BLOCKED' if d.get('blocked') else ''}] {d['reply'][:700]}")
    replies_seen.append((msg, d["reply"]))
    return d


HINGLISH = re.compile(r"\b(hai|hain|karo|karna|nahi|nhi|saal|aap|aapka|aapke|kya|kitna|kitne|chahiye|rakho|hata|daal|liye|mein|abhi|dhyan|badlav|batao|likhiye|bhi|sirf|kuch|wapas|samajh|bolo)\b", re.I)
replies_seen = []


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


d = say("I want to invest 5 lakh")
check("asks for years and risk", d["missing"] == ["years", "risk"])
d = say("5 years")
d = say("risk 35%")
pid = d.get("result", {}).get("profile_id")
check("plan created via /plan", bool(pid) and d["result"]["risk_score"] == 35 and "scenarios" in d["result"])
check("classes/split_pct/banks_mode/data_as_of passed through", all(k in d["result"] for k in ("classes", "split_pct", "banks_mode", "data_as_of")))
d = say("make it 10 years")
check("years 5 -> 10, same plan id", d["result"]["years"] == 10 and d["result"]["profile_id"] == pid)
stored = httpx.get(f"{BACKEND}/plan/{pid}", timeout=60).json()
check("backend stored plan has 10 years", stored["horizon_years"] == 10)
d = say("remove FD")
check("FD removed", d["params"]["classes"] == ["stocks", "mf"] and d["result"]["split_pct"]["bank"] == 0)
d = say("add FD wapas")
check("FD added back", d["params"]["classes"] == ["stocks", "mf", "fd"] and d["result"]["split_pct"]["bank"] > 0)
d = say("remove FD")
d = say("remove mutual funds")
check("MF removed", d["params"]["classes"] == ["stocks"])
d = say("add mutual funds")
check("MF added", d["params"]["classes"] == ["stocks", "mf"])
d = say("remove mutual funds")
d = say("shift 10% from stocks to mutual funds")
check("shift adds MF class", "mf" in d["result"]["classes"] and d["intent"] == "rebalance")
d = say("stocks se FD me 10% daal do")
check("shift 10% stocks->FD adds FD", "fd" in d["result"]["classes"] and d["result"]["split_pct"]["bank"] >= 9.9)
d = say("SBI aur HDFC me FD rakho")
check("custom banks", d["result"]["banks_mode"] == "custom" and len([i for i in d["result"]["instruments"] if i["bucket"] == "bank"]) == 2)
d = say("banks auto kar do")
check("back to auto 5", d["result"]["banks_mode"] == "auto")
d = say("Zebra Bank me FD rakho")
check("unknown bank refused", d.get("result") is None and "Zebra".lower() in d["reply"].lower())
d = say("make it 50 years")
check("years 50 refused", d["missing"] == ["years"])
d = say("what is the weather in Delhi today")
check("off-topic refused (English)", d.get("blocked") is True and "I can only help" in d["reply"])
d = say("aaj ka mausam kaisa hai batao")
check("off-topic refused (Hinglish)", d.get("blocked") is True and "I can only help" in d["reply"])
d = say("mujhe 8 lakh 6 saal ke liye moderate risk me lagana hai", sid=sid + "-h")
check("Hinglish plan created", d["result"]["years"] == 6 and d["result"]["risk_score"] == 50)
d = say("FD hata do", sid=sid + "-h")
check("Hinglish remove FD", d["params"]["classes"] == ["stocks", "mf"])
check("every reply is English", not [m for m in replies_seen if HINGLISH.search(m[1])])
sys.exit(1 if fails else 0)
