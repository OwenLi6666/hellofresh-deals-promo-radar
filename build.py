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
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from string import Template
from typing import Any

from ilang_config import ROOT, load_site_config

sys.path.insert(0, str(ROOT / "tools"))
from offer_quality import offer_passes_quality  # noqa: E402

from scraper import (
    VALID_UNTIL_NOT_STATED,
    _clean_title,
    _intro_is_brand_copy,
    _is_unit_price_not_promo,
    _looks_like_real_promo,
    _prefer_audience_headline,
    _validate_code,
    clean_conditions,
)

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


def sitemap_lastmod(value: str | None, fallback: str) -> str:
    """Normalize a build/scrape timestamp for sitemap lastmod (W3C datetime)."""
    raw = str(value or fallback or "").strip()
    if not raw:
        return fallback[:10]
    if "T" in raw:
        normalized = raw.replace("Z", "+00:00")
        if "+" not in normalized:
            normalized = normalized[:19] + "+00:00"
        return normalized[:25]
    return raw[:10]


def latest_offer_timestamp(rows: list[dict[str, Any]], fallback: str) -> str:
    stamps = [str(o.get("fetched_at") or "").strip() for o in rows if o.get("fetched_at")]
    return max(stamps, default=fallback)


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


def sanitize_offer(offer: dict[str, Any]) -> None:
    """Display-time cleanup: readable titles, no fake codes. Mutates offer in place."""
    raw_title = (offer.get("title") or "").strip()
    snippet = offer.get("snippet") or ""
    conditions = offer.get("conditions") or ""
    headline = _prefer_audience_headline(raw_title, snippet, conditions)
    title = _clean_title(headline)
    # Title cleanup must not erase a valid official extract — keep raw if clean stripped too much.
    if len(title) < 10 and len(headline) >= 10:
        title = headline
    offer["title"] = title
    if offer.get("snippet"):
        sn = _clean_title(offer.get("snippet") or "")
        if sn.lower() == title.lower() or title.lower() in sn.lower():
            offer["snippet"] = ""
        else:
            offer["snippet"] = sn
    code = _validate_code(offer.get("code"), title, offer.get("snippet") or "")
    if code:
        offer["code"] = code
        offer["code_required"] = "yes"
    else:
        offer.pop("code", None)
        if (offer.get("code_required") or "").lower() == "yes":
            offer.pop("code_required", None)
    note = (offer.get("valid_until_note") or "").strip()
    if note == "官方页未标":
        offer["valid_until_note"] = VALID_UNTIL_NOT_STATED


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
    title = (offer.get("title") or "").strip()
    if _is_unit_price_not_promo(title, offer.get("price")):
        return False
    if not offer_passes_quality(offer):
        return False
    if offer.get("visible_verified") is False:
        return False
    if _looks_like_real_promo(title, offer.get("price"), offer.get("code")):
        return True
    # Benefit is a fallback headline only when title cleanup left nothing usable.
    benefit = (offer.get("benefit") or "").strip()
    if not title and benefit and _looks_like_real_promo(benefit, offer.get("price"), offer.get("code")):
        return True
    return False


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


def offer_valid_display(offer: dict[str, Any]) -> str:
    if offer.get("valid_until"):
        return str(offer["valid_until"])
    note = (offer.get("valid_until_note") or "").strip()
    if note == "官方页未标":
        note = VALID_UNTIL_NOT_STATED
    return note or VALID_UNTIL_NOT_STATED


def offer_code_required_html(offer: dict[str, Any]) -> str:
    code = offer.get("code")
    req = (offer.get("code_required") or "").strip().lower()
    if code:
        return f"yes — <strong>{html.escape(str(code))}</strong>"
    if req == "yes":
        return "yes"
    if req == "no":
        return "no"
    return ""


def provider_about_html(name: str, profiles: dict[str, Any]) -> str:
    prof = profiles.get(name) or {}
    intro = (prof.get("intro") or "").strip()
    src = (prof.get("intro_source_url") or "").strip()
    if not intro or not _intro_is_brand_copy(intro, src):
        return ""
    src_html = ""
    if src:
        src_html = (
            f'<p class="meta">Source: <a href="{html.escape(src)}" rel="nofollow noopener">'
            f"{html.escape(src)}</a></p>"
        )
    return (
        f'<section class="panel about-brand">'
        f"<h2>About {html.escape(name)}</h2>"
        f"<p>{html.escape(intro)}</p>"
        f"{src_html}"
        f"</section>"
    )


def provider_sources_html(rows: list[dict[str, Any]]) -> str:
    items: list[str] = []
    seen: set[str] = set()
    for o in rows:
        src = (o.get("source_url") or o.get("offer_url") or "").strip()
        if not src or src in seen:
            continue
        seen.add(src)
        items.append(
            f'<li><a href="{html.escape(src)}" rel="nofollow noopener">{html.escape(src)}</a></li>'
        )
    if not items:
        return ""
    return (
        '<section class="panel">'
        "<h2>Official source pages</h2>"
        "<ul>"
        + "".join(items)
        + "</ul></section>"
    )


def _sentence_case_fragment(fragment: str) -> str:
    fragment = fragment.strip()
    if not fragment:
        return ""
    if fragment[0].islower():
        return fragment[0].upper() + fragment[1:]
    return fragment


def _split_condition_fragments(conditions: str) -> list[str]:
    parts: list[str] = []
    for piece in re.split(r"[,;]", conditions):
        p = piece.strip()
        if p:
            parts.append(p)
    return parts


# Homepage-only: whole-line fragments that read worse than showing nothing.
_CARD_CONDITION_UNREADABLE = frozenset(
    {
        "upcoming order",
        "for life",
        "first 4 weeks",
    }
)


def _drop_unreadable_card_condition(line: str) -> str:
    if not line:
        return ""
    if line.strip().lower() in _CARD_CONDITION_UNREADABLE:
        return ""
    return line.strip()


def _format_card_conditions(kept_fragments: list[str], comma_joined: str) -> str:
    """Turn deduped fragments into a short readable line; fall back if not clearer."""
    if not kept_fragments:
        return ""
    if len(kept_fragments) == 1:
        single = kept_fragments[0]
        cased = _sentence_case_fragment(single)
        return comma_joined if cased == single and single != comma_joined else cased
    formatted = "; ".join(_sentence_case_fragment(f) for f in kept_fragments)
    if formatted.lower().replace("; ", ", ") == comma_joined.lower():
        return formatted
    return formatted


def offer_card_conditions_line(offer: dict[str, Any]) -> str:
    """Homepage card line 2: deduped, lightly formatted conditions (detail pages keep full text)."""
    title = (offer.get("title") or "").strip()
    benefit = (offer.get("benefit") or "").strip()
    raw_cleaned = clean_conditions((offer.get("conditions") or "").strip())
    tl = title.lower()
    bl = benefit.lower()

    kept: list[str] = []
    if raw_cleaned:
        for part in _split_condition_fragments(raw_cleaned):
            pl = part.lower()
            if pl in tl or (bl and pl in bl):
                continue
            if bl and len(pl) >= 6 and pl in bl:
                continue
            if tl and len(pl) >= 10 and pl in tl:
                continue
            kept.append(part)

    comma_joined = ", ".join(kept)
    conditions = _format_card_conditions(kept, comma_joined)

    code = (offer.get("code") or "").strip()
    if code and code.upper() not in title.upper():
        code_bit = f"Code {code}"
        if code_bit.lower() not in conditions.lower():
            conditions = f"{conditions}; {code_bit}" if conditions else code_bit

    return _drop_unreadable_card_condition(conditions.strip(" ;"))


def normalize_offer_title(title: str) -> str:
    """Display-time cleanup for UI crumbs; never invents new offer claims."""
    from html import unescape

    title = _clean_title(unescape(title or ""))
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
        <p><strong>{html.escape(brand)}</strong> is a meal-kit promo radar: it lists publicly visible promotions scraped from official brand pages. It does not invent offers, prices, codes, or expiry dates.</p>
        <p>To reach the publisher about listing corrections, outdated promos, privacy questions, or partnership inquiries, email:</p>
        <p><a href="mailto:{html.escape(contact_email)}">{html.escape(contact_email)}</a></p>
        <p>Please include the page URL when you report an incorrect or outdated listing. We read messages sent to this address and reply when we can; we do not promise a fixed response time.</p>
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

    contact_line = (
        '<p><strong>Contact.</strong> For privacy questions, use the email on the <a href="/contact/">Contact</a> page.</p>'
        if contact_email and "@" in contact_email
        else '<p><strong>Contact.</strong> A public contact email will be listed on this site once the publisher publishes one.</p>'
    )
    privacy_body = f"""
        <p>This Privacy Policy applies to <strong>{html.escape(brand)}</strong> at <strong>{html.escape(domain)}</strong>, a static meal-kit promo radar hosted on Cloudflare Pages.</p>
        <p><strong>What we collect.</strong> The public site itself does not run a member login and does not ask you to create an account. Standard web server / CDN logs (such as IP address, user agent, and requested URL) may be processed by Cloudflare while serving the site. We do not sell personal information.</p>
        <p><strong>Affiliate links.</strong> Some outbound links to meal-kit brands may be affiliate links. If you click them and later subscribe or purchase, we may earn a commission at no extra cost to you. Affiliate networks and brand sites have their own privacy policies.</p>
        <p><strong>Third-party advertising.</strong> The site is prepared to display third-party ads (for example display or affiliate network creatives). Ad partners may use cookies or similar technologies to measure impressions or personalize ads. When ad codes are added, those partners' policies also apply. We will not invent tracking that is not actually installed.</p>
        <p><strong>Scraped listings.</strong> Promo titles, codes, and prices shown on this site come from publicly available brand pages. We do not invent missing fields.</p>
        {contact_line}
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
    shelved = set(cfg.get("shelved") or [])
    pub = cfg.get("publisher") or {}
    has_contact = bool((pub.get("contact_email") or "").strip() and "@" in (pub.get("contact_email") or ""))

    provider_profiles: dict[str, Any] = dict(data.get("provider_profiles") or {})
    raw_offers = [dict(o) for o in data.get("offers", [])]
    for o in raw_offers:
        if o.get("provider") in shelved:
            continue
        sanitize_offer(o)
    offers = [
        o
        for o in raw_offers
        if o.get("provider") not in shelved and is_showable(o)
    ]
    # Drop duplicate cards for the same brand + benefit + code after cleanup
    seen_card: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for o in offers:
        key = (
            o.get("provider") or "",
            (o.get("benefit") or o.get("title") or "").strip().lower(),
            (o.get("code") or "").upper(),
        )
        if key in seen_card:
            continue
        seen_card.add(key)
        deduped.append(o)
    offers = deduped
    for o in offers:
        o["_id"] = offer_id(o)
        o["_affiliate"] = affiliates.get(o.get("provider", ""), o.get("offer_url", "#"))

    by_provider: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for o in offers:
        by_provider[o.get("provider", "Unknown")].append(o)

    # Prefer config provider order (skip shelved brands — data kept, pages not emitted)
    provider_order = [p["name"] for p in cfg["providers"] if p["name"] not in shelved]
    for name in by_provider:
        if name not in provider_order and name not in shelved:
            provider_order.append(name)

    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "assets").mkdir(exist_ok=True)
    clean_output_dirs()

    month = month_label()
    # Homepage "Updated" stamp = build time so deploys are externally verifiable
    built_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    generated = built_at
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
    # Cloudflare Pages cache headers (keep homepage from sticking on edge)
    headers_src = TPL_DIR / "_headers"
    if headers_src.exists():
        (SITE_DIR / "_headers").write_text(headers_src.read_text(encoding="utf-8"), encoding="utf-8")

    # Index cards — only brands with at least one showable offer (no empty promo shells).
    cards = []
    listed_providers: list[str] = []
    for name in provider_order:
        rows = by_provider.get(name, [])
        if not rows:
            continue
        listed_providers.append(name)
        top = rows[0]
        top_title = top.get("title", name)
        cond_line = offer_card_conditions_line(top)
        cond_html = (
            f'<p class="card-conditions">{html.escape(cond_line)}</p>'
            if cond_line
            else ""
        )
        provider_href = page_path("providers", slugify(name))
        cards.append(
            f"""
            <article class="card">
              <p class="eyebrow">{html.escape(name)}</p>
              <h2><a href="{provider_href}">{html.escape(top_title)}</a></h2>
              {cond_html}
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
            for i, name in enumerate(listed_providers)
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
            "provider_count": str(len(listed_providers)),
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

    # Provider + deal pages — only for brands with showable offers
    sitemap_urls: list[tuple[str, str]] = [("/", generated)]

    for name in provider_order:
        rows = by_provider.get(name, [])
        if not rows:
            continue
        pslug = slugify(name)
        provider_path = page_path("providers", pslug)
        deal_links = []
        offer_nodes = []
        prices = []
        for o in rows:
            did = o["_id"]
            deal_path = page_path("deals", did)
            code_pill = f" code:{html.escape(str(o['code']))}" if o.get("code") else ""
            detail_bits = []
            if o.get("benefit"):
                detail_bits.append(f"What you get: {html.escape(str(o['benefit']))}")
            cond_display = clean_conditions(str(o.get("conditions") or ""))
            if cond_display:
                detail_bits.append(f"Conditions: {html.escape(cond_display)}")
            cr = offer_code_required_html(o)
            if cr:
                detail_bits.append(f"Code required: {cr}")
            detail_bits.append(f"Valid until: {html.escape(offer_valid_display(o))}")
            src = o.get("source_url") or ""
            if src:
                detail_bits.append(
                    f'Source: <a href="{html.escape(src)}" rel="nofollow noopener">{html.escape(src)}</a>'
                )
            detail_html = (
                f'<p class="deal-detail">{" · ".join(detail_bits)}</p>' if detail_bits else ""
            )
            deal_links.append(
                f"<li><a href=\"{deal_path}\">{html.escape(o.get('title',''))}</a>"
                f" <span class=\"pill\">{html.escape(o.get('status',''))}{code_pill}</span>"
                f"{detail_html}</li>"
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
            benefit = (o.get("benefit") or "").strip() or (o.get("title") or "")
            conditions = clean_conditions((o.get("conditions") or "").strip())
            deal_html = render_tpl(
                "deal.html",
                {
                    **base_vars,
                    "title": f"{o.get('title')} — {name} | {brand}",
                    "description": (o.get("benefit") or o.get("snippet") or o.get("title") or "")[:160],
                    "canonical": page_url,
                    "og_title": html.escape(str(o.get("title"))),
                    "provider": html.escape(name),
                    "provider_link": provider_path,
                    "deal_title": html.escape(str(o.get("title"))),
                    "benefit": html.escape(str(benefit)),
                    "conditions": html.escape(conditions),
                    "code_required_html": offer_code_required_html(o),
                    "valid_display": html.escape(offer_valid_display(o)),
                    "price_html": price_html,
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

        prof = provider_profiles.get(name) or {}
        intro = (prof.get("intro") or "").strip()
        desc_bits = [
            f"{name} promo codes, coupons, and deals for {month}.",
            intro[:140] if intro else "Public listings scraped from official brand pages.",
        ]
        listing_count = len(rows)
        provider_html = render_tpl(
            "provider.html",
            {
                **base_vars,
                "title": f"{name} promo codes & deals — {brand} ({month})",
                "description": " ".join(desc_bits)[:300],
                "canonical": abs_url(domain, provider_path),
                "og_title": f"{name} promo codes & deals — {month}",
                "h1": html.escape(f"{name} promo codes & deals"),
                "lede": html.escape(
                    f"Public {name} promo codes, coupons, and meal kit deals from official pages "
                    f"for {month}. Every line below is extracted from brand sites — nothing invented."
                ),
                "provider": html.escape(name),
                "about_section": provider_about_html(name, provider_profiles),
                "listings_heading": html.escape(f"{name} promo codes & coupons ({listing_count})"),
                "listings_note": html.escape(
                    f"{listing_count} public offer(s) extracted from official {name} pages."
                ),
                "deal_list": deal_list_html,
                "source_section": provider_sources_html(rows),
                "json_ld": json.dumps([product_ld, faq_ld], ensure_ascii=False),
                "official": html.escape(affiliates.get(name, rows[0].get("source_url", "#") if rows else "#")),
            },
        )
        write_page(provider_path, provider_html)
        sitemap_urls.append((provider_path, latest_offer_timestamp(rows, generated)))

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
        lm = sitemap_lastmod(str(lastmod), generated)
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
    from audit_offer_quality import collect_quality_issues  # noqa: E402

    issues = collect_quality_issues()
    if issues:
        print(f"quality audit failed ({len(issues)} issue(s)):", file=sys.stderr)
        for line in issues:
            print(f"- {line}", file=sys.stderr)
        sys.exit(1)
    render()
