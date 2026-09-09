# hellofresh-deals promo radar

Public meal-kit / meal-delivery promo radar for **hellofresh-deals**.

- Niche: meal delivery / meal kit deals (en-US)
- Runtime: pure Python (stdlib) + GitHub Actions + Cloudflare Pages
- No servers, no runtime LLM, no API keys required
- Config truth: `.ilang/site.ilang` (scraper + build both read it)

## Live site

After Cloudflare Pages is connected, the site will be at:

`https://hellofresh-deals-promo-radar.pages.dev`

(Update `.ilang/site.ilang` `@SITE.domain` if the Pages subdomain differs.)

## Local use

```bash
python scraper.py
python build.py
```

Open `site/index.html`. To change brands, edit `.ilang/site.ilang` only, then re-run.

## Auto update

`.github/workflows/update.yml` runs about every 6 hours: scrape → build → commit `data/offers.json`.

Cloudflare Pages build command: `python build.py`  
Output directory: `site`

## Monetization

Templates use official brand entry URLs from `AFFILIATE` in `.ilang/site.ilang`. Replace those with your approved affiliate destinations when networks approve the live site. Never invent commission rates.

## Domain note

Register your own domain ASAP. `*.pages.dev` age accrues to Cloudflare, not you. Bind a custom domain to Pages and set `@SITE.domain` + rebuild so canonical/sitemap use your domain.

---

站点规则用 I-Lang 协议描述，见 `.ilang/site.ilang`；协议说明：https://ilang.ai
