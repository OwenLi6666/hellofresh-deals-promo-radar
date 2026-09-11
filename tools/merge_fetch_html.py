"""Fetch URL via urllib and merge extract_offers into offers.json."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper import fetch  # noqa: E402
from tools.merge_browser_html import merge_provider  # noqa: E402


def main() -> None:
    provider, domain, url = sys.argv[1], sys.argv[2], sys.argv[3]
    st, final, body = fetch(url)
    if st != 200 or str(body).startswith("__ERROR__"):
        print(f"FAIL {provider} status={st} {final}")
        sys.exit(1)
    # save raw for audit
    safe = provider.lower().replace(" ", "").replace("'", "")
    path = ROOT / "data" / f"_browser_{safe}.html"
    path.write_text(body if isinstance(body, str) else body.decode("utf-8", "replace"), encoding="utf-8")
    n = merge_provider(ROOT / "data" / "offers.json", provider, domain, final, path.read_text(encoding="utf-8", errors="replace"))
    if n == 0:
        print(f"NO_PROMO {provider}")
        sys.exit(2)


if __name__ == "__main__":
    main()
