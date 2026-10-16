"""Build data/mf_sector_snapshot.json from the official monthly portfolio spreadsheets in data/mf_portfolios/.

Run it from the backend folder:  python -I scripts/build_mf_sector_snapshot.py   (isolated mode: the spreadsheets are downloaded
files, so they are only ever read as data). openpyxl is needed only when spreadsheets are present.

What it reads: each fund house publishes, per scheme, an "Allocation of Net Asset by Sectors" table (sector and
% to net assets) in its monthly portfolio file. This script finds that table in every sheet, matches the sheet to one of
the funds in universe/mf_scheme_codes.json, and records the sectors. Funds already stored in the database from an
earlier source are carried over unchanged, so the snapshot is the one complete file.

Output shape:
  {"generated_at": "...", "funds": {"<scheme_code>": {"fund_name", "as_of", "sectors": {"Sector": percent}, "source", "source_url"}}}
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(ROOT, "data", "mf_portfolios")
OUT = os.path.join(ROOT, "data", "mf_sector_snapshot.json")
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


def norm(name: str) -> str:
    """'Union Large Cap Fund' and 'Union Largecap Fund' compare equal."""
    s = re.sub(r"[^a-z0-9]+", "", name.lower().replace("&", "and"))
    return s.replace("fund", "")


def month_end(filename: str) -> str | None:
    low = filename.lower()
    for i, m in enumerate(MONTHS):
        hit = re.search(rf"{m}[-_ ]*(20\d\d)|(20\d\d)[-_ ]*{m}", low)
        if hit:
            year = int(hit.group(1) or hit.group(2))
            nxt = dt.date(year + (i + 1) // 12, (i + 1) % 12 + 1, 1)
            return (nxt - dt.timedelta(days=1)).isoformat()
    return None


def title_case(s: str) -> str:
    small = {"and", "of", "the", "&"}
    words = re.sub(r"\s+", " ", s.strip()).lower().split(" ")
    return " ".join(w if (w in small and i) else w.capitalize() for i, w in enumerate(words))


def sector_table(ws):
    """Find the 'Sectors' header and return {sector: percent}, or None when the sheet has no such table."""
    rows = list(ws.iter_rows(values_only=True))
    for r, row in enumerate(rows):
        cells = [str(c).strip().lower() if c is not None else "" for c in row]
        if "sectors" not in cells:
            continue
        c = cells.index("sectors")
        # the percentage column is the next non-empty cell to the right that is numeric in the following rows
        out: dict[str, float] = {}
        for nxt in rows[r + 1:]:
            name = nxt[c] if c < len(nxt) else None
            val = next((v for v in nxt[c + 1:c + 3] if isinstance(v, (int, float))), None)
            if name is None or str(name).strip() == "":
                if out:
                    break
                continue
            label = str(name).strip()
            if re.match(r"(?i)^(total|grand total|net assets)", label):
                break
            if val is None:
                continue
            pct = round(float(val) * 100, 4)
            if pct > 0:
                out[title_case(label)] = pct
        return out or None
    return None


def main() -> None:
    universe = json.load(open(os.path.join(ROOT, "universe", "mf_scheme_codes.json"), encoding="utf8"))
    by_norm = {norm(n): (n, c) for n, c in universe.items() if c}
    sources = {}
    sp = os.path.join(FOLDER, "_sources.json")
    if os.path.exists(sp):
        sources = json.load(open(sp, encoding="utf8"))

    funds: dict[str, dict] = {}
    # carry over what the database already holds (stored earlier from another source)
    db = os.path.join(ROOT, "data", "asset_allocation.db")
    if os.path.exists(db):
        con = sqlite3.connect(db)
        for code, date, sj, url in con.execute("select scheme_code, date, sector_json, source_url from mf_sector_allocation"):
            name = next((n for n, c in universe.items() if c == code), code)
            funds[code] = {"fund_name": name, "as_of": str(date), "sectors": json.loads(sj) if isinstance(sj, str) else sj,
                           "source": "earlier scrape (kept)", "source_url": url}
        con.close()

    report = []
    sheets = sorted(glob.glob(os.path.join(FOLDER, "*", "*.xls*")))
    if sheets:
        import openpyxl
    for path in sheets:
        fname = os.path.basename(path)
        if fname.startswith("~"):
            continue
        as_of = month_end(fname)
        try:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        except Exception as exc:
            report.append((fname, f"cannot open ({exc.__class__.__name__})"))
            continue
        used = skipped = 0
        for sheet in wb.sheetnames:
            hit = by_norm.get(norm(sheet))
            if not hit:
                skipped += 1
                continue
            name, code = hit
            sectors = sector_table(wb[sheet])
            if not sectors:
                report.append((fname, f"{sheet}: matched {name} but no sector table"))
                continue
            total = sum(sectors.values())
            if total > 100.6:
                report.append((fname, f"{sheet}: sectors add to {total:.1f}%, skipped"))
                continue
            funds[code] = {"fund_name": name, "as_of": as_of or "", "sectors": sectors,
                           "source": f"official monthly portfolio file ({fname})", "source_url": sources.get(fname, "")}
            used += 1
        report.append((fname, f"{used} funds loaded, {skipped} sheets not in our fund list"))
        wb.close()

    # Sector tables typed in from screenshots (data/mf_portfolios/manual_sectors.json):
    #   {"<fund name as in the app>": {"as_of": "YYYY-MM-DD", "source": "...", "sectors": {"Sector": percent, ...}}}
    manual = os.path.join(FOLDER, "manual_sectors.json")
    if os.path.exists(manual):
        for fund, rec in json.load(open(manual, encoding="utf8")).items():
            # match on the saved name first, then on any alternative name noted with it (e.g. the app's older name)
            hit = next((by_norm[norm(n)] for n in [fund, *rec.get("aliases", [])] if norm(n) in by_norm), None)
            if not hit:
                report.append(("manual_sectors.json", f"{fund}: not one of the funds in the app, skipped"))
                continue
            name, code = hit
            sectors = {title_case(k): round(float(v), 4) for k, v in rec["sectors"].items() if float(v) > 0}
            if sum(sectors.values()) > 100.6:
                report.append(("manual_sectors.json", f"{name}: sectors add to {sum(sectors.values()):.1f}%, skipped"))
                continue
            funds[code] = {"fund_name": name, "as_of": rec.get("as_of", ""), "sectors": sectors,
                           "source": rec.get("source", "entered by hand"), "source_url": rec.get("source_url", "")}
            report.append(("manual_sectors.json", f"{name}: loaded {len(sectors)} sectors (adds to {sum(sectors.values()):.1f}%)"))

    snapshot = {"generated_at": dt.datetime.now().isoformat(timespec="seconds"), "funds": funds}
    json.dump(snapshot, open(OUT, "w", encoding="utf8"), indent=1, ensure_ascii=False)
    for f, msg in report:
        print(f"{f}: {msg}")
    print(f"snapshot: {len(funds)} funds -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
