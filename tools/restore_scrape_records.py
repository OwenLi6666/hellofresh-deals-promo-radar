"""Restore provider offers from a prior git snapshot (scrape-time records)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper import _annotate_scrape_record, _cached_offer_still_valid

DATA = ROOT / "data" / "offers.json"
RESTORE_REF = "5b0514d"
RESTORE_PROVIDERS = [
    "HelloFresh",
    "Factor",
    "EveryPlate",
    "Green Chef",
    "Sunbasket",
    "Purple Carrot",
    "Chefs Plate",
    "Dinnerly",
    "Trifecta",
    "Icon Meals",
    "Magic Kitchen",
]


def _load_snapshot(ref: str) -> dict:
    raw = subprocess.check_output(["git", "show", f"{ref}:data/offers.json"], cwd=ROOT)
    return json.loads(raw.decode("utf-8"))


def _offer_key(row: dict) -> tuple[str, str, str]:
    return (
        row.get("provider") or "",
        (row.get("code") or "").upper(),
        (row.get("benefit") or row.get("title") or "").strip().lower()[:90],
    )


def main() -> None:
    hist = _load_snapshot(RESTORE_REF)
    current = json.loads(DATA.read_text(encoding="utf-8"))
    offers = list(current.get("offers") or [])
    have = {_offer_key(o) for o in offers}

    restored: list[dict] = []
    for row in hist.get("offers") or []:
        if row.get("provider") not in RESTORE_PROVIDERS:
            continue
        if not _cached_offer_still_valid(row):
            continue
        key = _offer_key(row)
        if key in have:
            continue
        kept = _annotate_scrape_record(dict(row))
        kept["restored_from"] = RESTORE_REF
        offers.append(kept)
        have.add(key)
        restored.append(kept)

    current["offers"] = offers
    DATA.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    by_provider: dict[str, int] = {}
    for row in restored:
        by_provider[row["provider"]] = by_provider.get(row["provider"], 0) + 1

    print(f"restored {len(restored)} offers from {RESTORE_REF}")
    for name in RESTORE_PROVIDERS:
        count = by_provider.get(name, 0)
        print(f"  {name}: {count}")


if __name__ == "__main__":
    main()
