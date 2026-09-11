"""Offer quality gates: unit prices, routine perks, contradictions, real promo signals."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper import PERCENT_RE, _is_unit_price_not_promo

ROUTINE_ONLY_RE = re.compile(
    r"(?i)(?:"
    r"free\s+shipping(?:\s+on\s+all\s+orders)?(?:\s+over\s+\$\d+)?"
    r"|no\s+subscription\s+required"
    r"|cancel\s+anytime"
    r"|subscription\s+not\s+required"
    r")"
)

REAL_PROMO_RE = re.compile(
    r"(?i)(?:"
    r"\d{1,3}%\s*off"
    r"|\$\d+(?:\.\d{1,2})?\s*off"
    r"|save\s+\$?\d+"
    r"|(?:get\s+)?\d+\s*free\s+meals?"
    r"|free\s+(?:breakfast|lunch|dozen|item|gift|trial|week|month|meals?|protein|favorites|welcome)"
    r"|free\s+\d+[-\s]?day\s+trial"
    r"|(?:\d+%|\$\d+).{0,30}(?:off|discount)"
    r")"
)


def _blob(offer: dict[str, Any]) -> str:
    parts = [
        offer.get("title") or "",
        offer.get("benefit") or "",
        offer.get("conditions") or "",
        offer.get("snippet") or "",
        offer.get("price") or "",
    ]
    return " ".join(p for p in parts if p).strip()


def has_real_promo_signal(offer: dict[str, Any]) -> bool:
    title = (offer.get("title") or "").strip()
    benefit = (offer.get("benefit") or "").strip()
    conditions = (offer.get("conditions") or "").strip()
    code = (offer.get("code") or "").strip()
    blob = _blob(offer)
    if not blob:
        return False
    if REAL_PROMO_RE.search(blob):
        return True
    if code and re.search(r"(?i)(?:save|off|discount|\$\d+|\d+%)", title + " " + benefit):
        return True
    if code and re.search(r"(?i)save\s+\$?\d+", title):
        return True
    if PERCENT_RE.search(blob) or re.search(r"(?i)\$\d+\s*off", blob):
        return True
    return False


def is_routine_service_not_promo(offer: dict[str, Any]) -> bool:
    if has_real_promo_signal(offer):
        return False
    title = (offer.get("title") or "").strip()
    benefit = (offer.get("benefit") or "").strip()
    blob = f"{title} {benefit}".lower()
    if _is_unit_price_not_promo(title, offer.get("price")):
        return True
    if re.fullmatch(
        r"(?i)(?:free\s+shipping|no\s+subscription\s+required|cancel\s+anytime)(?:\s+and\s+no\s+subscription\s+required)?\.?",
        title,
    ):
        return True
    if re.search(r"(?i)free\s+shipping\s+and\s+no\s+subscription", title):
        return True
    if re.fullmatch(r"(?i)free\s+shipping", benefit):
        return True
    if re.search(r"(?i)^factor\s+box,\s*plus\s+free\s+shipping$", title):
        return True
    if re.search(r"(?i)free\s+shipping\s+on\s+all\s+orders", blob):
        return True
    if ROUTINE_ONLY_RE.search(blob) and not REAL_PROMO_RE.search(blob):
        return True
    return False


def title_conditions_contradict(offer: dict[str, Any]) -> bool:
    title = (offer.get("title") or "").lower()
    conditions = (offer.get("conditions") or "").lower()
    benefit = (offer.get("benefit") or "").lower()
    meta = f"{conditions} {benefit}"
    if not title or not meta.strip():
        return False
    if re.search(r"no\s+subscription", title) and re.search(r"subscription\s+required", meta):
        return True
    if re.search(r"subscription\s+not\s+required", title) and re.search(
        r"subscription\s+required", meta
    ):
        return True
    if re.search(r"no\s+subscription\s+required", title) and conditions == "subscription required":
        return True
    return False


def audit_offer(offer: dict[str, Any]) -> list[str]:
    """Return human-readable rejection reasons (empty = pass)."""
    reasons: list[str] = []
    title = (offer.get("title") or "").strip()
    provider = offer.get("provider") or "?"

    if _is_unit_price_not_promo(title, offer.get("price")):
        reasons.append("unit-price-not-promo")
    if is_routine_service_not_promo(offer):
        reasons.append("routine-service-not-promo")
    if title_conditions_contradict(offer):
        reasons.append("title-conditions-contradiction")
    if not has_real_promo_signal(offer):
        reasons.append("missing-real-promo-signal")
    if reasons:
        return [f"{provider} | {title[:70]} | {r}" for r in reasons]
    return []


def offer_passes_quality(offer: dict[str, Any]) -> bool:
    return not audit_offer(offer)
