# mealkitdeals promo radar

**US meal-kit & prepared-meal promo radar** — open-source pipeline behind **[mealkitdeals.com](https://mealkitdeals.com/)**.

> Repository name `hellofresh-deals-promo-radar` is historical; the live product is **mealkitdeals.com**.

<p align="left">
  <a href="https://mealkitdeals.com/"><img src="https://img.shields.io/badge/website-mealkitdeals.com-0ea5e9?style=flat-square" alt="Website" /></a>
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <a href="https://github.com/longlicode/hellofresh-deals-promo-radar/actions/workflows/update.yml"><img src="https://github.com/longlicode/hellofresh-deals-promo-radar/actions/workflows/update.yml/badge.svg" alt="update-offers CI" /></a>
  <img src="https://img.shields.io/badge/deploy-Cloudflare%20Pages-F38020?style=flat-square&logo=cloudflare&logoColor=white" alt="Cloudflare Pages" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License: MIT" /></a>
</p>

## Features

- **Brand promo pages** — one page per configured meal-kit / meal-delivery brand, built from scraped rows only.
- **Compare view** — side-by-side promo table at [`/compare/`](https://mealkitdeals.com/compare/) (no invented prices or codes).
- **Buyer comparison guides** — intent pages (e.g. HelloFresh vs EveryPlate) with dated, source-linked facts in [`/guides/`](https://mealkitdeals.com/guides/).
- **Open exports** — [`data/offers.json`](data/offers.json), [`public/offers.csv`](public/offers.csv), and [`public/brands.md`](public/brands.md) for reuse with attribution to each row’s `source_url`.
- **Scheduled refresh** — GitHub Actions every **6 hours** (plus manual dispatch); no runtime LLM or paid scrape API on the default path.

## Architecture

```text
.ilang/site.ilang  →  scraper.py  →  data/offers.json
        ↓                                    ↓
   AFFILIATE block                    tools/export_public_assets.py
        ↓                                    ↓
                         build.py  →  site/  →  Cloudflare Pages (mealkitdeals.com)
```

| Layer | Role |
| --- | --- |
| [`.ilang/site.ilang`](.ilang/site.ilang) | Brand list, official scrape URLs, site domain, affiliate outbound rules |
| [`scraper.py`](scraper.py) | Fetches **public** official promo pages (robots-respecting), writes structured offers |
| [`build.py`](build.py) | Renders static HTML under `site/` (generated in CI, not committed) |
| [`.github/workflows/update.yml`](.github/workflows/update.yml) | Scrape → export → build → commit data when changed → deploy |

## Quickstart (local)

```bash
pip install -r requirements.txt
python scraper.py
python tools/export_public_assets.py
python build.py
```

Open `site/index.html` after `build.py`. Push source changes to `main`; CI rebuilds and deploys.

## Data integrity

- Each offer row includes an official **`source_url`** and scrape metadata; missing price, code, or expiry on the source page stays empty (or “Not stated on the official page” in UI)—**never invented**.
- Affiliate outbound URLs live only in the `AFFILIATE` block of `.ilang/site.ilang`.
- Agent and contributor rules: [`AGENTS.md`](AGENTS.md).

## How CI updates production

Workflow [`.github/workflows/update.yml`](.github/workflows/update.yml) on schedule (**every 6 hours**), on relevant pushes to `main`, and on **workflow_dispatch**:

1. `python scraper.py` — refresh offers from official pages  
2. `python tools/export_public_assets.py` — export CSV / brand list  
3. `python build.py` — render `site/`  
4. Commit `data/offers.json` and `public/` when changed  
5. Deploy `site/` to Cloudflare Pages (secrets only in GitHub Actions)

## License

[MIT](LICENSE) — use and fork freely; cite each row’s official `source_url` when republishing data.

---

**Live site:** https://mealkitdeals.com
