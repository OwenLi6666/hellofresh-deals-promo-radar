"""Pre-build audit: block showable offers that fail quality gates."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datetime import date

from build import sanitize_offer
from ilang_config import load_site_config
from scraper import _looks_like_real_promo

sys.path.insert(0, str(ROOT / "tools"))
from offer_quality import audit_offer, offer_passes_quality

DATA = ROOT / "data" / "offers.json"


def _is_promo_candidate(offer: dict) -> bool:
    if offer.get("status") in {"expired", "listing", "unreachable", "no_offer"}:
        return False
    vu = offer.get("valid_until")
    if vu:
        try:
            if date.fromisoformat(vu[:10]) < date.today():
                return False
        except ValueError:
            pass
    title = (offer.get("title") or "").strip()
    if not title:
        return False
    return _looks_like_real_promo(title, offer.get("price"), offer.get("code"))


def collect_quality_issues() -> list[str]:
    cfg = load_site_config()
    shelved = set(cfg.get("shelved") or [])
    data = json.loads(DATA.read_text(encoding="utf-8"))
    issues: list[str] = []
    for raw in data.get("offers") or []:
        o = dict(raw)
        sanitize_offer(o)
        if o.get("provider") in shelved or not _is_promo_candidate(o):
            continue
        if not offer_passes_quality(o):
            issues.extend(audit_offer(o))
    return issues


def main() -> None:
    issues = collect_quality_issues()
    print(f"quality issues: {len(issues)}")
    for line in issues:
        print("-", line)
    if issues:
        sys.exit(1)


if __name__ == "__main__":
    main()
