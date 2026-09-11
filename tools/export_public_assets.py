# ::ILANG
# [TYPE:tool][FILE:tools/export_public_assets.py]
# ::OBJECTIVE{export_citeable_assets}
#   target: Write public CSV + Markdown brand list from data/offers.json for reuse
"""Export citeable public assets from scraped offers. Stdlib only."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "offers.json"
OUT_DIR = ROOT / "public"


FIELDS = [
    "provider",
    "domain",
    "title",
    "benefit",
    "conditions",
    "code",
    "code_required",
    "valid_until",
    "valid_until_note",
    "source_url",
    "offer_url",
    "status",
    "fetched_at",
]


def main() -> None:
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    offers = payload.get("offers") or []
    providers = payload.get("providers") or []
    generated = payload.get("generated_at") or datetime.now(timezone.utc).isoformat()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    csv_path = OUT_DIR / "offers.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for o in offers:
            row = {k: o.get(k, "") for k in FIELDS}
            w.writerow(row)

    # Brand list with live top offer (no invented fields)
    by_p: dict[str, list[dict]] = {}
    for o in offers:
        by_p.setdefault(o.get("provider") or "Unknown", []).append(o)

    lines = [
        "# Meal kit / meal delivery brands tracked by mealkitdeals",
        "",
        f"Generated from `data/offers.json` at `{generated}`.",
        "",
        "Live listings: https://mealkitdeals.com/",
        "",
        "Only fields present in the scrape are shown. Empty means the official public page did not expose that detail.",
        "",
        "| Brand | Domain | Live listings | Top extracted title | Source URL |",
        "| --- | --- | ---: | --- | --- |",
    ]
    order = providers or sorted(by_p.keys())
    for name in order:
        rows = by_p.get(name, [])
        domain = rows[0].get("domain", "") if rows else ""
        title = (rows[0].get("title") or "").replace("|", "/") if rows else "(none extracted)"
        src = rows[0].get("source_url") or "" if rows else ""
        lines.append(f"| {name} | {domain} | {len(rows)} | {title} | {src} |")

    lines.extend(
        [
            "",
            "## Machine-readable offers",
            "",
            "- CSV: [`public/offers.csv`](offers.csv)",
            "- JSON: [`data/offers.json`](../data/offers.json)",
            "",
            "## Compare table",
            "",
            "Side-by-side view on the site: https://mealkitdeals.com/compare/",
            "",
        ]
    )
    (OUT_DIR / "brands.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Tiny CLI helper: print active offers as TSV (useful, not a placeholder)
    helper = OUT_DIR / "print_offers.py"
    helper.write_text(
        '''"""Print current offers as TSV from ../data/offers.json or ./offers.csv."""
from __future__ import annotations
import csv
import json
from pathlib import Path

root = Path(__file__).resolve().parent
json_path = root.parent / "data" / "offers.json"
csv_path = root / "offers.csv"

cols = ["provider", "benefit", "conditions", "code", "valid_until", "valid_until_note", "source_url"]
print("\\t".join(cols))
if json_path.exists():
    data = json.loads(json_path.read_text(encoding="utf-8"))
    for o in data.get("offers") or []:
        print("\\t".join(str(o.get(c) or "") for c in cols))
elif csv_path.exists():
    with csv_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            print("\\t".join(str(row.get(c) or "") for c in cols))
else:
    raise SystemExit("No offers.json or offers.csv found")
''',
        encoding="utf-8",
    )

    print(f"Wrote {csv_path} ({len(offers)} rows)")
    print(f"Wrote {OUT_DIR / 'brands.md'} ({len(order)} brands)")
    print(f"Wrote {helper}")


if __name__ == "__main__":
    main()
