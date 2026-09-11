import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scraper import extract_offers, _looks_like_real_promo, _clean_title

ROOT = Path(__file__).resolve().parents[1]
html = (ROOT / "data/_browser_butcherbox.html").read_text(encoding="utf-8")
line = [x for x in html.splitlines() if "100" in x][0]
plain = line.replace("<p>", "").replace("</p>", "")
print("plain:", plain)
print("clean:", _clean_title(plain))
print("looks:", _looks_like_real_promo(plain, None, None))
print("offers:", extract_offers({"name": "ButcherBox", "domain": "butcherbox.com"}, html, "https://www.butcherbox.com/"))

html2 = (ROOT / "data/_browser_trifecta.html").read_text(encoding="utf-8")
print("trifecta:", extract_offers({"name": "Trifecta", "domain": "trifectanutrition.com"}, html2, "https://www.trifectanutrition.com/"))
