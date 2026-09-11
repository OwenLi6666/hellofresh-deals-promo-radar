from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper import fetch  # noqa: E402

st, final, body = fetch("https://dinnerly.com/sitemap.xml")
print("sitemap", st, len(body))
hits = [
    u
    for u in re.findall(r"<loc>([^<]+)</loc>", body)
    if re.search(r"offer|promo|coupon|deal|discount|sale|welcome", u, re.I)
]
print("hits", len(hits))
for u in hits[:40]:
    print(u)

st2, _, b2 = fetch("https://dinnerly.com/")
m = re.search(r"<title>([^<]+)</title>", b2, re.I)
print("title", m.group(1) if m else None)
print("percent", len(re.findall(r"\d+%\s*off", b2, re.I)))
print("dollaroff", len(re.findall(r"\$\d+\s*off", b2, re.I)))
print("permeal", len(re.findall(r"\$\d+(?:\.\d{1,2})?\s*/\s*meal", b2, re.I)))
