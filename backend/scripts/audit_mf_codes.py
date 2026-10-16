"""Check every fund in universe/mf_scheme_codes.json against mfapi.in: does the scheme the code points to match the fund
name the app shows? Read-only: prints a report and writes data/mf_code_audit.json. Network: mfapi.in (the app's NAV source)."""
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
mf = json.load(open(ROOT / "universe" / "mf_scheme_codes.json", encoding="utf8"))
STOP = {"fund", "growth", "plan", "option", "direct", "regular", "the", "of", "and", "-"}
SYN = {"bluechip": "largecap", "largecap": "largecap", "largecap": "largecap", "midcap": "midcap", "smallcap": "smallcap"}


def words(s):
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower().replace("large cap", "largecap").replace("mid cap", "midcap").replace("small cap", "smallcap"))
    return {SYN.get(w, w) for w in s.split() if w not in STOP}


def get(code):
    req = urllib.request.Request(f"https://api.mfapi.in/mf/{code}/latest", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["meta"]


rows, bad = [], []
for name, code in mf.items():
    if not code:
        continue
    try:
        m = get(code)
    except Exception as exc:
        rows.append({"fund": name, "code": code, "error": exc.__class__.__name__})
        continue
    official = m["scheme_name"]
    miss = words(name) - words(official)       # words of our name that the official name lacks
    extra = words(official) - words(name)      # words the official name has that ours lacks (e.g. "us", "etf", "fof")
    ok = not (miss or {"us", "global", "international", "fof", "etf", "overseas"} & extra)
    rows.append({"fund": name, "code": code, "official": official, "category": m.get("scheme_category"),
                 "direct": "direct" in official.lower(), "ok": ok, "missing": sorted(miss), "extra": sorted(extra)})
    if not ok:
        bad.append(rows[-1])
    time.sleep(0.15)
json.dump(rows, open(ROOT / "data" / "mf_code_audit.json", "w", encoding="utf8"), indent=1)
print(f"{len(rows)} funds checked, {len(bad)} look wrong or suspicious\n")
for r in bad:
    print(f"- {r['fund']}  [{r['code']}]\n    points to: {r.get('official')}  ({r.get('category')})  missing={r.get('missing')} extra={r.get('extra')}")
print("\nplan type split:", {"direct": sum(1 for r in rows if r.get('direct')), "not direct": sum(1 for r in rows if 'direct' in r and not r['direct'])})
