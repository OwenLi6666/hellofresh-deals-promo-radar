# ::ILANG
# [TYPE:lib][FILE:ilang_config.py]
# ::OBJECTIVE{parse_site_ilang}
#   target: 读 .ilang/site.ilang 给 scraper/build 当唯一配置真源
# ::BOUNDARY{never:在业务代码里另写一份厂商清单}
"""Minimal I-Lang config reader for site.ilang (stdlib only)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SITE_ILANG = ROOT / ".ilang" / "site.ilang"


def _kv_pairs(blob: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in re.finditer(r"(\w+):([^,\|}]+)", blob):
        out[m.group(1).strip()] = m.group(2).strip()
    return out


def load_site_config(path: Path | None = None) -> dict[str, Any]:
    p = path or SITE_ILANG
    text = p.read_text(encoding="utf-8")

    site: dict[str, str] = {}
    m = re.search(r"::STATE\{@SITE,\s*([^}]+)\}", text)
    if m:
        site = _kv_pairs(m.group(1))

    providers: list[dict[str, Any]] = []
    prov_block = re.search(
        r"::MODULE\{PROVIDERS[^}]*\}(.*?)(?=::MODULE\{|::RULE\{|::BOUNDARY\{|\Z)",
        text,
        re.S,
    )
    if prov_block:
        for line in prov_block.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("[") or line.startswith("#"):
                continue
            parts = [x.strip() for x in line.split("|")]
            if len(parts) < 3:
                continue
            name, domain = parts[0], parts[1]
            urls = [p for p in parts[2:] if p.startswith("http") and "robots.txt" not in p]
            robots_parts = [p for p in parts[2:] if "robots.txt" in p]
            robots = robots_parts[0] if robots_parts else f"https://www.{domain}/robots.txt"
            if not urls:
                continue
            providers.append(
                {
                    "name": name,
                    "domain": domain,
                    "promo_url": urls[0],
                    "promo_urls": urls,
                    "robots_url": robots,
                }
            )

    fields: list[str] = []
    fields_block = re.search(
        r"::MODULE\{FIELDS[^}]*\}(.*?)(?=::MODULE\{|::RULE\{|::BOUNDARY\{|\Z)",
        text,
        re.S,
    )
    if fields_block:
        for line in fields_block.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("["):
                continue
            fields.extend(line.split())

    affiliates: dict[str, str] = {}
    aff_block = re.search(
        r"::MODULE\{AFFILIATE[^}]*\}(.*?)(?=::MODULE\{|::RULE\{|::BOUNDARY\{|\Z)",
        text,
        re.S,
    )
    if aff_block:
        for line in aff_block.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("["):
                continue
            parts = [x.strip() for x in line.split("|")]
            if len(parts) >= 2:
                affiliates[parts[0]] = parts[1]

    affiliate_note = ""
    render_block = re.search(
        r"::MODULE\{RENDER[^}]*\}(.*?)(?=::MODULE\{|::RULE\{|::BOUNDARY\{|\Z)",
        text,
        re.S,
    )
    if render_block:
        for line in render_block.group(1).splitlines():
            line = line.strip()
            if line.startswith("affiliate_note:"):
                affiliate_note = line.split(":", 1)[1].strip()

    publisher: dict[str, str] = {}
    pub_block = re.search(
        r"::MODULE\{PUBLISHER[^}]*\}(.*?)(?=::MODULE\{|::RULE\{|::BOUNDARY\{|\Z)",
        text,
        re.S,
    )
    if pub_block:
        for line in pub_block.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("[") or "|" not in line:
                continue
            key, _, val = line.partition("|")
            publisher[key.strip()] = val.strip()

    return {
        "site": site,
        "providers": providers,
        "fields": fields,
        "affiliates": affiliates,
        "affiliate_note": affiliate_note or (
            "Links may be affiliate links. We may earn a commission at no extra cost to you."
        ),
        "publisher": publisher,
        "source_path": str(p),
    }
