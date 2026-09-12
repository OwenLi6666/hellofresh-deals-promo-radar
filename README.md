# mealkitdeals promo radar

Public, open-source pipeline behind **[mealkitdeals.com](https://mealkitdeals.com/)** — a static meal-kit / meal-delivery promo radar for the United States.

## What this site does

[mealkitdeals.com](https://mealkitdeals.com/) publishes **live public promo listings** for meal-kit and prepared-meal brands. Each row is scraped from an official brand page. Prices, codes, and expiry dates are shown only when the source page states them; nothing is invented.

Visitors can browse brand pages, compare offers side by side, and follow outbound links to official sites.

## Where the data comes from

| Source | Location in repo |
| --- | --- |
| Brand list & scrape targets | [`.ilang/site.ilang`](.ilang/site.ilang) |
| Extracted offers (JSON) | [`data/offers.json`](data/offers.json) |
| Public CSV export | [`public/offers.csv`](public/offers.csv) |
| Public brand summary | [`public/brands.md`](public/brands.md) |

The scraper (`scraper.py`) reads `.ilang/site.ilang`, fetches public official promo pages (robots-respecting), and writes structured offer records. `build.py` renders the static HTML site from that data.

## How it updates automatically

GitHub Actions workflow [`.github/workflows/update.yml`](.github/workflows/update.yml) runs on a schedule (**every 6 hours**), on pushes to `main` that touch source/data, and on manual dispatch:

1. `python scraper.py` — refresh offers from official pages  
2. `python tools/export_public_assets.py` — export CSV / brand list  
3. `python build.py` — render `site/` (not committed; built in CI)  
4. Commit `data/offers.json` and `public/` when changed  
5. Deploy `site/` to Cloudflare Pages  

No runtime LLM and no paid API keys are required for the scrape path. Deployment credentials live only in GitHub Actions secrets (never in this repository).

## Local rebuild (optional)

```bash
python scraper.py
python tools/export_public_assets.py
python build.py
```

Open `site/index.html` after `build.py`. Push source changes to `main`; CI rebuilds and deploys.

## Rules

- Missing price, code, or expiry on the official page → field left empty (or “Not stated on the official page” for display). Never invent offers.
- Affiliate outbound URLs are configured in the `AFFILIATE` block of `.ilang/site.ilang`.

## License

Use and fork freely for research and publishing workflows that cite the official `source_url` on each row.

---

**Live site:** https://mealkitdeals.com
