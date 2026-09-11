"""Fetch a URL via browser CDP and extract offers with scraper.extract_offers."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper import extract_offers  # noqa: E402


def merge_provider(data_path: Path, provider_name: str, domain: str, source_url: str, html: str) -> int:
    provider = {"name": provider_name, "domain": domain}
    offers = extract_offers(provider, html, source_url)
    data = json.loads(data_path.read_text(encoding="utf-8"))
    kept = [o for o in data.get("offers", []) if o.get("provider") != provider_name]
    kept.extend(offers)
    data["offers"] = kept
    log = data.get("fetch_log") or []
    log.append(
        {
            "provider": provider_name,
            "url": source_url,
            "status": "ok_browser" if offers else "ok_browser_no_promo",
            "offers_extracted": len(offers),
            "http_status": 200,
            "note": "urllib got 403; HTML captured via browser render of official page",
        }
    )
    data["fetch_log"] = log
    data_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{provider_name}: extracted {len(offers)}")
    for o in offers:
        print(" -", o.get("title"), "|", o.get("benefit"), "|", o.get("conditions"), "|", o.get("code"), "|", o.get("valid_until_note") or o.get("valid_until"))
    return len(offers)


if __name__ == "__main__":
    html_path = Path(sys.argv[1])
    provider = sys.argv[2]
    domain = sys.argv[3]
    source_url = sys.argv[4]
    html = html_path.read_text(encoding="utf-8", errors="replace")
    merge_provider(ROOT / "data" / "offers.json", provider, domain, source_url, html)
