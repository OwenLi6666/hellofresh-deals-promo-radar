"""Print current offers as TSV from ../data/offers.json or ./offers.csv."""
from __future__ import annotations
import csv
import json
from pathlib import Path

root = Path(__file__).resolve().parent
json_path = root.parent / "data" / "offers.json"
csv_path = root / "offers.csv"

cols = ["provider", "benefit", "conditions", "code", "valid_until", "valid_until_note", "source_url"]
print("\t".join(cols))
if json_path.exists():
    data = json.loads(json_path.read_text(encoding="utf-8"))
    for o in data.get("offers") or []:
        print("\t".join(str(o.get(c) or "") for c in cols))
elif csv_path.exists():
    with csv_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            print("\t".join(str(row.get(c) or "") for c in cols))
else:
    raise SystemExit("No offers.json or offers.csv found")
