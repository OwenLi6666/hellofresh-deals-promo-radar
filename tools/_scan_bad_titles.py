#!/usr/bin/env python3
"""Count BAD-pattern titles in local showable list and live compare."""
import html
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from build import is_showable, sanitize_offer  # noqa: E402
from card_presentation import pick_card_lead_offer  # noqa: E402
from ilang_config import load_site_config
import json

BAD = re.compile(
    r"(cart|login|learn more|see menu|national wellness|exclusive benefits include|"
    r"O rders|inside scoop|shop smoothies|^\d{2}\s+\d+%|\+ \$1\b)",
    re.I,
)


def bad_title(t: str) -> bool:
    t = (t or "").strip()
    if len(t) < 8:
        return True
    if BAD.search(t):
        return True
    if t.isupper() and len(t) > 30:
        return True
    if re.search(r",\s*h$", t) or (re.search(r"\s[a-z]$", t) and len(t) > 50):
        return True
    return False


def local_bad() -> list[str]:
    cfg = load_site_config()
    shelved = set(cfg["shelved"])
    data = json.loads((ROOT / "data/offers.json").read_text(encoding="utf-8"))
    from collections import defaultdict

    by = defaultdict(list)
    for o in data["offers"]:
        if o["provider"] in shelved:
            continue
        sanitize_offer(o)
        if is_showable(o):
            by[o["provider"]].append(o)
    hits = []
    for name, rows in by.items():
        top = pick_card_lead_offer(name, rows)
        t = top.get("title", "")
        if bad_title(t):
            hits.append(f"LOCAL {name} | {t[:100]}")
    return hits


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "mealkitdeals-night-patrol/1.0"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", errors="replace")


def live_bad() -> list[str]:
    body = fetch("https://mealkitdeals.com/compare/")
    rows = re.findall(
        r'<tr><td><a href="/providers/[^"]+">([^<]+)</a></td><td>([^<]*)</td>',
        body,
    )
    hits = []
    for brand, title in rows:
        t = html.unescape(title)
        if bad_title(t):
            hits.append(f"LIVE {brand} | {t[:100]}")
    return hits, len(rows)


if __name__ == "__main__":
    lb = local_bad()
    live_hits, n = live_bad()
    print("local_bad", len(lb))
    for x in lb:
        print(x)
    print("live_bad", len(live_hits), "brands", n)
    for x in live_hits:
        print(x)
