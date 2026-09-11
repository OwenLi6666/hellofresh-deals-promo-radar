"""Probe candidate meal-kit brand URLs; print HTTP status + extract_offers count."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper import extract_offers, fetch, robots_allows  # noqa: E402

CANDIDATES: list[tuple[str, str, list[str]]] = [
    (
        "EveryPlate",
        "everyplate.com",
        [
            "https://www.everyplate.com/robots.txt",
            "https://www.everyplate.com/sitemap.xml",
            "https://www.everyplate.com/",
            "https://www.everyplate.com/pages/promotions",
            "https://www.everyplate.com/eat/coupon-codes-and-promotions",
            "https://blog.everyplate.com/",
        ],
    ),
    (
        "Green Chef",
        "greenchef.com",
        [
            "https://www.greenchef.com/robots.txt",
            "https://www.greenchef.com/sitemap.xml",
            "https://www.greenchef.com/",
            "https://www.greenchef.com/pages/promotions",
            "https://blog.greenchef.com/",
            "https://www.greenchef.com/offers",
        ],
    ),
    (
        "Dinnerly",
        "dinnerly.com",
        [
            "https://dinnerly.com/robots.txt",
            "https://dinnerly.com/sitemap.xml",
            "https://www.dinnerly.com/",
            "https://dinnerly.com/",
            "https://dinnerly.com/offer",
            "https://blog.dinnerly.com/",
        ],
    ),
    (
        "Sunbasket",
        "sunbasket.com",
        [
            "https://sunbasket.com/robots.txt",
            "https://sunbasket.com/sitemap.xml",
            "https://sunbasket.com/",
            "https://www.sunbasket.com/",
            "https://sunbasket.com/promo",
            "https://blog.sunbasket.com/",
        ],
    ),
    (
        "Purple Carrot",
        "purplecarrot.com",
        [
            "https://www.purplecarrot.com/robots.txt",
            "https://www.purplecarrot.com/sitemap.xml",
            "https://www.purplecarrot.com/",
            "https://www.purplecarrot.com/pages/promotions",
            "https://blog.purplecarrot.com/",
            "https://www.purplecarrot.com/offers",
        ],
    ),
]


def main() -> None:
    for name, domain, urls in CANDIDATES:
        print(f"\n=== {name} ({domain}) ===")
        robots = next((u for u in urls if u.endswith("robots.txt")), f"https://www.{domain}/robots.txt")
        for url in urls:
            if url.endswith("robots.txt"):
                st, final, body = fetch(url)
                print(f"  robots {st} {final} len={len(body)}")
                continue
            allowed = robots_allows(robots, url)
            st, final, body = fetch(url)
            n = 0
            titles: list[str] = []
            if st == 200 and not body.startswith("__ERROR__"):
                offers = extract_offers({"name": name, "domain": domain}, body, final)
                n = len(offers)
                titles = [o.get("title", "")[:70] for o in offers]
            print(f"  {st} allowed={allowed} offers={n} {final}")
            for t in titles:
                print(f"      - {t}")


if __name__ == "__main__":
    main()
