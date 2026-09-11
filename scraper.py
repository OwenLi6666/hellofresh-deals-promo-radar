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
    r"\$\d+(?:\.\d{1,2})?\s*/\s*meals?|"
    r"\d+\s*free meals?|"
    r"free (?:breakfast|lunch|shipping|dessert|item|gift|dozen|protein|steaks?|ribeyes?|meal prep|favorites|welcome)[^.!]{0,80}|"
    r"free (?:\d+[-\s]?day\s+)?trial|"
    r"\$[\d,]+(?:\.\d{1,2})?\s*(?:worth|value)[^.!]{0,40}(?:for\s+free|free)?|"
    r"(?:use|with)\s+code\s+[A-Z][A-Z0-9]{3,19}"
    r")",
    re.I,
)
PRICE_RE = re.compile(r"\$\s?(\d+(?:\.\d{1,2})?)")
PERCENT_RE = re.compile(r"(\d{1,3})\s*%\s*off", re.I)
CODE_RE = re.compile(
    r"(?:(?:use|with|promo)\s+)?code\s*[^\w\r\n]{0,4}([A-Z][A-Z0-9]{3,19})\b",
    re.I,
)
DATE_RE = re.compile(
    r"(expires?|valid through|until|ends?|offer ends|good through|limited time until|"
    r"ordered before|redeemed by|before)\s*"
    r"(?:\d{1,2}:\d{2}\s*(?:AM|PM)\s*ET\s+on\s+)?"
    r":?\s*"
    r"([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})",
    re.I,
)
BENEFIT_RE = re.compile(
    r"(?i)("
    r"(?:up to\s+)?\d{1,3}%\s*off|"
    r"\$\d+(?:\.\d{1,2})?\s*off|"
    r"\$\d+(?:\.\d{1,2})?\s*/\s*meals?|"
    r"save\s+\$\d+(?:\.\d{1,2})?(?:\s+off)?|"
    r"\d+\s*free meals?(?:\s*\+\s*free shipping)?|"
    r"free breakfast(?: for (?:life|1 year|one year))?|"
    r"free lunch(?: for a month)?|"
    r"free (?:protein|steaks?|ribeyes?|favorites)[^.!?]{0,80}|"
    r"free meal prep[^.!?]{0,60}|"
    r"free (?:\d+[-\s]?day\s+)?trial|"
    r"\$[\d,]+(?:\.\d{1,2})?\s*(?:worth|value)[^.!?]{0,40}(?:for\s+free)?|"
    r"free shipping|"
    r"free dozen[^.!?]{0,60}|"
    r"1 free item(?: for life)?|"
    r"free item for life"
    r")"
)
CONDITION_RES = [
    re.compile(p, re.I)
    for p in (
        r"frontline workers[^.!?]{0,100}",
        r"military\s*/\s*first\s+responder[s]?[^.!?]{0,80}",
        r"(?:for\s+)?(?:military|first\s+responders?)[^.!?]{0,60}",
        r"(?:on\s+)?(?:your\s+)?first\s+(?:\d+\s+)?(?:orders?|boxes?|weeks?|deliveries?|box)\b",
        r"applies to boxes?\s+\d+\s*[-–]\s*\d+",
        r"boxes?\s+\d+\s*[-–]\s*\d+",
        r"across\s+\d+\s+boxes?",
        r"spend\s+\$?\d+\+?",
        r"for\s+(?:1\s+year|one year|life)\b",
        r"all year round",
        r"next month",
        r"upcoming order",
        r"national wellness month",
        r"new (?:customers?|subscribers?)\s*only",
        r"new customers?\b",
        r"qualifying auto-renewing subscription[^.!?]{0,40}",
        r"one per box[^.!?]{0,100}",
        r"varies by plan",
        r"expires\s+\d+\s+days after[^.!?]{0,80}",
        r"free meals applied as discount on first box",
        r"subscription\b[^.!?]{0,40}",
    )
]
NO_CODE_RE = re.compile(
    r"(?i)\b(?:no code (?:needed|required|necessary)|code not required|"
    r"automatically applied|auto[- ]?applied|no promo code needed)\b"
)
VALID_UNTIL_NOT_STATED = "Not stated on the official page"
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
    "BUTTONS", "BUTTON", "CLICK", "VERIFY", "VERIFIED", "BELOW", "SIGNUP",
    "LOGIN", "HERO", "TODAY", "START",
}
_FAKE_CODE_CONTEXT_RE = re.compile(
    r"(?i)get\s+code.*button|click.*get\s+code|buttons?\s+below|get\s+verified and receive"
)


def _validate_code(code: str | None, title: str = "", extra: str = "") -> str | None:
    if not code:
        return None
    code = code.upper().strip()
    if not code or code in CODE_STOP or code.isdigit():
        return None
    if len(code) < 4 or len(code) > 16:
        return None
    blob = f"{title} {extra}"
    if _FAKE_CODE_CONTEXT_RE.search(blob):
        return None
    return code


def _dedupe_repeated_segments(title: str) -> str:
    """Drop later repeats of the same phrase (duplicate hero copy on official pages)."""
    for size in range(min(len(title) // 2, 72), 14, -1):
        for i in range(0, len(title) - size + 1):
            seg = title[i : i + size].strip()
            seg_l = seg.lower()
            if len(seg_l) < 15:
                continue
            rest = title[i + size :]
            idx = rest.lower().find(seg_l)
            if idx >= 0:
                rest = (rest[:idx] + rest[idx + len(seg) :]).strip(" ,.*")
                title = (title[: i + size] + (" " + rest if rest else "")).strip()
                title = re.sub(r"\s+", " ", title)
                return _dedupe_repeated_segments(title)
    return title


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
        code = _validate_code((m.group(1) or "").upper(), text)
        if code:
            return code
    return None


def _normalize_quotes(text: str) -> str:
    return (text or "").translate(
        str.maketrans(
            {
                "\u2018": "'",
                "\u2019": "'",
                "\u201c": '"',
                "\u201d": '"',
                "\u00b4": "'",
                "`": "'",
            }
        )
    )


_AUDIENCE_HINTS = re.compile(
    r"(?i)frontline workers|first responders|military\s*/\s*first responder|"
    r"healthcare workers|teachers|students|seniors|military members"
)


def _prefer_audience_headline(title: str, snippet: str = "", conditions: str = "") -> str:
    """When official copy names an audience but the title does not, use that sentence."""
    title = (title or "").strip()
    for blob in (snippet, conditions):
        if not blob or not _AUDIENCE_HINTS.search(blob):
            continue
        if _AUDIENCE_HINTS.search(title):
            return title
        for sent in re.split(r"(?<=[.!?])\s+", blob.strip()):
            s = sent.strip(" ,;")
            if _AUDIENCE_HINTS.search(s) and PROMO_RE.search(s):
                cleaned = _clean_title(s)
                if cleaned and len(cleaned) >= 20:
                    return cleaned
        if _AUDIENCE_HINTS.search(blob) and PROMO_RE.search(blob) and len(blob) <= 140:
            cleaned = _clean_title(blob.strip())
            if cleaned:
                return cleaned
    return title


def _clean_title(title: str) -> str:
    from html import unescape

    title = _normalize_quotes(unescape(title))
    title = re.sub(r"\s+", " ", title).strip(" -–|:;,.")
    title = re.sub(r"^[^A-Za-z0-9$]+", "", title)
    title = re.sub(r"^(?:and|or|the|a|an|of|to|for|on|in|with|your|our|so|now|shop now)\s+", "", title, flags=re.I)
    # Restore "$N" when a dollar amount was clipped at window start
    if re.match(r"^\d{2,3}\s+on\s+your\s+first", title, re.I):
        title = "$" + title
    # Prefer a clean "20% Off" badge over "20% Off <product dump>"
    m20 = re.match(r"(?i)^(20%\s*off)\b(.{0,80})$", title)
    if m20 and re.search(r"\b(ground beef|chicken|pork|steak|lb\b|pack)\b", m20.group(2), re.I):
        title = "20% Off"    # Normalize "use code X …" into a readable offer title
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
    if m and m.start() > 40 and not _AUDIENCE_HINTS.search(title[: m.start()]):
        original = title
        # rewind to nearest sentence/capital/$ start before promo
        cut = title.rfind(". ", 0, m.start())
        if cut == -1:
            cut = max(0, m.start() - 30)
            while cut < m.start() and not (
                title[cut].isupper() or title[cut].isdigit() or title[cut] == "$"
            ):
                cut += 1
            # If we landed on digits of a $amount, include the dollar sign
            if cut > 0 and title[cut].isdigit() and title[cut - 1] == "$":
                cut -= 1
        else:
            cut = cut + 2
        title = title[cut:].strip()
        # Bare "$N off" after cut — keep earlier free/plus context from original sentence
        if re.fullmatch(r"\$\d+(?:\.\d{1,2})?\s*off", title, re.I):
            anchor = re.search(
                r"(?i)((?:choose\s+)?free\b.{0,100}|plus\s+)\$\d+(?:\.\d{1,2})?\s*off",
                original,
            )
            if anchor:
                title = anchor.group(0).strip()
    # Drop leftover leading chrome words after cut (keep Save/$ amounts)
    title = re.sub(r"^(?:Get Started|Login|Menu|Home)\s+", "", title, flags=re.I)
    # Normalize CTA-only titles to the promo phrase
    cta = re.match(r"(?i)^click\s+here\s+for\s+(.+)$", title)
    if cta:
        title = cta.group(1).strip()
        if title and title[0].islower():
            title = title[0].upper() + title[1:]
    # Prefer "Save $N …" over bare "$N …" when both appear; restore Save if clipped
    if re.match(r"^\$\d+", title) and re.search(r"(?i)first\s+\d+\s+boxes?", title):
        if not title.lower().startswith("save"):
            title = "Save " + title
    # Home Chef UI status chrome → real offer phrase only
    if re.search(r"(?i)successfully applied|code successfully", title):
        m = re.search(
            r"(?i)(\d+\s*free meals?(?:\s*\+\s*free shipping)?(?:\s+on\s+(?:your\s+)?first\s+box)?)",
            title,
        )
        if m:
            title = m.group(1).strip()
            title = title[0].upper() + title[1:] if title else title
    # Strip legal/UI crumbs that are not offer copy
    title = re.sub(r"(?i)\s*see\s*t&?\s*cs\.?\s*$", "", title)
    title = re.sub(r"(?i)\s*see\s*terms(?:\s*(?:and|&)\s*conditions)?\.?\s*$", "", title)
    # Coupon hub / brand listing chrome
    title = re.sub(r"(?i)^[\w\s&'-]{0,48}coupon codes and promos:\s*", "", title)
    title = re.sub(r"(?i)^coupon codes and promos:\s*", "", title)
    # Nav / category crumbs before the promo phrase
    title = re.sub(r"(?i)^dinners,?\s*easy cleanup\s*", "", title)
    title = re.sub(r"(?i)^meal kits today and get\s+", "", title)
    # Marketing tails
    title = re.sub(r"(?i)\s*learn more about .+$", "", title)
    title = re.sub(r"(?i)\s*get offer\s*\*?\s*.*$", "", title)
    title = re.sub(r"(?i)\s*\*one free item per box while subscripti.*$", "", title)
    title = re.sub(r"(?i)\s*licious starts here\s*", "", title)
    # Brand prefix before the offer sentence
    title = re.sub(
        r"(?i)^(?:chefs plate|hellofresh|everyplate|green chef|butcherbox|factor):\s*",
        "",
        title,
    )
    # Long nav dumps: keep the promo token only
    if re.search(r"(?i)satisfaction guarantee|third-party certified|animal welfare", title):
        for pat in (
            r"(?i)\bfree shipping\b",
            r"(?i)\bfree ribeyes?\b",
            r"(?i)\$\d+(?:\.\d{1,2})?\s*off",
            r"(?i)\d{1,3}%\s*off",
            r"(?i)\d+\s*free meals?",
        ):
            m = re.search(pat, title)
            if m:
                chunk = m.group(0).strip()
                title = chunk[0].upper() + chunk[1:] if chunk and chunk[0].islower() else chunk
                break
    # Marketing wrapper around a trial headline
    tm = re.match(r"(?i)^try our (free \d+[-\s]?day trial)\b", title)
    if tm:
        title = tm.group(1)
        title = title[0].upper() + title[1:]
    title = re.sub(r"[\ufffd]+", "", title)
    # Social / footer icon chrome glued to promo text
    title = re.sub(
        r"(?i)(?:facebook|twitter|instagram|linkedin|pinterest|youtube|tiktok|snapchat)+$",
        "",
        title,
    )
    title = re.sub(
        r"(?i)^hellofresh(?:®|\u00ae)?\s*canada\s*meal kits:\s*",
        "",
        title,
    )
    title = re.sub(r"\s*\|\s*[A-Za-z][A-Za-z0-9 &'-]{1,40}$", "", title)
    title = _dedupe_repeated_segments(title)
    title = re.sub(r"(?i)\s*get up to\s*$", "", title)
    hf = re.search(r"(?i)(?:get up to )?\d+\s*free meals?\s*\+\s*free sides for life\*?", title)
    if hf and title.lower().count("free meals") > 1:
        title = hf.group(0).strip()
        if title and title[0].islower():
            title = title[0].upper() + title[1:]
    title = re.sub(r"\s+", " ", title).strip(" -–|:;,.")
    if title and title[0].islower() and not title.startswith("use "):
        # Capitalize leading letter for display only when we already validated promo
        pass
    return title.strip()


def _looks_like_real_promo(title: str, price: str | None, code: str | None) -> bool:
    """Reject marketing fluff / fallback copy pretending to be an offer."""
    t = title.lower().strip()
    if len(t) < 8:
        return False
    # Short percent / $off headlines like "15% Off" / "$100 off" are valid
    if len(t) < 10 and not (
        PERCENT_RE.search(title) or re.search(r"\$\d+(?:\.\d{1,2})?\s*off", title, re.I)
    ):
        return False
    if re.search(r"(?i)offer is based on\b", title):
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
    if re.search(r"(?i)click.*get\s+code.*button|get\s+verified and receive your discount", t):
        return False
    if re.fullmatch(r"(?i)life\*?\s*(\*one free item per box while subscripti)?", t.strip()):
        return False
    # Subscription perks like bare "Free Shipping" are not standalone promos
    if re.fullmatch(r"(?i)free\s+shipping(?:\s+on\s+(?:all|every)\s+orders?)?\.?", t):
        return False
    if re.search(r"(?i)free\s+shipping\s+and\s+no\s+subscription", t):
        if not re.search(r"(?i)(?:\d+%\s*off|\$\d+\s*off|save\s+\$?\d+)", t):
            return False
    if re.fullmatch(r"(?i)factor\s+box,\s*plus\s+free\s+shipping", t):
        return False
    if _is_unit_price_not_promo(title, price):
        return False
    has_promo = bool(PROMO_RE.search(title))
    strong = bool(
        PERCENT_RE.search(title)
        or re.search(r"\$\d+\s*off", title, re.I)
        or re.search(r"\d+\s*free meals?", title, re.I)
        or re.search(r"free (?:breakfast|lunch|item|gift|dozen|trial|shipping|protein|favorites|welcome)", title, re.I)
        or re.search(r"free (?:\d+[-\s]?day\s+)?trial", title, re.I)
        or re.search(r"\$[\d,]+\s*(?:worth|value).{0,40}free", title, re.I)
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


def _extract_benefit(text: str) -> str:
    found: list[str] = []
    seen: set[str] = set()
    for m in BENEFIT_RE.finditer(text or ""):
        chunk = re.sub(r"\s+", " ", m.group(0)).strip(" -–|:;,.")
        key = chunk.lower()
        if not chunk or key in seen:
            continue
        seen.add(key)
        found.append(chunk)
        if len(found) >= 4:
            break
    if found:
        return " + ".join(found)
    # Fall back to short title only when it already is a promo headline
    t = re.sub(r"\s+", " ", (text or "")).strip()
    if t and PROMO_RE.search(t) and len(t) <= 120:
        return t[:200]
    return ""


def _extract_conditions(text: str, near: str | None = None) -> str:
    found: list[str] = []
    seen: set[str] = set()
    text = text or ""
    near_positions: list[int] = []
    if near:
        nl = near.lower()
        start = 0
        tl = text.lower()
        while True:
            i = tl.find(nl, start)
            if i < 0:
                break
            near_positions.append(i)
            start = i + max(1, len(nl))
    for cre in CONDITION_RES:
        for m in cre.finditer(text):
            if near_positions and not any(0 <= (m.start() - p) <= 90 for p in near_positions):
                continue
            chunk = re.sub(r"\s+", " ", m.group(0)).strip(" -–|:;,.")
            key = chunk.lower()
            if not chunk or key in seen:
                continue
            seen.add(key)
            found.append(chunk)
            if len(found) >= 5:
                break
        if len(found) >= 5:
            break
    return "; ".join(found)


# UI chrome mistaken for conditions during extract — strip only, never invent replacements
_CONDITION_CTA_RE = re.compile(
    r"(?i)\s*(?:click\s+here\s+for\s+.*|redeem\s+now\s*|get\s+started\s+today!?)\s*$"
)
_CONDITION_UI_JUNK_RE = re.compile(r"(?i)\bwho you are\b|\bregistered dietitians\b|\bmore question")
_CONDITION_TRAILING_JUNK_RE = re.compile(r"(?i)\s*,?\s*more question.*$")


def clean_conditions(raw: str) -> str:
    """Dedupe and join condition fragments into one readable line. No new meaning."""
    if not raw or not str(raw).strip():
        return ""
    parts: list[str] = []
    for piece in str(raw).split(";"):
        piece = _CONDITION_CTA_RE.sub("", piece.strip()).strip(" -–|,." )
        if not piece:
            continue
        if _CONDITION_UI_JUNK_RE.search(piece):
            salvaged: list[str] = []
            for seg in (x.strip() for x in piece.split(",")):
                if not seg:
                    continue
                seg = _CONDITION_TRAILING_JUNK_RE.sub("", seg).strip(" ,.")
                if seg and not _CONDITION_UI_JUNK_RE.search(seg):
                    salvaged.append(seg)
            piece = ", ".join(salvaged)
        if piece:
            parts.append(piece)
    if not parts:
        return ""

    # Exact dedupe (case-insensitive), keep first casing
    seen: set[str] = set()
    unique: list[str] = []
    for p in parts:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)

    # Drop shorter fragment when fully contained in a longer one (same source text)
    kept: list[str] = []
    lowers = [p.lower() for p in unique]
    for i, p in enumerate(unique):
        pl = lowers[i]
        if any(i != j and len(pl) >= 4 and pl in lowers[j] for j in range(len(unique))):
            continue
        kept.append(p)

    out = ", ".join(kept)
    if _CONDITION_UI_JUNK_RE.search(out):
        out = ", ".join(
            p for p in (x.strip() for x in out.split(",")) if p and not _CONDITION_UI_JUNK_RE.search(p)
        )
    out = _CONDITION_TRAILING_JUNK_RE.sub("", out).strip(" ,.")
    if out and out[0].islower():
        out = out[0].upper() + out[1:]
    return out[:320]


def _enrich_details(
    title: str,
    extra: str,
    code: str | None,
    valid_until: str | None,
) -> dict[str, str]:
    """Fill structured detail fields from already-extracted official text only."""
    blob = " ".join(x for x in (title, extra) if x)
    benefit = _extract_benefit(title) or _extract_benefit(blob)
    focus = ""
    pm = PERCENT_RE.search(title) or re.search(r"\$\d+\s*off|\d+\s*free meals?", title, re.I)
    if pm:
        focus = pm.group(0)
    title_conds = _extract_conditions(title)
    strong_title = bool(
        re.search(
            r"(?i)applies to|across\s+\d+|spend\s+\$|first\s+\d+\s+(?:orders?|boxes?|deliveries?|weeks?)",
            title or "",
        )
    )
    parts: list[str] = []
    seen_c: set[str] = set()
    chunks = [title_conds]
    if not (title_conds and strong_title):
        chunks.append(_extract_conditions(extra or "", near=focus or None))
    for chunk in chunks:
        if not chunk:
            continue
        for piece in chunk.split("; "):
            key = piece.lower().strip()
            if key and key not in seen_c:
                seen_c.add(key)
                parts.append(piece.strip())
    conditions = clean_conditions("; ".join(parts))
    out: dict[str, str] = {}
    if benefit:
        out["benefit"] = benefit[:240]
    if conditions:
        out["conditions"] = conditions
    if code:
        out["code_required"] = "yes"
    elif NO_CODE_RE.search(blob):
        out["code_required"] = "no"
    if valid_until:
        out["valid_until"] = valid_until
    else:
        out["valid_until_note"] = VALID_UNTIL_NOT_STATED
    return out


_INTRO_PROMO_HEAVY = re.compile(
    r"(?i)(\d{1,3}%\s*off|\$\d+\s*off|use code|coupon code|promo code|limited.?time|save \$\d+)"
)
_INTRO_JUNK = re.compile(
    r"(?i)(cookie policy|privacy policy|terms of service|subscribe to our newsletter|sign up for|"
    r"these statements have not been evaluated|not intended to diagnose|nutritional information|"
    r"ingredients: pork|serving size \d|calories: \d|get verified and receive your discount)"
)
_INTRO_BAD_PATH = re.compile(
    r"(?i)(/guides/|/blog(?:/|$)|/offer|/lp/|specialty_discount|/pages/hero|/eat/coupon|/limited-time/)"
)
_INTRO_ARTICLE = re.compile(
    r"(?i)(beginning with recipes|written by|what'?s changing|starting august|earlier this year, we asked)"
)
_INTRO_NOT_BRAND = re.compile(r"(?i)^explore .+ blog for")


def _page_visible_text(html: str) -> str:
    stripped = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html or "")
    stripped = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", stripped)
    stripped = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", stripped)
    stripped = re.sub(r"(?s)<[^>]+>", " ", stripped)
    return re.sub(r"\s+", " ", stripped).strip()


def _is_unit_price_not_promo(title: str, price: str | None = None) -> bool:
    blob = f"{title} {price or ''}".lower()
    if re.search(r"(?i)\$\d+(?:\.\d{1,2})?\s*(?:/|\s*per\s*)meal", blob):
        if not re.search(r"(?i)(?:off|save|discount|\d+%\s*off|free\s+\w)", blob):
            return True
    if re.search(r"(?i)\$\d+(?:\.\d{1,2})?\s*/\s*week", blob):
        if not re.search(r"(?i)(?:off|save|discount|free)", blob):
            return True
    if re.search(r"(?i)from \$\d+(?:\.\d{1,2})?\s*each", blob):
        return True
    return False


def _offer_in_visible_page(title: str, code: str | None, html: str) -> bool:
    """Promo must appear in visible page text — not only sitewide JSON/script chrome."""
    text = _page_visible_text(html).lower()
    if not text:
        return False
    if code and code.lower() in text:
        return True
    clean = _clean_title(title).lower()
    if len(clean) >= 12 and clean in text:
        return True
    for token in (
        r"\d{1,3}%\s*off",
        r"\$\d+\s*off",
        r"\d+\s*free meals?",
        r"free dozen",
        r"free shipping",
    ):
        m = re.search(token, title, re.I)
        if m and m.group(0).lower() in text:
            return True
    return False


def _intro_is_brand_copy(text: str, source_url: str) -> bool:
    text = (text or "").strip()
    if len(text) < 35:
        return False
    if (
        _INTRO_JUNK.search(text)
        or _INTRO_ARTICLE.search(text)
        or _INTRO_NOT_BRAND.search(text)
        or _INTRO_PROMO_HEAVY.search(text)
    ):
        return False
    if len(text) >= 470 and not text.rstrip().endswith((".", "!", "?")):
        return False
    if re.search(r"(?i)\bpayin\s*$|\bpayin\b", text) and not text.rstrip().endswith((".", "!", "?")):
        return False
    path = urlparse(source_url or "").path
    if _INTRO_BAD_PATH.search(path):
        return False
    return True


def _clean_intro(text: str) -> str:
    from html import unescape

    text = _normalize_quotes(unescape(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(?i)\s*(shop now|get started|order now|learn more)\s*\.?\s*$", "", text)
    return text.strip()


def extract_provider_intro(html: str, final_url: str) -> dict[str, str] | None:
    """Brand description from official homepage meta or body — not blog/promo articles."""
    path = urlparse(final_url or "").path
    if _INTRO_BAD_PATH.search(path):
        return None

    parser = _MetaParser()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001
        pass

    ranked: list[tuple[int, str]] = []
    for key, base in (("og:description", 55), ("description", 45), ("twitter:description", 40)):
        val = (parser.metas.get(key) or "").strip()
        if len(val) < 35:
            continue
        score = base
        if _INTRO_PROMO_HEAVY.search(val[:120]):
            score -= 35
        if _INTRO_JUNK.search(val) or _INTRO_NOT_BRAND.search(val):
            score -= 40
        ranked.append((score, val))

    for p in parser.texts[:20]:
        p = re.sub(r"\s+", " ", p).strip()
        if not (40 <= len(p) <= 700):
            continue
        if _INTRO_PROMO_HEAVY.search(p[:120]) or _INTRO_JUNK.search(p) or _INTRO_ARTICLE.search(p):
            continue
        ranked.append((28 + min(len(p) // 12, 18), p))

    if not ranked:
        return None
    ranked.sort(key=lambda x: x[0], reverse=True)
    best = _clean_intro(ranked[0][1])
    if len(best) < 35 or ranked[0][0] < 15:
        return None
    if len(best) > 480:
        cut = best.rfind(". ", 0, 480)
        if cut > 200:
            best = best[: cut + 1].strip()
        else:
            return None
    if not _intro_is_brand_copy(best, final_url):
        return None
    return {"intro": best, "intro_source_url": final_url}


def _offer_passes_quality_gate(row: dict[str, Any]) -> bool:
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent
    tools = str(root / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    from offer_quality import offer_passes_quality

    return offer_passes_quality(row)


def _cached_offer_still_valid(row: dict[str, Any]) -> bool:
    """Reuse prior official extracts using scrape-time record, not live re-fetchability."""
    title = row.get("title") or ""
    if _is_unit_price_not_promo(title, row.get("price")):
        return False
    if not _looks_like_real_promo(title, row.get("price"), row.get("code")):
        return False
    if not _offer_passes_quality_gate(row):
        return False
    if row.get("visible_verified") is False:
        return False
    if row.get("visible_verified") is True:
        return True
    src = (row.get("source_url") or "").strip()
    fetched = (row.get("fetched_at") or "").strip()
    if src and fetched:
        return True
    return False


def _annotate_scrape_record(row: dict[str, Any]) -> dict[str, Any]:
    kept = dict(row)
    if not kept.get("verification_basis"):
        kept["verification_basis"] = "scrape_record"
    return kept


def _dedupe_provider_offers(offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for o in offers:
        key = (
            (o.get("code") or "").upper(),
            (o.get("benefit") or o.get("title") or "").strip().lower()[:90],
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(o)
    return out


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

    # Plain text corpus for condition mining (official page only; never invent)
    stripped_page = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    stripped_page = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", stripped_page)
    stripped_page = re.sub(r"(?s)<[^>]+>", " ", stripped_page)
    stripped_page = re.sub(r"\s+", " ", stripped_page)
    page_terms_blob = stripped_page[:120000]

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
        code = _validate_code(code, title, extra)
        if not _looks_like_real_promo(title, price, code):
            return
        if not _offer_in_visible_page(title, code, html):
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
        # Prefer local window; also mine official-page sentences that mention this promo token
        nearby = extra or ""
        if promo_token and page_terms_blob:
            for sent in re.split(r"(?<=[.!*])\s+", page_terms_blob):
                sl = sent.lower()
                if promo_token in sl and 20 <= len(sent) <= 500:
                    nearby = (nearby + " " + sent).strip()
        elif page_terms_blob and title:
            # Free-meal / free-breakfast style titles without percent/$ token
            keys = []
            for m in re.finditer(
                r"(?i)\d+\s*free meals?|free breakfast|free shipping|free dozen|free item",
                title,
            ):
                keys.append(m.group(0).lower())
            for sent in re.split(r"(?<=[.!*])\s+", page_terms_blob):
                sl = sent.lower()
                if keys and any(k in sl for k in keys) and 20 <= len(sent) <= 500:
                    nearby = (nearby + " " + sent).strip()
        details = _enrich_details(item["title"], nearby[:4000], code, valid_until)
        item.update(details)
        if item.get("valid_until") and _expired(str(item["valid_until"])):
            item["status"] = "expired"
            item.pop("valid_until_note", None)
        if not _offer_passes_quality_gate(item):
            return
        item["visible_verified"] = True
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
        r"[^.!?]{0,120}(?:\d{1,3}%\s*off|\$\d+\s*off|\$\d+(?:\.\d{1,2})?\s*/\s*meals?|\d+\s*free meals?|free breakfast|free lunch|free shipping|use code\s+[A-Z0-9]{4,}|with code\s+[A-Z0-9]{4,})[^.!?]{0,120}",
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
    provider_profiles: dict[str, dict[str, Any]] = {}

    prev_by_provider: dict[str, list[dict[str, Any]]] = {}
    prev_profiles: dict[str, dict[str, Any]] = {}
    if DATA_PATH.exists():
        try:
            prev = json.loads(DATA_PATH.read_text(encoding="utf-8"))
            for o in prev.get("offers") or []:
                name = o.get("provider") or ""
                if name:
                    prev_by_provider.setdefault(name, []).append(o)
            prev_profiles = dict(prev.get("provider_profiles") or {})
        except (OSError, json.JSONDecodeError):
            prev_by_provider = {}
            prev_profiles = {}

    for provider in cfg["providers"]:
        urls = provider.get("promo_urls") or [provider["promo_url"]]
        robots_url = provider.get("robots_url") or f"https://{provider['domain']}/robots.txt"
        got_page = False
        got_offers = False
        last_error = ""
        provider_offers: list[dict[str, Any]] = []
        best_intro: dict[str, Any] | None = None
        home_url = (cfg.get("affiliates") or {}).get(provider["name"], "")
        if home_url and robots_allows(robots_url, home_url):
            status, final_url, body = fetch(home_url)
            if status == 200 and not body.startswith("__ERROR__"):
                best_intro = extract_provider_intro(body, final_url)
                fetch_log.append(
                    {
                        "provider": provider["name"],
                        "url": home_url,
                        "http_status": status,
                        "final_url": final_url,
                        "status": "ok_intro_only" if best_intro else "ok_no_intro",
                        "robots_allowed": True,
                    }
                )
            time.sleep(0.8)
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
            provider_offers.extend(offers)
            got_page = True
            if offers:
                got_offers = True
            time.sleep(1.0)

        merged = _dedupe_provider_offers(provider_offers)[:6]
        if merged:
            all_offers.extend(merged)
        if best_intro:
            best_intro["fetched_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            provider_profiles[provider["name"]] = best_intro
        elif prev_profiles.get(provider["name"]):
            old = prev_profiles[provider["name"]]
            if _intro_is_brand_copy(old.get("intro") or "", old.get("intro_source_url") or ""):
                provider_profiles[provider["name"]] = old

        if not got_offers:
            # Keep last good extract when live fetch fails, returns zero promos, or robots blocks.
            # Never invent new rows — only reuse previously scraped official extracts.
            cached = prev_by_provider.get(provider["name"]) or []
            if cached:
                reused = 0
                for row in cached:
                    if not _cached_offer_still_valid(row):
                        continue
                    kept = _annotate_scrape_record(row)
                    if not kept.get("valid_until") and not kept.get("valid_until_note"):
                        kept["valid_until_note"] = VALID_UNTIL_NOT_STATED
                    all_offers.append(kept)
                    reused += 1
                fetch_log.append(
                    {
                        "provider": provider["name"],
                        "url": urls[0],
                        "status": "reused_previous_extract",
                        "error": last_error or ("ok_no_promo" if got_page else "unknown"),
                        "offers_reused": reused,
                        "note": "Live fetch failed or returned no promo; kept prior official-page extract. Not invented.",
                    }
                )
            elif not got_page:
                fetch_log.append(
                    {
                        "provider": provider["name"],
                        "url": urls[0],
                        "status": "all_urls_failed",
                        "error": last_error or "unknown",
                    }
                )

    # Final safeguard: never drop a provider that still has a prior official extract.
    have_by_name: dict[str, list[dict[str, Any]]] = {}
    for row in all_offers:
        name = row.get("provider") or ""
        if name:
            have_by_name.setdefault(name, []).append(row)
    for provider in cfg["providers"]:
        name = provider["name"]
        if have_by_name.get(name):
            continue
        cached = prev_by_provider.get(name) or []
        if not cached:
            continue
        reused = 0
        for row in cached:
            if not _cached_offer_still_valid(row):
                continue
            kept = _annotate_scrape_record(row)
            if not kept.get("valid_until") and not kept.get("valid_until_note"):
                kept["valid_until_note"] = VALID_UNTIL_NOT_STATED
            all_offers.append(kept)
            reused += 1
        fetch_log.append(
            {
                "provider": name,
                "url": (provider.get("promo_urls") or [provider.get("promo_url")])[0],
                "status": "reused_previous_extract",
                "offers_reused": reused,
                "note": "Safeguard merge: provider had zero fresh rows; kept prior official extract.",
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
        "provider_profiles": provider_profiles,
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
