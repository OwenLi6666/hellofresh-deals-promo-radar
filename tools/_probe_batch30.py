"""Quick urllib probe of candidate brands; print any extract_offers hits."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper import extract_offers, fetch  # noqa: E402

CANDIDATES = [
    ("Territory Foods", "territoryfoods.com", ["https://www.territoryfoods.com/", "https://www.territoryfoods.com/pages/offers"]),
    ("Snap Kitchen", "snapkitchen.com", ["https://www.snapkitchen.com/", "https://www.snapkitchen.com/pages/promotions"]),
    ("Veestro", "veestro.com", ["https://veestro.com/", "https://www.veestro.com/pages/special-offers"]),
    ("Icon Meals", "iconmeals.com", ["https://iconmeals.com/", "https://iconmeals.com/pages/deals"]),
    ("Pete's Paleo", "petespaleo.com", ["https://www.petespaleo.com/"]),
    ("Diet-to-Go", "diettogo.com", ["https://www.diettogo.com/", "https://www.diettogo.com/special-offers/"]),
    ("Magic Kitchen", "magickitchen.com", ["https://www.magickitchen.com/"]),
    ("Crowd Cow", "crowdcow.com", ["https://www.crowdcow.com/", "https://www.crowdcow.com/deals"]),
    ("Prep Dish", "prepdish.com", ["https://prepdish.com/"]),
    ("Metabolic Meals", "mymetabolicmeals.com", ["https://www.mymetabolicmeals.com/"]),
    ("Fresh N Lean", "freshnlean.com", ["https://www.freshnlean.com/"]),
    ("Goodfood", "makegoodfood.ca", ["https://www.makegoodfood.ca/", "https://www.makegoodfood.ca/en/offer"]),
    ("Chefs Plate", "chefsplate.com", ["https://www.chefsplate.com/"]),
    ("RealEats", "realeats.com", ["https://www.realeats.com/"]),
    ("Good Chop", "goodchop.com", ["https://www.goodchop.com/"]),
    ("Omaha Steaks", "omahasteaks.com", ["https://www.omahasteaks.com/"]),
    ("Nutrisystem", "nutrisystem.com", ["https://www.nutrisystem.com/"]),
    ("Jenny Craig", "jennycraig.com", ["https://www.jennycraig.com/"]),
    ("Actifai / Territory", "x", []),
    ("CookUnity already", "x", []),
    ("Meal Prep Heroes", "mealprepheroes.com", ["https://mealprepheroes.com/"]),
    ("MacroPlate", "macroplate.com", ["https://www.macroplate.com/"]),
    ("Trifecta already", "x", []),
    ("Factor already", "x", []),
    ("Green Chef already", "x", []),
    ("EveryPlate already", "x", []),
    ("Sunbasket already", "x", []),
    ("Purple Carrot already", "x", []),
    ("Dinnerly already", "x", []),
    ("ButcherBox already", "x", []),
    ("Hungryroot already", "x", []),
    ("Sprig", "sprig.com", ["https://www.sprig.com/"]),
    ("Terra's Kitchen", "terraskitchen.com", ["https://www.terraskitchen.com/"]),
    ("Martha Stewart & Marley Spoon", "x", []),
    ("Dinner Delivery Canada", "x", []),
    ("HelloFresh CA", "hellofresh.ca", ["https://www.hellofresh.ca/"]),
    ("Factor_CA", "factor75.ca", ["https://www.factor75.ca/"]),
    ("Green Chef CA", "greenchef.ca", ["https://www.greenchef.ca/"]),
    ("Freshly", "freshly.com", ["https://www.freshly.com/"]),
    ("Applegate", "applegate.com", ["https://www.applegate.com/"]),
    ("True Food Kitchen kits", "x", []),
    ("Epicured", "epicured.com", ["https://www.epicured.com/"]),
    ("ModifyHealth already", "x", []),
    ("Clean Eatz already", "x", []),
    ("Splendid Spoon already", "x", []),
    ("Daily Harvest already", "x", []),
    ("Sakara already", "x", []),
    ("Mosaic already", "x", []),
    ("Thistle already", "x", []),
    ("Gobble already", "x", []),
    ("Home Chef already", "x", []),
    ("Blue Apron already", "x", []),
    ("Marley Spoon already", "x", []),
    ("CookUnity already2", "x", []),
    ("Hungryroot already2", "x", []),
    ("Trifecta Nutrition already", "x", []),
    ("Sprouts meal kits", "x", []),
    ("Kettlebell Kitchen", "kettlebellkitchen.com", ["https://www.kettlebellkitchen.com/"]),
    ("Performance Kitchen", "performkitchen.com", ["https://performkitchen.com/"]),
    ("Freshly Canadian", "x", []),
    ("MamaSezz", "mamasezz.com", ["https://www.mamasezz.com/"]),
    ("Purple Carrot already2", "x", []),
    ("Sunbasket already2", "x", []),
    ("Veestro2", "veestro.com", ["https://www.veestro.com/"]),
    ("Snap2", "snapkitchen.com", ["https://order.snapkitchen.com/"]),
    ("Territory2", "territoryfoods.com", ["https://territoryfoods.com/"]),
    ("Icon2", "iconmeals.com", ["https://www.iconmeals.com/collections/deals"]),
    ("DietToGo2", "diettogo.com", ["https://www.diettogo.com/current-specials.html"]),
    ("CrowdCow2", "crowdcow.com", ["https://www.crowdcow.com/collections/deals"]),
    ("GoodChop2", "goodchop.com", ["https://www.goodchop.com/pages/offer"]),
    ("Metabolic2", "mymetabolicmeals.com", ["https://www.mymetabolicmeals.com/pages/special-offer"]),
    ("PrepDish2", "prepdish.com", ["https://prepdish.com/pages/special-offer"]),
    ("Magic2", "magickitchen.com", ["https://www.magickitchen.com/specials/"]),
    ("Pete2", "petespaleo.com", ["https://www.petespaleo.com/collections/sale"]),
    ("Epicured2", "epicured.com", ["https://www.epicured.com/pages/offers"]),
    ("MamaSezz2", "mamasezz.com", ["https://www.mamasezz.com/pages/special-offer"]),
    ("MacroPlate2", "macroplate.com", ["https://www.macroplate.com/pages/offer"]),
    ("Performance2", "performkitchen.com", ["https://performkitchen.com/pages/specials"]),
    ("Nutrisystem2", "nutrisystem.com", ["https://www.nutrisystem.com/js/cms/sp/current-offer"]),
    ("RealEats2", "realeats.com", ["https://www.realeats.com/pages/offer"]),
]

hits = []
fails = []
for name, domain, urls in CANDIDATES:
    if not urls:
        continue
    best = []
    notes = []
    for url in urls:
        st, final, body = fetch(url)
        if st == 200 and not str(body).startswith("__ERROR__"):
            offers = extract_offers({"name": name, "domain": domain}, body, final)
            notes.append(f"{st}:{len(offers)}:{final}")
            if offers:
                best = offers
                break
        else:
            notes.append(f"{st}:{final}")
    if best:
        hits.append((name, best, notes))
        print(f"HIT {name}: {len(best)}")
        for o in best:
            print("  -", (o.get("title") or "")[:90])
    else:
        fails.append((name, notes))
        print(f"MISS {name}: {notes}")

print("\n=== SUMMARY hits", len(hits), "miss", len(fails), "===")
