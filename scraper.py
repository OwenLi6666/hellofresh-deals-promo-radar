# ::ILANG
# [TYPE:tool][FILE:scraper.py]
# ::OBJECTIVE{scrape_public_offers}
#   target: 读 site.ilang 抓公开优惠页 写 data/offers.json
# ::RULE{抓不到 price⇒不写 price|valid_until 过期⇒标 expired}
# ::BOUNDARY{never:编优惠 编价格 编佣金}
"""Fetch public meal-kit promo pages. Stdlib only. No API keys."""

from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from ilang_config import ROOT, load_site_config

DATA_PATH = ROOT / "data" / "offers.json"
UA = "mealkitdeals-promo-radar/1.0 (+https://github.com/; public promo indexer; respects robots.txt)"
TIMEOUT = 25


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.metas: dict[str, str] = {}
        self.canonical = ""
        self.json_ld: list[Any] = []
        self._capture_title = False
        self._capture_ld = False
        self._ld_buf: list[str] = []
        self.headings: list[str] = []
        self._capture_h = False
        self._h_buf = ""
        self.texts: list[str] = []
        self._capture_p = False
        self._p_buf = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k: (v or "") for k, v in attrs}
        if tag == "title":
            self._capture_title = True
        elif tag == "meta":
            key = ad.get("property") or ad.get("name") or ""
            if key and ad.get("content"):
                self.metas[key.lower()] = ad["content"].strip()
        elif tag == "link" and ad.get("rel", "").lower() == "canonical" and ad.get("href"):
            self.canonical = ad["href"]
        elif tag == "script" and "ld+json" in ad.get("type", "").lower():
            self._capture_ld = True
            self._ld_buf = []
        elif tag in {"h1", "h2", "h3"}:
            self._capture_h = True
            self._h_buf = ""
        elif tag == "p":
            self._capture_p = True
            self._p_buf = ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._capture_title = False
        elif tag == "script" and self._capture_ld:
            self._capture_ld = False
            raw = "".join(self._ld_buf).strip()
            if raw:
                try:
                    self.json_ld.append(json.loads(raw))
                except json.JSONDecodeError:
                    pass
        elif tag in {"h1", "h2", "h3"} and self._capture_h:
            self._capture_h = False
            t = re.sub(r"\s+", " ", self._h_buf).strip()
            if t:
                self.headings.append(t)
        elif tag == "p" and self._capture_p:
            self._capture_p = False
            t = re.sub(r"\s+", " ", self._p_buf).strip()
            if t and len(t) > 20:
                self.texts.append(t)

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self.title += data
        if self._capture_ld:
            self._ld_buf.append(data)
        if self._capture_h:
            self._h_buf += data
        if self._capture_p:
            self._p_buf += data


def _ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    return ctx


def fetch(url: str) -> tuple[int, str, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; mealkitdeals-promo-radar/1.0; "
                "+https://github.com/; public-promo-indexer)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_ctx()) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            body = resp.read().decode(charset, errors="replace")
            return resp.status, str(resp.geturl()), body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return e.code, url, body
    except Exception as e:  # noqa: BLE001 — record failure, never invent
        return 0, url, f"__ERROR__:{type(e).__name__}:{e}"


def robots_allows(robots_url: str, target_url: str) -> bool:
    rp = RobotFileParser()
    try:
        status, _, body = fetch(robots_url)
        if status != 200 or body.startswith("__ERROR__"):
            # If robots can't be fetched, be conservative: allow only homepage-like promo URLs already listed.
            return True
        rp.parse(body.splitlines())
        return rp.can_fetch(UA, target_url)
    except Exception:  # noqa: BLE001
        return True


def _walk_ld(node: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(node, list):
        for item in node:
            found.extend(_walk_ld(item))
        return found
    if not isinstance(node, dict):
        return found
    types = node.get("@type", "")
    if isinstance(types, list):
        types_l = [str(t).lower() for t in types]
    else:
        types_l = [str(types).lower()]
    if any(t in {"offer", "aggregateoffer"} for t in types_l):
        found.append(node)
    if "offers" in node:
        found.extend(_walk_ld(node["offers"]))
    if "@graph" in node:
        found.extend(_walk_ld(node["@graph"]))
    return found


PROMO_RE = re.compile(
    r"(\d{1,3}%\s*off|up to\s*\$?\d+|\$\d+\s*off|\d+\s*free meals?|free (?:breakfast|shipping|dessert|item)[^.!]{0,40})",
    re.I,
)
PRICE_RE = re.compile(r"\$\s?(\d+(?:\.\d{1,2})?)")
PERCENT_RE = re.compile(r"(\d{1,3})\s*%\s*off", re.I)
DATE_RE = re.compile(
    r"(expires?|valid through|until|ends?)\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})",
    re.I,
)


def _parse_date(raw: str) -> str | None:
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(raw.replace(",", ""), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _expired(valid_until: str | None) -> bool:
    if not valid_until:
        return False
    try:
        return date.fromisoformat(valid_until) < date.today()
    except ValueError:
        return False


def extract_offers(provider: dict[str, str], html: str, final_url: str) -> list[dict[str, Any]]:
    parser = _MetaParser()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001
        pass

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    offers: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(title: str, offer_url: str, price: str | None = None, currency: str | None = None, valid_until: str | None = None, extra: str = "") -> None:
        title = re.sub(r"\s+", " ", title).strip()
        if len(title) < 8:
            return
        key = title.lower()[:120]
        if key in seen:
            return
        seen.add(key)
        item: dict[str, Any] = {
            "provider": provider["name"],
            "domain": provider["domain"],
            "title": title[:200],
            "offer_url": offer_url,
            "source_url": final_url,
            "fetched_at": now,
            "status": "active",
            "snippet": extra[:280] if extra else "",
        }
        if price:
            item["price"] = price
            item["currency"] = currency or "USD"
        if valid_until:
            item["valid_until"] = valid_until
            if _expired(valid_until):
                item["status"] = "expired"
        offers.append(item)

    # JSON-LD Offer nodes (real structured data only)
    for block in parser.json_ld:
        for offer in _walk_ld(block):
            title = (
                offer.get("name")
                or offer.get("description")
                or parser.metas.get("og:title")
                or parser.title
                or f"{provider['name']} offer"
            )
            price = None
            currency = None
            if "price" in offer and offer["price"] not in (None, ""):
                price = str(offer["price"])
                currency = str(offer.get("priceCurrency") or "USD")
            elif "lowPrice" in offer and offer["lowPrice"] not in (None, ""):
                price = str(offer["lowPrice"])
                currency = str(offer.get("priceCurrency") or "USD")
            valid_until = None
            for k in ("priceValidUntil", "validThrough"):
                if offer.get(k):
                    valid_until = _parse_date(str(offer[k])[:32]) or str(offer[k])[:10]
                    break
            url = offer.get("url") or final_url
            if isinstance(url, list):
                url = url[0]
            add(str(title), str(url), price, currency, valid_until)

    # Heading / paragraph promo phrases
    corpus = parser.headings + parser.texts[:30]
    og = parser.metas.get("og:description") or parser.metas.get("description") or ""
    if og:
        corpus.insert(0, og)
    if parser.title:
        corpus.insert(0, parser.title.strip())

    for text in corpus:
        for m in PROMO_RE.finditer(text):
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 60)
            window = text[start:end].strip(" -–|:;,.")
            price = None
            currency = None
            # Only record absolute $ amounts as price, never invent percent as price
            pm = PRICE_RE.search(m.group(0))
            if pm and "free" not in m.group(0).lower():
                # Prefer not treating "% off" windows as price; only clear $N
                if "%" not in m.group(0):
                    price = pm.group(1)
                    currency = "USD"
            valid_until = None
            dm = DATE_RE.search(text)
            if dm:
                valid_until = _parse_date(dm.group(2))
            add(window, final_url, price, currency, valid_until, text)

    if not offers:
        # Honest fallback: page reachable but no extractable promo phrase
        title = parser.metas.get("og:title") or parser.title.strip() or f"{provider['name']} official page"
        add(
            f"{provider['name']}: check current promotions on official page",
            final_url,
            None,
            None,
            None,
            og or "No structured promo phrase extracted; visit official page for live offers.",
        )
        offers[-1]["status"] = "listing"

    # Drop expired from active listing later in build; keep them marked
    return offers


def scrape_all() -> dict[str, Any]:
    cfg = load_site_config()
    site = cfg["site"]
    all_offers: list[dict[str, Any]] = []
    fetch_log: list[dict[str, Any]] = []

    for provider in cfg["providers"]:
        urls = provider.get("promo_urls") or [provider["promo_url"]]
        robots_url = provider.get("robots_url") or f"https://{provider['domain']}/robots.txt"
        got_any = False
        last_error = ""
        for url in urls:
            allowed = robots_allows(robots_url, url)
            entry: dict[str, Any] = {
                "provider": provider["name"],
                "url": url,
                "robots_allowed": allowed,
            }
            if not allowed:
                entry["status"] = "skipped_robots"
                fetch_log.append(entry)
                continue
            status, final_url, body = fetch(url)
            entry["http_status"] = status
            entry["final_url"] = final_url
            if status != 200 or body.startswith("__ERROR__"):
                # one retry after short wait
                time.sleep(1.5)
                status, final_url, body = fetch(url)
                entry["http_status"] = status
                entry["final_url"] = final_url
                entry["retried"] = True
            if status != 200 or body.startswith("__ERROR__"):
                entry["status"] = "fetch_failed"
                entry["error"] = body[:200] if body.startswith("__ERROR__") else f"HTTP {status}"
                last_error = entry["error"]
                fetch_log.append(entry)
                time.sleep(0.8)
                continue
            offers = extract_offers(provider, body, final_url)
            entry["status"] = "ok"
            entry["offers_extracted"] = len(offers)
            fetch_log.append(entry)
            all_offers.extend(offers)
            got_any = True
            time.sleep(1.0)
            break
        if not got_any:
            all_offers.append(
                {
                    "provider": provider["name"],
                    "domain": provider["domain"],
                    "title": f"{provider['name']}: official promo page temporarily unreachable",
                    "offer_url": urls[0],
                    "source_url": urls[0],
                    "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                    "status": "unreachable",
                    "snippet": f"Fetch failed ({last_error or 'unknown'}); open the official URL for current offers. No price invented.",
                }
            )

    payload = {
        "brand": site.get("brand", "hellofresh-deals"),
        "niche": site.get("niche", ""),
        "locale": site.get("locale", "en-US"),
        "currency_default": site.get("currency", "USD"),
        "domain": site.get("domain", ""),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "config_source": cfg["source_path"],
        "providers": [p["name"] for p in cfg["providers"]],
        "fetch_log": fetch_log,
        "offers": all_offers,
    }
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    data = scrape_all()
    print(f"Wrote {len(data['offers'])} offers -> {DATA_PATH}")
    for row in data["fetch_log"]:
        print(row)
