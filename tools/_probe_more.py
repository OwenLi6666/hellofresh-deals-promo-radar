"""Probe additional meal-kit brands via urllib extract_offers."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper import extract_offers, fetch, robots_allows  # noqa: E402

MORE = [
    ("Fresh N Lean", "freshnlean.com", ["https://www.freshnlean.com/", "https://freshnlean.com/"]),
    ("Trifecta", "trifectanutrition.com", ["https://www.trifectanutrition.com/", "https://www.trifecta.com/"]),
    ("Territory Foods", "territoryfoods.com", ["https://www.territoryfoods.com/"]),
    ("BistroMD", "bistromd.com", ["https://www.bistromd.com/", "https://www.bistromd.com/pages/special-offers"]),
    ("Snap Kitchen", "snapkitchen.com", ["https://www.snapkitchen.com/"]),
    ("Veestro", "veestro.com", ["https://veestro.com/", "https://www.veestro.com/"]),
    ("Icon Meals", "iconmeals.com", ["https://iconmeals.com/"]),
    ("Pete's Paleo", "petespaleo.com", ["https://www.petespaleo.com/"]),
    ("Diet-to-Go", "diettogo.com", ["https://www.diettogo.com/"]),
    ("Magic Kitchen", "magickitchen.com", ["https://www.magickitchen.com/"]),
    ("RealEats", "realeats.com", ["https://www.realeats.com/"]),
    ("Martha & Marley Spoon", "marleyspoon.com", ["https://marleyspoon.com/"]),  # may overlap
    ("Chefs Plate", "chefsplate.com", ["https://www.chefsplate.com/"]),
    ("Goodfood", "makegoodfood.ca", ["https://www.makegoodfood.ca/"]),
    ("Factor_alt", "factor75.com", []),  # skip
    ("Home Chef already", "x", []),
    ("Hungryroot already", "x", []),
    ("ButcherBox", "butcherbox.com", ["https://www.butcherbox.com/", "https://www.butcherbox.com/deals/"]),
    ("Crowd Cow", "crowdcow.com", ["https://www.crowdcow.com/"]),
    ("Prep Dish", "prepdish.com", ["https://prepdish.com/"]),
    ("Dinnerly offer path", "dinnerly.com", ["https://dinnerly.com/select-plan", "https://dinnerly.com/how"]),
    ("Sunbasket try", "sunbasket.com", ["https://sunbasket.com/menu"]),
    ("Purple Carrot try", "purplecarrot.com", ["https://www.purplecarrot.com/plant-based-meal-delivery"]),
    ("Metabolic Meals", "mymetabolicmeals.com", ["https://www.mymetabolicmeals.com/"]),
    ("Trifecta Nutrition", "trifectanutrition.com", ["https://www.trifectanutrition.com/meal-delivery"]),
]

for name, domain, urls in MORE:
    if not urls:
        continue
    print(f"\n=== {name} ===")
    robots = f"https://www.{domain}/robots.txt"
    for url in urls:
        allowed = robots_allows(robots, url)
        st, final, body = fetch(url)
        n = 0
        titles = []
        if st == 200 and not str(body).startswith("__ERROR__"):
            offers = extract_offers({"name": name, "domain": domain}, body, final)
            n = len(offers)
            titles = [(o.get("title") or "")[:70] for o in offers]
        print(f"  {st} offers={n} {final}")
        for t in titles:
            print("   -", t)
