import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scraper import extract_offers, PROMO_RE
html = (ROOT / "data/_browser_crowdcow.html").read_text(encoding="utf-8")
print("matches", [m.group(0) for m in PROMO_RE.finditer(html)])
print(extract_offers({"name":"Crowd Cow","domain":"crowdcow.com"}, html, "https://www.crowdcow.com/"))
html2 = """<!DOCTYPE html><html><body>
<p>START FREE 7-DAY TRIAL</p>
<p>Try our free 7-day trial</p>
<p>free trial</p>
</body></html>"""
print("prep", extract_offers({"name":"Prep Dish","domain":"prepdish.com"}, html2, "https://prepdish.com/"))
