"""Audit showable offers and provider intros for provenance issues."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build import is_showable, sanitize_offer
from ilang_config import load_site_config
from scraper import (
    _intro_is_brand_copy,
    _is_unit_price_not_promo,
    _offer_in_visible_page,
    fetch,
)

DATA = ROOT / "data" / "offers.json"


def main() -> None:
    cfg = load_site_config()
    shelved = set(cfg.get("shelved") or [])
    data = json.loads(DATA.read_text(encoding="utf-8"))
    profiles = data.get("provider_profiles") or {}
    issues: list[str] = []

    for raw in data.get("offers") or []:
        o = dict(raw)
        sanitize_offer(o)
        if o.get("provider") in shelved or not is_showable(o):
            continue
        title = o.get("title") or ""
        if _is_unit_price_not_promo(title, o.get("price")):
            issues.append(f"unit-price offer: {o['provider']} | {title}")
        src = o.get("source_url") or ""
        if not src:
            issues.append(f"missing source: {o['provider']} | {title[:60]}")
            continue
        if o.get("visible_verified") is True:
            continue
        if o.get("verification_basis") == "scrape_record" and (o.get("fetched_at") or "").strip():
            continue
        status, _final, body = fetch(src)
        if status != 200 or body.startswith("__ERROR__"):
            issues.append(f"source fetch fail: {o['provider']} | HTTP {status} | {src}")
            continue
        if not _offer_in_visible_page(title, o.get("code"), body):
            issues.append(f"source mismatch: {o['provider']} | {title[:60]} | {src}")

    for name, prof in profiles.items():
        if name in shelved:
            continue
        intro = (prof.get("intro") or "").strip()
        src = (prof.get("intro_source_url") or "").strip()
        if not intro:
            continue
        if not _intro_is_brand_copy(intro, src):
            issues.append(f"bad about: {name} | {intro[:80]} | {src}")

    print(f"issues: {len(issues)}")
    for line in issues:
        print("-", line)


if __name__ == "__main__":
    main()
