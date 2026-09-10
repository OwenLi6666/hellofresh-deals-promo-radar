# ::ILANG
# [TYPE:tool][FILE:build.py]
# ::OBJECTIVE{render_static_site}
#   target: 读 site.ilang + data/offers.json 渲染 site/ 含 JSON-LD sitemap robots
# ::BOUNDARY{never:编 price 或缺字段时伪造结构化数据}
"""Render static coupon site from offers.json. Stdlib only.

URL scheme: extensionless paths via directory index files
  /compare           -> site/compare/index.html
  /providers/{slug}  -> site/providers/{slug}/index.html
  /deals/{id}        -> site/deals/{id}/index.html
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from string import Template
from typing import Any

from ilang_config import ROOT, load_site_config

DATA_PATH = ROOT / "data" / "offers.json"
SITE_DIR = ROOT / "site"
TPL_DIR = ROOT / "templates"

FOOTER_LINKS_HTML = (
    '<p class="footer-links">'
    '<a href="/about/">About</a> '
    '<a href="/contact/">Contact</a> '
    '<a href="/privacy/">Privacy</a> '
    '<a href="/compare/">Compare</a>'
    "</p>"
)
NAV_LINKS_HTML = (
    '<a href="/">Home</a>\n'
    '        <a href="/compare/">Compare</a>\n'
    '        <a href="/about/">About</a>\n'
    '        <a href="/contact/">Contact</a>'
)


def nav_links_html(include_contact: bool = True) -> str:
    links = [
        '<a href="/">Home</a>',
        '<a href="/compare/">Compare</a>',
        '<a href="/about/">About</a>',
    ]
    if include_contact:
        links.append('<a href="/contact/">Contact</a>')
    return "\n        ".join(links)


def footer_links_html(include_contact: bool = True) -> str:
    parts = ['<a href="/about/">About</a>']
    if include_contact:
        parts.append('<a href="/contact/">Contact</a>')
    parts.extend(['<a href="/privacy/">Privacy</a>', '<a href="/compare/">Compare</a>'])
    return '<p class="footer-links">' + " ".join(parts) + "</p>"


def slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:80] or "offer"


def offer_id(offer: dict[str, Any]) -> str:
    base = f"{offer.get('provider','')}-{offer.get('title','')}-{offer.get('offer_url','')}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
    return f"{slugify(offer.get('provider', 'x'))}-{slugify(offer.get('title', 'offer'))[:40]}-{h}"


def load_offers() -> dict[str, Any]:
    if not DATA_PATH.exists():
        return {
            "brand": "mealkitdeals",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "offers": [],
            "providers": [],
        }
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def is_showable(offer: dict[str, Any]) -> bool:
    # Never surface fluff / unreachable placeholders as deals
    if offer.get("status") in {"expired", "listing", "unreachable", "no_offer"}:
        return False
    vu = offer.get("valid_until")
    if vu:
        try:
            if date.fromisoformat(vu[:10]) < date.today():
                return False
        except ValueError:
            pass
    title = (offer.get("title") or "").lower()
    if "check current promotions" in title or "temporarily unreachable" in title:
        return False
    return True


def month_label() -> str:
    return datetime.now(timezone.utc).strftime("%B %Y")


def read_tpl(name: str) -> Template:
    return Template((TPL_DIR / name).read_text(encoding="utf-8"))


def tpl_escape(value: Any) -> str:
    """Values are inserted literally by string.Template — do not double '$'."""
    return str(value)


def render_tpl(name: str, mapping: dict[str, Any]) -> str:
    safe = {k: tpl_escape(v) for k, v in mapping.items()}
    return read_tpl(name).safe_substitute(safe)


def normalize_offer_title(title: str) -> str:
    """Display-time cleanup for UI crumbs; never invents new offer claims."""
    from html import unescape

    title = unescape(title or "")
    title = re.sub(r"\s+", " ", title).strip()
    if re.search(r"(?i)successfully applied|code successfully", title):
        m = re.search(
            r"(?i)(\d+\s*free meals?(?:\s*\+\s*free shipping)?(?:\s+on\s+(?:your\s+)?first\s+box)?)",
            title,
        )
        if m:
            title = m.group(1).strip()
            title = title[0].upper() + title[1:]
    title = re.sub(r"(?i)\s*see\s*t&?\s*cs\.?\s*$", "", title)
    title = re.sub(r"(?i)\s*see\s*terms(?:\s*(?:and|&)\s*conditions)?\.?\s*$", "", title)
    title = re.sub(r"[\ufffd]+", "", title)
    # Drop brand suffix pipes like "| CookUnity"
    title = re.sub(r"\s*\|\s*[A-Za-z][A-Za-z0-9 &'-]{1,40}$", "", title)
    return title.strip(" -–|:;,.")


def abs_url(domain: str, path: str) -> str:
    domain = domain.rstrip("/")
    if not domain.startswith("http"):
        domain = "https://" + domain
    if not path.startswith("/"):
        path = "/" + path
    # Directory indexes on Cloudflare Pages live at trailing-slash URLs;
    # non-slash requests 308 to slash — keep page canonicals on the slash form.
    # File assets (sitemap.xml, robots.txt, *.css, …) must NOT get a trailing slash.
    is_file = bool(re.search(r"\.[A-Za-z0-9]{1,8}$", path.rstrip("/")))
    if is_file:
        path = path.rstrip("/")
    elif path != "/" and not path.endswith("/"):
        path = path + "/"
    return domain + path


def page_path(*parts: str) -> str:
    """Extensionless public path with trailing slash for CF Pages directory indexes.

    Example: ('providers','hellofresh') -> /providers/hellofresh/
    """
    clean = [p.strip("/") for p in parts if p and p.strip("/")]
    if not clean:
        return "/"
    return "/" + "/".join(clean) + "/"


def write_page(rel_path: str, content: str) -> None:
    """Write HTML as directory index so /path/ serves without .html."""
    rel = rel_path.strip("/")
    if not rel or rel == "index":
        out = SITE_DIR / "index.html"
    else:
        out = SITE_DIR / rel / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")


def json_ld_offer(offer: dict[str, Any], page_url: str) -> dict[str, Any]:
    node: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Offer",
        "name": offer.get("title"),
        "url": offer.get("offer_url") or page_url,
        "availability": "https://schema.org/InStock"
        if offer.get("status") in {"active", "listing"}
        else "https://schema.org/SoldOut",
    }
    if offer.get("price"):
        node["price"] = str(offer["price"])
        node["priceCurrency"] = offer.get("currency") or "USD"
    if offer.get("valid_until"):
        node["priceValidUntil"] = offer["valid_until"][:10]
    seller = {"@type": "Organization", "name": offer.get("provider")}
    if offer.get("domain"):
        seller["url"] = f"https://{offer['domain']}"
    node["seller"] = seller
    return node


def clean_output_dirs() -> None:
    """Remove prior page trees so leftover .html files cannot leak old URLs."""
    for name in ("providers", "deals", "compare", "about", "contact", "privacy"):
        target = SITE_DIR / name
        if target.exists():
            shutil.rmtree(target)
    for stale in ("compare.html", "404.html"):
        p = SITE_DIR / stale
        if p.exists():
            p.unlink()


def build_static_pages(
    brand: str,
    domain: str,
    affiliate_note: str,
    base_vars: dict[str, Any],
    cfg: dict[str, Any],
) -> list[tuple[str, str]]:
    """Emit About / Contact / Privacy trust pages. Never invent contact email."""
    pub = cfg.get("publisher") or {}
    contact_email = (pub.get("contact_email") or "").strip()
    about_operator = (pub.get("about_operator") or "").strip()
    written: list[tuple[str, str]] = []

    about_who = (
        html.escape(about_operator)
        if about_operator
        else "the independent publisher of this site"
    )
    about_body = f"""
        <p><strong>{html.escape(brand)}</strong> is a meal-kit promo radar: we list publicly visible promotions scraped from official brand pages.</p>
        <p>It is operated by {about_who}. The site is a static Cloudflare Pages site built from a public GitHub repository. Listings update automatically from public sources.</p>
        <p>We only show titles, prices, promo codes, and expiry dates when those fields are extracted from official pages. We do not invent offers, prices, codes, or valid-through dates.</p>
        <p>Outbound brand links may be affiliate links. Third-party advertising may appear on the site in the future; see the Privacy page for how that works.</p>
    """
    about_path = page_path("about")
    about_html = render_tpl(
        "static.html",
        {
            **base_vars,
            "title": f"About — {brand}",
            "description": f"Who runs {brand} and what this meal-kit promo radar does.",
            "canonical": abs_url(domain, about_path),
            "og_title": f"About {brand}",
            "eyebrow": "About",
            "heading": f"About {brand}",
            "body": about_body,
        },
    )
    write_page(about_path, about_html)
    written.append((about_path, about_html))

    if contact_email and "@" in contact_email:
        contact_body = f"""
        <p>Questions about listings, corrections, or partnership inquiries:</p>
        <p><a href="mailto:{html.escape(contact_email)}">{html.escape(contact_email)}</a></p>
        <p>Please include the page URL if you are reporting an incorrect or outdated promo listing.</p>
        """
        contact_path = page_path("contact")
        contact_html = render_tpl(
            "static.html",
            {
                **base_vars,
                "title": f"Contact — {brand}",
                "description": f"Contact the publisher of {brand}.",
                "canonical": abs_url(domain, contact_path),
                "og_title": f"Contact {brand}",
                "eyebrow": "Contact",
                "heading": "Contact",
                "body": contact_body,
            },
        )
        write_page(contact_path, contact_html)
        written.append((contact_path, contact_html))

    privacy_body = f"""
        <p>This Privacy Policy applies to <strong>{html.escape(brand)}</strong> at <strong>{html.escape(domain)}</strong>, a static meal-kit promo radar hosted on Cloudflare Pages.</p>
        <p><strong>What we collect.</strong> The public site itself does not run a member login and does not ask you to create an account. Standard web server / CDN logs (such as IP address, user agent, and requested URL) may be processed by Cloudflare while serving the site. We do not sell personal information.</p>
        <p><strong>Affiliate links.</strong> Some outbound links to meal-kit brands may be affiliate links. If you click them and later subscribe or purchase, we may earn a commission at no extra cost to you. Affiliate networks and brand sites have their own privacy policies.</p>
        <p><strong>Third-party advertising.</strong> The site is prepared to display third-party ads (for example display or affiliate network creatives). Ad partners may use cookies or similar technologies to measure impressions or personalize ads. When ad codes are added, those partners' policies also apply. We will not invent tracking that is not actually installed.</p>
        <p><strong>Scraped listings.</strong> Promo titles, codes, and prices shown on this site come from publicly available brand pages. We do not invent missing fields.</p>
        <p><strong>Contact.</strong> For privacy questions, use the email on the <a href="/contact/">Contact</a> page once published.</p>
        <p>Last updated: {html.escape(date.today().isoformat())}.</p>
    """
    privacy_path = page_path("privacy")
    privacy_html = render_tpl(
        "static.html",
        {
            **base_vars,
            "title": f"Privacy Policy — {brand}",
            "description": f"Privacy Policy for {brand}, including affiliate links and third-party ads.",
            "canonical": abs_url(domain, privacy_path),
            "og_title": f"Privacy — {brand}",
            "eyebrow": "Legal",
            "heading": "Privacy Policy",
            "body": privacy_body,
        },
    )
    write_page(privacy_path, privacy_html)
    written.append((privacy_path, privacy_html))
    return written


def render() -> None:
    cfg = load_site_config()
    data = load_offers()
    site = cfg["site"]
    brand = site.get("brand") or data.get("brand") or "mealkitdeals"
    domain = site.get("domain") or data.get("domain") or "localhost"
    niche = site.get("niche") or data.get("niche") or "meal kit deals"
    affiliate_note = cfg["affiliate_note"]
    affiliates = cfg["affiliates"]
    pub = cfg.get("publisher") or {}
    has_contact = bool((pub.get("contact_email") or "").strip() and "@" in (pub.get("contact_email") or ""))

    offers = [o for o in data.get("offers", []) if is_showable(o)]
    for o in offers:
        o["title"] = normalize_offer_title(o.get("title") or "")
        if o.get("snippet"):
            sn = normalize_offer_title(o.get("snippet") or "")
            # Avoid repeating the same sentence under the card title
            if sn.lower() == (o.get("title") or "").lower() or (o.get("title") or "").lower() in sn.lower():
                o["snippet"] = ""
            else:
                o["snippet"] = sn
        o["_id"] = offer_id(o)
        o["_affiliate"] = affiliates.get(o.get("provider", ""), o.get("offer_url", "#"))

    by_provider: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for o in offers:
        by_provider[o.get("provider", "Unknown")].append(o)

    # Prefer config provider order
    provider_order = [p["name"] for p in cfg["providers"]]
    for name in by_provider:
        if name not in provider_order:
            provider_order.append(name)

    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "assets").mkdir(exist_ok=True)
    clean_output_dirs()

    month = month_label()
    generated = data.get("generated_at") or datetime.now(timezone.utc).isoformat()
    base_vars = {
        "brand": html.escape(brand),
        "niche": html.escape(niche),
        "month": html.escape(month),
        "generated": html.escape(str(generated)),
        "affiliate_note": html.escape(affiliate_note),
        "canonical_home": abs_url(domain, "/"),
        "year": str(datetime.now(timezone.utc).year),
        "nav_links": nav_links_html(has_contact),
        "footer_links": footer_links_html(has_contact),
    }

    # CSS
    (SITE_DIR / "assets" / "style.css").write_text(
        (TPL_DIR / "style.css").read_text(encoding="utf-8"), encoding="utf-8"
    )

    # Index cards — include providers with zero offers (honest empty), skip none from config
    cards = []
    for name in provider_order:
        rows = by_provider.get(name, [])
        top_title = rows[0].get("title", name) if rows else f"{name}: no public promo extracted yet"
        snip = rows[0].get("snippet") if rows else ""
        if not snip and rows:
            # Short meta line — not a second copy of the title
            bits = []
            if rows[0].get("code"):
                bits.append(f"Code {rows[0]['code']}")
            if rows[0].get("valid_until"):
                bits.append(f"Until {rows[0]['valid_until']}")
            snip = " · ".join(bits) if bits else "From official public promo pages."
        if not rows:
            snip = "No public promo phrase/code extracted from official pages. We do not invent deals."
        provider_href = page_path("providers", slugify(name))
        cards.append(
            f"""
            <article class="card">
              <p class="eyebrow">{html.escape(name)}</p>
              <h2><a href="{provider_href}">{html.escape(top_title)}</a></h2>
              <p>{html.escape(snip)}</p>
              <p class="meta">{len(rows)} live listing(s)</p>
              <a class="btn" href="{provider_href}">View {html.escape(name)}</a>
            </article>
            """
        )

    item_list = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i + 1,
                "url": abs_url(domain, page_path("providers", slugify(name))),
                "name": name,
            }
            for i, name in enumerate(provider_order)
        ],
    }

    index_html = render_tpl(
        "index.html",
        {
            **base_vars,
            "title": f"{brand} — {niche} promo radar ({month})",
            "description": f"Live public promo listings for meal kits: {', '.join(provider_order[:6])}. Updated {month}.",
            "canonical": abs_url(domain, "/"),
            "og_title": f"{brand} meal kit deals — {month}",
            "cards": "\n".join(cards) or "<p>No offers extracted yet. Pipeline will retry.</p>",
            "json_ld": json.dumps(item_list, ensure_ascii=False),
            "offer_count": str(len(offers)),
            "provider_count": str(len(provider_order)),
        },
    )
    write_page("/", index_html)

    # Compare page — only rows with real offers
    compare_rows = []
    compare_list = []
    pos = 0
    for name in provider_order:
        rows = by_provider.get(name, [])
        if not rows:
            continue
        pos += 1
        top = rows[0]
        provider_href = page_path("providers", slugify(name))
        price_cell = f"${html.escape(str(top['price']))}" if top.get("price") else "—"
        code_cell = html.escape(str(top["code"])) if top.get("code") else "—"
        compare_rows.append(
            f"<tr><td><a href=\"{provider_href}\">{html.escape(name)}</a></td>"
            f"<td>{html.escape(top.get('title',''))}</td>"
            f"<td>{price_cell}</td>"
            f"<td>{code_cell}</td>"
            f"<td>{html.escape(top.get('status',''))}</td>"
            f"<td><a href=\"{html.escape(top.get('_affiliate') or top.get('offer_url',''))}\">Go</a></td></tr>"
        )
        compare_list.append(
            {
                "@type": "ListItem",
                "position": pos,
                "url": abs_url(domain, provider_href),
                "name": name,
            }
        )
    compare_path = page_path("compare")
    compare_ld = {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": compare_list}
    compare_html = render_tpl(
        "compare.html",
        {
            **base_vars,
            "title": f"Compare meal kit promos — {brand} ({month})",
            "description": f"Side-by-side public promo listings across {len(by_provider)} meal kit brands.",
            "canonical": abs_url(domain, compare_path),
            "og_title": f"Compare meal kit deals — {month}",
            "rows": "\n".join(compare_rows) or "<tr><td colspan=\"6\">No public promo offers extracted yet.</td></tr>",
            "json_ld": json.dumps(compare_ld, ensure_ascii=False),
        },
    )
    write_page(compare_path, compare_html)

    # Provider + deal pages — always emit a provider page for each config brand
    sitemap_urls: list[tuple[str, str]] = [("/", generated)]

    for name in provider_order:
        rows = by_provider.get(name, [])
        pslug = slugify(name)
        provider_path = page_path("providers", pslug)
        deal_links = []
        offer_nodes = []
        prices = []
        for o in rows:
            did = o["_id"]
            deal_path = page_path("deals", did)
            code_pill = f" code:{html.escape(str(o['code']))}" if o.get("code") else ""
            deal_links.append(
                f"<li><a href=\"{deal_path}\">{html.escape(o.get('title',''))}</a>"
                f" <span class=\"pill\">{html.escape(o.get('status',''))}{code_pill}</span></li>"
            )
            page_url = abs_url(domain, deal_path)
            offer_nodes.append(json_ld_offer(o, page_url))
            if o.get("price"):
                try:
                    prices.append(float(str(o["price"]).replace(",", "")))
                except ValueError:
                    pass

            breadcrumbs = {
                "@context": "https://schema.org",
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": abs_url(domain, "/")},
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": name,
                        "item": abs_url(domain, provider_path),
                    },
                    {"@type": "ListItem", "position": 3, "name": o.get("title"), "item": page_url},
                ],
            }
            ld_graph = [json_ld_offer(o, page_url), breadcrumbs]
            price_html = ""
            if o.get("price"):
                price_html = f"<p class=\"price\">{html.escape(o.get('currency','USD'))} {html.escape(str(o['price']))}</p>"
            if o.get("code"):
                price_html += f"<p class=\"meta\">Promo code: <strong>{html.escape(str(o['code']))}</strong></p>"
            valid_html = f"<p class=\"meta\">Valid until {html.escape(o['valid_until'])}</p>" if o.get("valid_until") else ""
            deal_html = render_tpl(
                "deal.html",
                {
                    **base_vars,
                    "title": f"{o.get('title')} — {name} | {brand}",
                    "description": (o.get("snippet") or o.get("title") or "")[:160],
                    "canonical": page_url,
                    "og_title": html.escape(str(o.get("title"))),
                    "provider": html.escape(name),
                    "provider_link": provider_path,
                    "deal_title": html.escape(str(o.get("title"))),
                    "snippet": html.escape(o.get("snippet") or ""),
                    "price_html": price_html,
                    "valid_html": valid_html,
                    "cta_url": html.escape(o.get("_affiliate") or o.get("offer_url") or "#"),
                    "source_url": html.escape(o.get("source_url") or ""),
                    "fetched_at": html.escape(str(o.get("fetched_at") or "")),
                    "json_ld": json.dumps(ld_graph, ensure_ascii=False),
                    "status": html.escape(str(o.get("status") or "")),
                },
            )
            write_page(deal_path, deal_html)
            sitemap_urls.append((deal_path, o.get("fetched_at") or generated))

        product_ld: dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "Service",
            "name": f"{name} meal kit promotions",
            "provider": {"@type": "Organization", "name": name},
            "url": abs_url(domain, provider_path),
        }
        if prices:
            product_ld["offers"] = {
                "@type": "AggregateOffer",
                "lowPrice": str(min(prices)),
                "highPrice": str(max(prices)),
                "priceCurrency": "USD",
                "offerCount": str(len(prices)),
            }
        elif offer_nodes:
            cleaned = []
            for n in offer_nodes[:20]:
                cleaned.append(n)
            product_ld["offers"] = cleaned

        faq_ld = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": f"Where do {name} promo details come from?",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": f"From the public official {name} pages listed in .ilang/site.ilang. Prices/codes are only shown when extracted; we never invent them.",
                    },
                },
                {
                    "@type": "Question",
                    "name": f"How often is {name} updated?",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": "The public GitHub Actions pipeline refreshes about every 6 hours.",
                    },
                },
            ],
        }

        deal_list_html = (
            "\n".join(deal_links)
            if deal_links
            else (
                "<p><strong>No public promo offer extracted yet.</strong> "
                "We do not invent titles, prices, or codes. "
                f"Check the <a href=\"{html.escape(affiliates.get(name, '#'))}\">official {html.escape(name)} site</a> "
                "for live promotions.</p>"
            )
        )

        provider_html = render_tpl(
            "provider.html",
            {
                **base_vars,
                "title": f"{name} promo codes & deals — {brand} ({month})",
                "description": f"Public {name} meal kit promo listings for {month}. Source: official pages.",
                "canonical": abs_url(domain, provider_path),
                "og_title": f"{name} deals — {month}",
                "provider": html.escape(name),
                "deal_list": deal_list_html,
                "json_ld": json.dumps([product_ld, faq_ld], ensure_ascii=False),
                "official": html.escape(affiliates.get(name, rows[0].get("source_url", "#") if rows else "#")),
            },
        )
        write_page(provider_path, provider_html)
        sitemap_urls.append((provider_path, generated))

    sitemap_urls.append((compare_path, generated))

    # Legal / trust pages for affiliate review
    static_pages = build_static_pages(brand, domain, affiliate_note, base_vars, cfg)
    for path, _html in static_pages:
        sitemap_urls.append((path, generated))

    # 404 page (Cloudflare Pages serves this for missing paths)
    (SITE_DIR / "404.html").write_text(
        (TPL_DIR / "404.html").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    # sitemap + robots
    sm = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for path, lastmod in sitemap_urls:
        lm = str(lastmod)[:10]
        sm.append("  <url>")
        sm.append(f"    <loc>{html.escape(abs_url(domain, path))}</loc>")
        sm.append(f"    <lastmod>{html.escape(lm)}</lastmod>")
        sm.append("  </url>")
    sm.append("</urlset>")
    (SITE_DIR / "sitemap.xml").write_text("\n".join(sm) + "\n", encoding="utf-8")
    (SITE_DIR / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {abs_url(domain, '/sitemap.xml')}\n",
        encoding="utf-8",
    )

    print(f"Built {len(offers)} offers across {len(by_provider)} providers -> {SITE_DIR}")


if __name__ == "__main__":
    render()
