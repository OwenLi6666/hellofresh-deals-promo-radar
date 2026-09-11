# mealkitdeals promo radar

Open-source scraper and static site generator that collects **public** meal-kit / meal-delivery promo text from official brand pages (robots-respecting, no invented prices or codes).

Live listings: https://mealkitdeals.com/

## What you can reuse

| Asset | Path | Notes |
| --- | --- | --- |
| Offers CSV | [`public/offers.csv`](public/offers.csv) | One row per extracted offer: benefit, conditions, code, source URL, fetch time |
| Brand list | [`public/brands.md`](public/brands.md) | 15 tracked brands with listing counts and source URLs |
| Full JSON | [`data/offers.json`](data/offers.json) | Same data plus scrape log |
| Compare UI | https://mealkitdeals.com/compare/ | Side-by-side table rendered from the scrape |
| Print helper | [`public/print_offers.py`](public/print_offers.py) | Prints current offers as TSV |

Regenerate CSV/MD after a scrape:

```bash
python scraper.py
python tools/export_public_assets.py
python build.py
```

## Stack

- Pure Python (stdlib) + GitHub Actions + Cloudflare Pages
- Config truth: [`.ilang/site.ilang`](.ilang/site.ilang)
- No runtime LLM, no paid API keys required for the scrape path

## Local use

```bash
python scraper.py
python tools/export_public_assets.py
python build.py
```

Open `site/index.html`. To change brands, edit `.ilang/site.ilang` only, then re-run.

## Auto update

`.github/workflows/update.yml` runs about every 6 hours (and on relevant pushes): scrape → build → commit `data/offers.json` + `site/`.

## Deploy

```bash
npx wrangler pages deploy site --project-name hellofresh-deals-promo-radar
```

## Rules

- Missing price / code / expiry on the official page → field left empty (or `官方页未标` for expiry display). Never invent offers.
- Affiliate destinations live in `AFFILIATE` inside `.ilang/site.ilang`; swap in approved network links only after acceptance.

## License

Use and fork freely for research and publishing workflows that cite the official `source_url` on each row.
