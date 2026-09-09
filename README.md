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

`.github/workflows/update.yml` runs about every 6 hours (and on relevant pushes): scrape → build → commit `data/offers.json` + `site/`.

## Cloudflare Pages (step 7)

1. Open [Cloudflare Dashboard → Workers & Pages → Create → Pages → Connect to Git](https://dash.cloudflare.com/?to=/:account/pages)
2. Select repo `OwenLi6666/hellofresh-deals-promo-radar`, branch `main`
3. Build settings:
   - **Framework preset:** None
   - **Build command:** *(leave empty)* — Actions already commits `site/`
   - **Build output directory:** `site`
4. Save and deploy. Production URL should be `https://hellofresh-deals-promo-radar.pages.dev` (or the project name you chose).
5. If the subdomain differs, set `@SITE.domain` in `.ilang/site.ilang` and re-run the workflow.

Optional CLI deploy (needs `CLOUDFLARE_API_TOKEN` + account login):

```bash
npx wrangler pages project create hellofresh-deals-promo-radar --production-branch main
npx wrangler pages deploy site --project-name hellofresh-deals-promo-radar
```

## Monetization

Templates use official brand entry URLs from `AFFILIATE` in `.ilang/site.ilang`. Replace those with your approved affiliate destinations when networks approve the live site. Never invent commission rates.

## Domain note

Register your own domain ASAP. `*.pages.dev` age accrues to Cloudflare, not you. Bind a custom domain to Pages and set `@SITE.domain` + rebuild so canonical/sitemap use your domain.

---

站点规则用 I-Lang 协议描述，见 `.ilang/site.ilang`；协议说明：https://ilang.ai
