"""Human-readable listing titles for homepage/compare (official fields only)."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper import _clean_title, _looks_like_real_promo

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "]+",
    flags=re.UNICODE,
)

_AUDIENCE_RE = re.compile(
    r"(?i)frontline workers|first responders|military|healthcare workers|teachers|students"
)

_NAV_PHRASES_RE = re.compile(
    r"(?i)\b(?:"
    r"shop(?:\s+all|\s+smoothies)?|login|log\s*in|sign\s*in|cart|menu|learn\s+more|"
    r"see\s+menu(?:\s*&\s*pricing)?|how\s+do\s+i\s+get\s+started|get\s+started|"
    r"best\s+deal|hsa/fsa\s+eligible|student\s+discount\s+boost"
    r")\b"
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


def _normalize_spaces_and_typos(text: str) -> str:
    text = re.sub(r"\bO\s+rders\b", "Orders", text, flags=re.I)
    text = re.sub(r"\btodayand\b", "today and ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_ui_chrome(text: str) -> str:
    text = _EMOJI_RE.sub("", text)
    text = re.sub(r"[★☆⭐]+", "", text)
    text = re.sub(r"(?i)\s*start today with\s+", "", text)
    text = _NAV_PHRASES_RE.sub(" ", text)
    text = re.sub(r"(?i)^huel\s+", "", text)
    text = re.sub(r"(?i)^everyplate\s+", "", text)
    text = re.sub(r"(?i)^exclusive benefits include\s+", "", text)
    text = re.sub(r"^[•·]\s*", "", text)
    text = re.sub(r"\s*[•·]\s*", "; ", text)
    text = re.sub(r"\s*:\s*$", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ;,.")
    return _normalize_spaces_and_typos(text)


def _sentence_case(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    if s.isupper() and len(s) > 18:
        s = s.title()
        s = re.sub(r"\bOff\b", "off", s)
        s = re.sub(r"\bAnd\b", "and", s)
        s = re.sub(r"\bWith\b", "with", s)
        s = re.sub(r"\bOn\b", "on", s)
        s = re.sub(r"\bFor\b", "for", s)
        s = re.sub(r"\bCode\b", "code", s)
    if s and s[0].islower() and not re.match(r"(?i)use code", s):
        s = s[0].upper() + s[1:]
    return s


def _humanize_benefit(benefit: str) -> str:
    b = benefit.strip()
    b = re.sub(r"\s*\+\s*", " and ", b)
    if b.isupper():
        b = b.title()
    b = re.sub(r"\bOff\b", "off", b)
    b = re.sub(r"\bAnd\b", "and", b)
    return b.strip()


def _humanize_conditions(conditions: str) -> str:
    c = conditions.strip().strip(",").strip()
    if not c or len(c) > 55:
        return ""
    if c.isupper():
        c = c.title()
    cl = c.lower()
    if cl.startswith("your "):
        return "on " + cl
    if cl.startswith("on "):
        return cl
    if cl.startswith("applies "):
        return cl
    if cl in {"first order", "upcoming order"}:
        return "on your " + cl
    if cl == "first order":
        return "on your first order"
    return ""


def _min_order_from_blob(blob: str) -> str | None:
    m = re.search(r"(?i)orders?\s*\$([\d,]+)\+", blob)
    if m:
        return f"orders ${m.group(1)}+"
    m = re.search(r"(?i)free shipping\s*\$([\d,]+)\+", blob)
    if m:
        return f"orders ${m.group(1)}+"
    return None


def is_truncated_title(title: str) -> bool:
    t = title.strip()
    if not t:
        return True
    if re.search(r",\s*h$", t) or (re.search(r"\s[a-z]$", t) and len(t) > 45):
        return True
    if re.search(r":\s*•\s*\d+$", t):
        return True
    if "Recurring Orders:" in t and re.search(r"•\s*10\s*$", t):
        return True
    if re.match(r"^\d{2}\s+\d+%", t):
        return True
    if re.match(r"(?i)^off\b", t) and not re.search(r"(?i)\d+%\s*off", t):
        return True
    if re.search(r"(?i)meal plan\s*-\s*10 meal plan", t):
        return True
    if re.search(r"(?i)expires \d+ days after", t):
        return True
    return False


def needs_listing_recompose(title: str) -> bool:
    t = title.strip()
    if not t:
        return True
    if is_truncated_title(t):
        return True
    if re.search(r"(?i)\b(cart|login|learn more|see menu)\b", t):
        return True
    if re.search(r"(?i)national wellness month", t):
        return True
    if re.search(r"(?i)exclusive benefits include", t):
        return True
    if t.isupper() and len(t) > 25:
        return True
    if re.search(r"(?i)subscribe and save.*student discount", t):
        return True
    if re.search(r"(?i)huel free shipping", t):
        return True
    if re.search(r"(?i)shop smoothies", t):
        return True
    if re.search(r"(?i)aarp discount first order:", t):
        return True
    if re.search(r"(?i)\$15 off your entire order:", t):
        return True
    if re.search(r"(?i)everyplate today", t):
        return True
    if re.search(r"(?i)today and get", t):
        return True
    if re.search(r"month'", t):
        return True
    if re.search(r"(?i)inside scoop", t):
        return True
    if re.search(r"(?i)free shipping \$65\+", t):
        return True
    if re.search(r"(?i)pause or cancel", t):
        return True
    if re.search(r"(?i)free bottle\s+\d+$", t):
        return True
    if re.match(r"(?i)^off &", t):
        return True
    if re.search(r"\d+%\s*off\s*\+", t, re.I):
        return True
    if re.search(r"(?i)\+\s*\$1\b", t):
        return True
    if re.search(r"(?i)frontline workers get our best sale price", t):
        return True
    if t[0].islower() and not re.match(r"(?i)use code", t):
        return True
    return False


def is_bad_listing_title(title: str, offer: dict[str, Any] | None = None) -> bool:
    t = title.strip()
    if len(t) < 10:
        return True
    if is_truncated_title(t):
        return True
    if re.search(r"(?i)\b(cart|login|learn more|see menu)\b", t):
        return True
    if re.search(r"with code \w+ with code", t, re.I):
        return True
    if len(t) > 200:
        return True
    if re.search(r"\$\d+\s+off\s+and\s+\$\d+\s+off", t, re.I):
        return True
    if not _looks_like_real_promo(t, offer.get("price") if offer else None, offer.get("code") if offer else None):
        return True
    return False


def compose_listing_title(offer: dict[str, Any]) -> str | None:
    benefit = (offer.get("benefit") or "").strip()
    conditions = (offer.get("conditions") or "").strip()
    code = (offer.get("code") or "").strip()
    blob = _blob(offer)
    provider = (offer.get("provider") or "").strip()
    blob_l = blob.lower()

    if re.search(r"(?i)(?:up to\s+)?\$15\s+off\s+your\s+entire\s+order", blob):
        return "Up to $15 off your entire order"

    if provider == "Icon Meals" and re.search(r"(?i)15%\s*off", blob):
        if "military" in blob_l or "first responder" in blob_l:
            return "15% off for military and first responders"

    if provider == "Mosaic Foods" and re.search(r"(?i)20%\s*off", blob):
        return "20% off your first order"

    if provider == "Sunbasket" and re.search(r"(?i)\$90\s*off\s+across\s+4\s+boxes", blob):
        return "Get $90 off across 4 boxes"

    if provider == "Dinnerly" and re.search(r"(?i)up to\s*\$180\s*off", blob):
        return "Up to $180 off your first 5 boxes"

    if provider == "Huel":
        ship = re.search(r"(?i)free shipping\s*\$([\d,]+)\+", blob)
        pct33 = re.search(r"(?i)33%\s*off", blob)
        if ship and pct33:
            return f"Free shipping on orders ${ship.group(1)}+ and 33% off"
        if "subscribe" in blob_l:
            sub = re.search(r"(?i)subscribe\s+and\s+save\s+(\d{1,3})%", blob)
            bits: list[str] = []
            if ship:
                bits.append(f"Free shipping on orders ${ship.group(1)}+")
            if sub:
                bits.append(f"subscribe and save {sub.group(1)}%")
            if bits:
                return "; ".join(bits)

    if benefit and re.search(r"(?i)15%\s*off", benefit) and provider == "Huel":
        return "15% off your first order"

    if re.search(r"(?i)large box", blob) and re.search(r"(?i)20%\s*off", blob):
        return "20% off large box"

    if re.search(r"(?i)save\s+20%", blob) and re.search(r"(?i)free shipping", blob):
        if "pause or cancel" in blob_l:
            return "Save 20% with free shipping"

    aarp = "aarp" in blob_l
    if provider == "Silver Cuisine" and benefit:
        hb = _humanize_benefit(benefit)
        min_ord = _min_order_from_blob(blob)
        prefix = "AARP members: " if aarp else ""
        title = f"{prefix}{hb} on your first order"
        if min_ord:
            title += f" ({min_ord})"
        return _sentence_case(title)

    if provider == "ModifyHealth" and code:
        return f"25% off your first order and free shipping with code {code.upper()}"

    if provider == "Marley Spoon":
        url_l = (offer.get("source_url") or offer.get("offer_url") or "").lower()
        benefit_txt = (benefit or "Up to 50% off").strip()
        if "rtc-50p" in url_l or "rtc50" in url_l:
            hb = _humanize_benefit(benefit_txt) if benefit_txt else "Up to 50% off"
            return f"Marley Spoon promo: {hb} on the official rtc50p offer page"
        return f"Marley Spoon discount: {_humanize_benefit(benefit_txt)}"

    if provider == "Chefs Plate" and benefit:
        if re.search(r"(?i)free meals", benefit) or re.search(r"(?i)20 free meals", benefit):
            return "Get up to 20 free meals + free shipping"

    if provider == "Thistle" and _AUDIENCE_RE.search(blob):
        return "Frontline workers: 50% off your first week of Thistle, all year round"

    if provider == "Kencko" and benefit and re.search(r"(?i)25%\s*off", benefit):
        if re.search(r"(?i)free bottle", blob):
            return "25% off and free shipping with a free bottle"
        return "25% off and free shipping"

    if code and benefit and "code" not in benefit.lower():
        hb = _humanize_benefit(benefit)
        hc = _humanize_conditions(conditions)
        title = hb + (f" {hc}" if hc else "") + f" (code {code.upper()})"
        return _sentence_case(strip_ui_chrome(title))

    if benefit and re.match(r"(?i)^10%\s*off", benefit):
        hc = _humanize_conditions(conditions)
        return _sentence_case(_humanize_benefit(benefit) + (f" {hc}" if hc else ""))

    if benefit and re.search(r"(?i)20%\s*off", benefit) and "month" in blob_l:
        tail = "applies to boxes 2-5" if "boxes 2-5" in blob_l else ""
        base = "20% off your next month"
        return f"{base} ({tail})" if tail else base

    if re.search(r"(?i)\$2\.99/meal", blob) and re.search(r"(?i)10%\s*off", blob):
        return "Get $2.99/meal on your first box + 10% off for 1 month"

    if re.search(r"(?i)subscribe\s*&\s*save", blob):
        m = re.search(r"(?i)subscribe\s*&\s*save\s+(\d+)%", blob)
        if m and re.search(r"(?i)free shipping", blob):
            return f"Subscribe and save {m.group(1)}% and get free shipping"

    raw = strip_ui_chrome(_clean_title((offer.get("title") or "")))
    raw = re.sub(r"(?i)^everyplate\s+today\s+and\s+get\s+", "Get ", raw)
    m = re.search(
        r"(?i)(\$[\d.]+/meal[^+]*\+[^*]+|get \$[\d.]+/meal[^*]+)",
        raw,
    )
    if m:
        return _sentence_case(strip_ui_chrome(m.group(1)))

    if benefit and len(benefit) <= 50:
        hb = _humanize_benefit(benefit)
        if re.search(r"(?i)(?:\d+%|\$\d+|free)", hb):
            hc = _humanize_conditions(conditions)
            t = hb + (f" {hc}" if hc else "")
            if not is_bad_listing_title(t, offer):
                return _sentence_case(strip_ui_chrome(t))

    return None


def polish_listing_title(cleaned_raw: str) -> str:
    t = strip_ui_chrome(cleaned_raw)
    t = re.sub(r"\s+with code (\w+)\s+with code \1", r" with code \1", t, flags=re.I)
    t = re.sub(r"\s+\d\s*$", "", t)
    return _sentence_case(t)


def finalize_listing_title(offer: dict[str, Any], cleaned_raw: str) -> str | None:
    if (offer.get("provider") or "").strip() == "Marley Spoon":
        composed = compose_listing_title(offer)
        if composed and not is_bad_listing_title(composed, offer):
            return composed
    polished = polish_listing_title(cleaned_raw)
    if polished and not needs_listing_recompose(polished) and not is_bad_listing_title(polished, offer):
        return polished
    composed = compose_listing_title(offer)
    if composed:
        composed = strip_ui_chrome(_normalize_spaces_and_typos(composed))
        composed = re.sub(r"\s+", " ", composed).strip()
        if not is_bad_listing_title(composed, offer):
            return composed
    return None


def listing_title_passes(offer: dict[str, Any]) -> bool:
    title = (offer.get("title") or "").strip()
    return bool(title) and not is_bad_listing_title(title, offer)
