"""Load data/mf_sector_snapshot.json into the mf_sector_allocation table, so the existing endpoint
/mutual-funds/{fund}/sector-allocation (and the app's Fund sectors page) serve it. Additive: it only inserts or
replaces rows for the funds in the snapshot and never touches any other table.

    python scripts/load_mf_sector_snapshot.py
"""
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.dialects.sqlite import insert  # noqa: E402

from backend.db import get_engine, init_db, mf_sector_allocation  # noqa: E402

snap = json.load(open(Path(__file__).resolve().parents[1] / "data" / "mf_sector_snapshot.json", encoding="utf8"))
init_db()
now = dt.datetime.now()
n = 0
with get_engine().begin() as conn:
    for code, f in snap["funds"].items():
        if not f.get("as_of") or not f.get("sectors"):
            print("skipped (no date or sectors):", code, f.get("fund_name"))
            continue
        row = {"scheme_code": code, "date": dt.date.fromisoformat(f["as_of"]), "sector_json": f["sectors"],
               "source_url": f.get("source_url") or f.get("source", ""), "fetched_at": now}
        stmt = insert(mf_sector_allocation).values(**row).on_conflict_do_update(
            index_elements=["scheme_code", "date"],
            set_={"sector_json": row["sector_json"], "source_url": row["source_url"], "fetched_at": now})
        conn.execute(stmt)
        n += 1
print(f"{n} funds in the database now")
