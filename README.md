# mealkitdeals promo radar

Public meal-kit / meal-delivery promo radar for **mealkitdeals**.

- Niche: meal delivery / meal kit deals (en-US)
- Runtime: pure Python (stdlib) + GitHub Actions + Cloudflare Pages
- No servers, no runtime LLM, no API keys required
- Config truth: `.ilang/site.ilang` (scraper + build both read it)

## Live site

`https://mealkitdeals.com`

(Pages project: `hellofresh-deals-promo-radar`; canonical domain is set in `.ilang/site.ilang`.)

## Local use

```bash
python scraper.py
python build.py
```

Open `site/index.html`. To change brands, edit `.ilang/site.ilang` only, then re-run.

## Auto update

`.github/workflows/update.yml` runs about every 6 hours (and on relevant pushes): scrape → build → commit `data/offers.json` + `site/`.

## Deploy

Direct upload to the existing Pages project:

```bash
npx wrangler pages deploy site --project-name hellofresh-deals-promo-radar
```

## Monetization

Templates use official brand entry URLs from `AFFILIATE` in `.ilang/site.ilang`. Replace those with your approved affiliate destinations when networks approve the live site. Never invent commission rates.

---

站点规则用 I-Lang 协议描述，见 `.ilang/site.ilang`；协议说明：https://ilang.ai
