"""Homepage / compare card: which offer leads and what subtitle to show."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper import clean_conditions

_AUDIENCE_RE = re.compile(
    r"(?i)frontline workers|first responders|military|healthcare workers|teachers|students"
)


def _blob(offer: dict[str, Any]) -> str:
    return " ".join(
        p
        for p in (
            offer.get("title"),
            offer.get("snippet"),
            offer.get("benefit"),
            offer.get("conditions"),
        )
        if p
    )


def _is_campaign_shout(fragment: str) -> bool:
    letters = [c for c in fragment if c.isalpha()]
    if len(letters) < 10:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) > 0.8


def pick_card_lead_offer(provider: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Choose the offer shown on homepage + compare for this brand."""
    if not rows:
        raise ValueError("empty rows")
    if provider == "Huel":
        for o in rows:
            if re.search(r"(?i)33%\s*off", _blob(o)):
                return o
        for o in rows:
            if re.search(r"(?i)free shipping", _blob(o)) and re.search(
                r"(?i)33%\s*off", o.get("benefit") or ""
            ):
                return o
    return rows[0]


def normalize_offer_conditions_for_cards(offer: dict[str, Any]) -> None:
    """Trim conditions so card line 2 matches the same promo (mutates offer)."""
    provider = (offer.get("provider") or "").strip()
    raw = (offer.get("conditions") or "").strip()
    if provider == "ModifyHealth":
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        kept = [p for p in parts if re.search(r"(?i)first order", p)]
        offer["conditions"] = "Your first order" if kept else ""
        return
    if provider == "Thistle" and _AUDIENCE_RE.search(raw):
        offer["conditions"] = "First week only; available all year round"
        return
    if provider == "Huel" and re.search(r"(?i)33%\s*off", _blob(offer)):
        if re.search(r"(?i)student discount boost", _blob(offer)):
            offer["conditions"] = "Student discount boost"
        else:
            offer["conditions"] = ""
        return


def card_conditions_line(offer: dict[str, Any], base_line_fn) -> str:
    """Wrapper around build.offer_card_conditions_line with card-specific rules."""
    o = dict(offer)
    normalize_offer_conditions_for_cards(o)
    line = base_line_fn(o)
    if not line:
        return ""
    parts = [p.strip() for p in re.split(r";\s*", line) if p.strip()]
    kept = [p for p in parts if not _is_campaign_shout(p)]
    return "; ".join(kept).strip()
