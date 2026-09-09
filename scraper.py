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
    r"("
    r"\d{1,3}%\s*off|"
    r"up to\s*\d{1,3}%|"
    r"\$\d+(?:\.\d{1,2})?\s*off|"
    r"\d+\s*free meals?|"
    r"free (?:breakfast|shipping|dessert|item|gift|trial|dozen)[^.!]{0,50}|"
    r"(?:use|with)\s+code\s+[A-Z][A-Z0-9]{3,19}"
    r")",
    re.I,
)
PRICE_RE = re.compile(r"\$\s?(\d+(?:\.\d{1,2})?)")
PERCENT_RE = re.compile(r"(\d{1,3})\s*%\s*off", re.I)
CODE_RE = re.compile(
    r"(?:(?:use|with|promo)\s+)?code\s*[:\s\"'\u201c\u201d\u00ab\u00bb]*([A-Z][A-Z0-9]{3,19})\b",
    re.I,
)
DATE_RE = re.compile(
    r"(expires?|valid through|until|ends?)\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})",
    re.I,
)
# Words that are not promo codes even if CODE_RE matches
CODE_STOP = {
    "HERE", "THIS", "THAT", "YOUR", "FROM", "WITH", "WHEN", "WILL", "SHOULD",
    "COULD", "WOULD", "HAVE", "BEEN", "THEY", "THEM", "FREE", "SHIP", "MEAL",
    "ENTER", "APPLIED", "SUCCESSFULLY", "REDEEM", "ORDER", "ORDERS", "FIRST",
    "BOX", "BOXES", "WEEK", "WEEKS", "LIFE", "SHIPPING", "OFFER", "PROMO",
    "DISCOUNT", "COUPON", "CODES", "PAGE", "HOME", "MENU", "PLAN", "PLANS",
    "SAVE", "SAVING", "GET", "NOW", "TODAY", "MORE", "LESS", "THAN", "THEN",
    "ALSO", "ONLY", "JUST", "NEXT", "LAST", "BEST", "DEAL", "SALE", "LIMITED",
    "TIME", "ITEM", "ITEMS", "GIFT", "TRIAL", "BREAKFAST", "DESSERT", "DOZEN",
    "REQUIRED", "OPTIONAL", "ZIP", "POSTAL",
    "GIVE", "GIVES", "TAKE", "TAKES", "MAKE", "MAKES", "COME", "COMES",
}


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


def _extract_code(text: str) -> str | None:
    for m in CODE_RE.finditer(text):
        code = (m.group(1) or "").upper()
        if not code or code in CODE_STOP or code.isdigit():
            continue
        if len(code) < 4 or len(code) > 16:
            continue
        if code.isalpha() and code.lower() in {
            "successfully", "required", "optional", "shipping", "breakfast",
            "discount", "limited", "current", "official", "subscription",
        }:
            continue
        return code
    return None


def _clean_title(title: str) -> str:
    from html import unescape

    title = unescape(title)
    title = re.sub(r"\s+", " ", title).strip(" -–|:;,.")
    title = re.sub(r"^[^A-Za-z0-9$]+", "", title)
    title = re.sub(r"^(?:and|or|the|a|an|of|to|for|on|in|with|your|our|so|now|shop now)\s+", "", title, flags=re.I)
    # Restore "$N" when a dollar amount was clipped at window start
    if re.match(r"^\d{2,3}\s+on\s+your\s+first", title, re.I):
        title = "$" + title
    # Normalize "use code X …" into a readable offer title
    um = re.match(
        r"(?i)use\s+code\s+([A-Z0-9]{3,19})\s+(?:on\s+)?(?:an\s+)?upcoming\s+order\s+for\s+(.+)$",
        title,
    )
    if um:
        title = f"{um.group(2).strip().rstrip('.*')} (code {um.group(1).upper()})"
        if title and title[0].islower():
            title = title[0].upper() + title[1:]
    # Prefer short canonical percent headlines when present
    short = re.search(r"(?i)\b((?:up to\s+)?\d{1,3}%\s*off)\b", title)
    if short and len(title) > 50 and "code" not in title.lower():
        # Keep longer title if it adds first-order / free item context
        if not re.search(r"(?i)first (?:order|week|box)|free (?:item|gift|shipping|meals?)", title):
            title = short.group(1)
            if title.islower() or title[0].islower():
                title = title[0].upper() + title[1:]
    # If nav chrome precedes the promo phrase, keep from the promo phrase onward
    m = PROMO_RE.search(title)
    if m and m.start() > 40:
        # rewind to nearest sentence/capital start before promo
        cut = title.rfind(". ", 0, m.start())
        if cut == -1:
            cut = max(0, m.start() - 30)
            while cut < m.start() and not (title[cut].isupper() or title[cut].isdigit()):
                cut += 1
        else:
            cut = cut + 2
        title = title[cut:].strip()
    if title and title[0].islower() and not title.startswith("use "):
        # Capitalize leading letter for display only when we already validated promo
        pass
    return title.strip()


def _looks_like_real_promo(title: str, price: str | None, code: str | None) -> bool:
    """Reject marketing fluff / fallback copy pretending to be an offer."""
    t = title.lower().strip()
    if len(t) < 10:
        return False
    if "check current promotions" in t:
        return False
    if "temporarily unreachable" in t:
        return False
    if "no structured promo" in t:
        return False
    # Reject legalese / mid-sentence fragments (allow "use code …" and digit-led "% off")
    if title and title[0].islower() and not re.match(r"(?i)use\s+code\b", title):
        if not code:
            return False
    if t.startswith(("of ", "er ", "se ", "nt ", "life'", "life’")):
        return False
    if re.search(r"will receive (more|less) than|based on (a limit|total discount)|if subscription", t):
        return False
    if "how to redeem" in t and not code:
        return False
    # Reject windows that are mostly form chrome
    if "zip code" in t and "off" not in t and "free" not in t:
        return False
    # Reject truncated crumb titles
    if t.endswith(" reg") or t in {"18 free meals", "45% off reg", "30% off reg"}:
        return False
    if re.search(r"\bwho you are\b", t):
        # Keep only if short specialty discount headline
        if len(t) > 60:
            return False
    # Reject nav / footer chrome mistaken for offers
    if re.search(
        r"gift shop|affiliate\s*&|discover our story|search shop all|shop all clear|"
        r"more info faqs|sustainability ter|glp-1 support get",
        t,
    ):
        return False
    if len(t) > 90 and t.count(" ") > 14 and not code:
        # Long nav dump without a code is almost never a clean offer title
        if re.search(r"\b(blog|shop all|gift|affiliate|support|faq)\b", t):
            return False
    has_promo = bool(PROMO_RE.search(title))
    strong = bool(
        PERCENT_RE.search(title)
        or re.search(r"\$\d+\s*off", title, re.I)
        or re.search(r"\d+\s*free meals?", title, re.I)
        or re.search(r"free (?:breakfast|item|gift|dozen|trial)", title, re.I)
        or code
        or price
    )
    # "$65 with code" / "Save $65" without literal "off" still counts via code+save
    if code and re.search(r"\$\d+|save\s+\$?\d+", title, re.I):
        strong = True
    if not strong:
        return False
    if code and has_promo:
        return True
    if code and re.search(r"off|free|discount|save|\$\d+", t):
        return True
    if price and has_promo:
        return True
    # Use original title casing — lowercased `t` always starts lowercase
    if has_promo and title and (not title[0].islower() or title[0].isdigit()):
        return True
    if has_promo and re.match(r"(?i)use\s+code\b", title):
        return True
    return False


def _score_offer(title: str, price: str | None, code: str | None) -> int:
    score = 0
    if code:
        score += 40
    if price:
        score += 15
    if PERCENT_RE.search(title):
        score += 25
    if re.search(r"\$\d+\s*off", title, re.I):
        score += 25
    if re.search(r"\d+\s*free meals?", title, re.I):
        score += 25
    if re.search(r"free (?:breakfast|shipping|item|gift|dozen)", title, re.I):
        score += 15
    if re.fullmatch(r"(?i)(?:get\s+)?(?:up to\s+)?\d{1,3}%\s*off!?", title.strip()):
        score += 20
    # Prefer concise titles
    if 20 <= len(title) <= 120:
        score += 10
    if len(title) > 160:
        score -= 10
    if title and title[0].islower():
        score -= 20
    return score


def extract_offers(provider: dict[str, str], html: str, final_url: str) -> list[dict[str, Any]]:
    parser = _MetaParser()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001
        pass

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(
        title: str,
        offer_url: str,
        price: str | None = None,
        currency: str | None = None,
        valid_until: str | None = None,
        extra: str = "",
        code: str | None = None,
    ) -> None:
        title = _clean_title(title)
        if len(title) < 10:
            return
        if code:
            code = code.upper()
            if code in CODE_STOP:
                code = None
        if not _looks_like_real_promo(title, price, code):
            return
        # Dedupe by code + core promo token when possible
        promo_token = ""
        pm = PERCENT_RE.search(title) or re.search(r"\$\d+\s*off|\d+\s*free meals?", title, re.I)
        if pm:
            promo_token = pm.group(0).lower()
        key = f"{(code or '').lower()}|{promo_token}|{title.lower()[:80]}"
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
            "snippet": _clean_title(extra)[:280] if extra else "",
            "_score": _score_offer(title, price, code),
        }
        if price:
            item["price"] = price
            item["currency"] = currency or "USD"
        if code:
            item["code"] = code
            if code.upper() not in title.upper():
                item["title"] = f"{item['title']} (code {code})"[:200]
        if valid_until:
            item["valid_until"] = valid_until
            if _expired(valid_until):
                item["status"] = "expired"
        candidates.append(item)

    # JSON-LD Offer nodes (real structured data only)
    for block in parser.json_ld:
        for offer in _walk_ld(block):
            title = (
                offer.get("name")
                or offer.get("description")
                or parser.metas.get("og:title")
                or parser.title
                or ""
            )
            if not title:
                continue
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
            code = _extract_code(str(title))
            add(str(title), str(url), price, currency, valid_until, code=code)

    # Prefer title / headings / short paragraphs before noisy body windows
    corpus: list[str] = []
    if parser.title:
        corpus.append(parser.title.strip())
    og = parser.metas.get("og:description") or parser.metas.get("description") or ""
    if og:
        corpus.append(og)
    corpus.extend(parser.headings)
    corpus.extend(parser.texts[:30])

    # Promo+code pairs often live in JSON/script blobs that tag parsers miss
    for m in re.finditer(
        r"(?i)((?:get\s+)?\$\d+(?:\.\d{1,2})?\s*off[^<\"\\]{0,100}(?:with\s+|use\s+)?code\s+[A-Z0-9]{4,20}"
        r"|(?:use\s+|with\s+)?code\s+[A-Z0-9]{4,20}[^<\"\\]{0,80}(?:free\s+(?:dozen|shipping|meals?|item|gift)|\$\d+\s*off|\d+%\s*off))",
        html,
    ):
        chunk = re.sub(r"[\\\"]+", " ", m.group(0))
        chunk = re.sub(r"\s+", " ", chunk).strip()
        if chunk:
            corpus.append(chunk)

    # Strip scripts/styles then scan for promo sentences (not random 80-char windows)
    stripped = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    stripped = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", stripped)
    stripped = re.sub(r"(?s)<[^>]+>", " ", stripped)
    stripped = re.sub(r"\s+", " ", stripped)
    for chunk in re.findall(
        r"[^.!?]{0,120}(?:\d{1,3}%\s*off|\$\d+\s*off|\d+\s*free meals?|free breakfast|free shipping|use code\s+[A-Z0-9]{4,}|with code\s+[A-Z0-9]{4,})[^.!?]{0,120}",
        stripped[:150000],
        flags=re.I,
    ):
        corpus.append(chunk.strip())

    for text in corpus:
        code_in_text = _extract_code(text)
        for m in PROMO_RE.finditer(text):
            # Prefer a sentence-ish window around the match
            start = max(0, m.start() - 50)
            end = min(len(text), m.end() + 80)
            window = text[start:end]
            # If a full short sentence exists in text, prefer it
            for sent in re.split(r"[.!?\n]", text):
                if m.group(0).lower() in sent.lower() and 15 <= len(sent.strip()) <= 180:
                    window = sent
                    break
            window = window.strip(" -–|:;,.")
            price = None
            currency = None
            # Never treat "$N off" discount amounts as a product price
            matched = m.group(0)
            if not re.search(r"off|%|free", matched, re.I):
                pm = PRICE_RE.search(matched)
                if pm:
                    price = pm.group(1)
                    currency = "USD"
            valid_until = None
            dm = DATE_RE.search(text)
            if dm:
                valid_until = _parse_date(dm.group(2))
            code = code_in_text or _extract_code(window)
            add(window, final_url, price, currency, valid_until, text, code=code)

        # Standalone promo-code mentions with nearby discount language
        if code_in_text and not PROMO_RE.search(text):
            if re.search(r"off|discount|save|free|promo", text, re.I):
                add(text[:180], final_url, None, None, None, text, code=code_in_text)

    # Keep best few offers only — no fluff padding
    candidates.sort(key=lambda o: int(o.get("_score") or 0), reverse=True)
    offers: list[dict[str, Any]] = []
    kept_codes: set[str] = set()
    kept_tokens: set[str] = set()
    for item in candidates:
        score = int(item.pop("_score", 0) or 0)
        code = (item.get("code") or "").upper()
        title = item.get("title") or ""
        token_m = PERCENT_RE.search(title) or re.search(r"\$\d+\s*off|\d+\s*free meals?", title, re.I)
        token = (token_m.group(0).lower() if token_m else title.lower()[:40])
        if code and code in kept_codes:
            continue
        if not code and token in kept_tokens:
            continue
        # Drop low-quality leftovers once we already have solid offers
        if offers and score < 20:
            continue
        if re.search(r"^\d+-?\d*\s*free meals?\)?$", title, re.I):
            continue
        if code:
            kept_codes.add(code)
        kept_tokens.add(token)
        offers.append(item)
        if len(offers) >= 3:
            break
    return offers


def scrape_all() -> dict[str, Any]:
    cfg = load_site_config()
    site = cfg["site"]
    all_offers: list[dict[str, Any]] = []
    fetch_log: list[dict[str, Any]] = []

    for provider in cfg["providers"]:
        urls = provider.get("promo_urls") or [provider["promo_url"]]
        robots_url = provider.get("robots_url") or f"https://{provider['domain']}/robots.txt"
        got_page = False
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
            entry["status"] = "ok" if offers else "ok_no_promo"
            entry["offers_extracted"] = len(offers)
            fetch_log.append(entry)
            all_offers.extend(offers)
            got_page = True
            time.sleep(1.0)
            # Keep trying next URL if this page had zero real promos
            if offers:
                break
        if not got_page:
            # Record failure in log only — do not invent a fake offer row.
            fetch_log.append(
                {
                    "provider": provider["name"],
                    "url": urls[0],
                    "status": "all_urls_failed",
                    "error": last_error or "unknown",
                }
            )

    payload = {
        "brand": site.get("brand", "mealkitdeals"),
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
