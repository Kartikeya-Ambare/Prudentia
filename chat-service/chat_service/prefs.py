"""Knowledgeable-mode preferences: stock sectors (the 12 in the backend's stock_universe.yaml) and MF categories.
Parsed by rules from the user's own words; nothing here is guessed."""
from __future__ import annotations

import re
from typing import Optional

from chat_service.guardrails.chat_guardrails import normalise
from chat_service.parse import _ADD, _REMOVE

SECTORS = {
    "banking": r"banking|bank\s+stocks?",
    "nbfc_insurance_amc": r"nbfc|\bamc\b|asset\s+management",
    "it_technology": r"\bit\s+(sector|stocks?|shares?|companies)|technology|\btech\b|software",
    "pharma_healthcare": r"pharma\w*|health\s?care",
    "auto_ancillary": r"\bauto(mobile|motive)?\b|auto\s+ancillary",
    "fmcg": r"\bfmcg\b",
    "metals_mining": r"\bmetals?\b|mining",
    "energy_power": r"\benergy\b|\bpower\b",
    "realty_infra": r"realty|infra\w*",
    "capital_goods_defence": r"capital\s+goods|defen[cs]e",
    "consumer_durables_retail": r"consumer\s+durables?|\bretail\b",
    "media_digital": r"\bmedia\b|\bdigital\b",
}
SECTOR_LABEL = {k: k.replace("_", " ").title().replace("Nbfc Insurance Amc", "NBFC/Insurance/AMC")
                .replace("It Technology", "IT/Technology").replace("Fmcg", "FMCG") for k in SECTORS}
CATEGORIES = {"Large Cap": r"large\s*caps?", "Mid Cap": r"mid\s*caps?", "Small Cap": r"small\s*caps?"}
_PREF_CUE = re.compile(r"\b(sector|sectors|stocks?|shares?|category|categories|funds?|only|sirf|focus|prefer\w*|"
                       r"include|exclude|rakho|chahiye|hata\w*|add|lagao|me|mein)\b", re.I)


def _mode(t: str) -> str:
    return "remove" if _REMOVE.search(t) else "add" if _ADD.search(t) else "set"


def parse_prefs(text: str) -> dict:
    """{'sector_pref': (mode, set_of_ids), 'mf_category_pref': (mode, set_of_names)} for the keys found."""
    t = normalise(text)
    out: dict = {}
    sec = {k for k, rx in SECTORS.items() if re.search(rx, t, re.I)}
    cat = {k for k, rx in CATEGORIES.items() if re.search(rx, t, re.I)}
    if sec and _PREF_CUE.search(t):
        out["sector_pref"] = (_mode(t), sec)
    if cat:
        out["mf_category_pref"] = (_mode(t), cat)
    return out


def apply_pref(current: Optional[list], mode: str, vals: set) -> list:
    cur = set(current or [])
    new = vals if mode == "set" else cur | vals if mode == "add" else cur - vals
    return sorted(new)
