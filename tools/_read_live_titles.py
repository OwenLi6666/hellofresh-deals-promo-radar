#!/usr/bin/env python3
import html
import re
import urllib.request

REQ = urllib.request.Request(
    "https://mealkitdeals.com/compare/",
    headers={"User-Agent": "mealkitdeals-title-check/1.0"},
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "mealkitdeals-title-check/1.0"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", errors="replace")


compare = fetch("https://mealkitdeals.com/compare/")
rows = re.findall(
    r'<tr><td><a href="/providers/[^"]+">([^<]+)</a></td><td>([^<]*)</td>',
    compare,
)
print("=== compare (one row per brand) ===")
for brand, title in rows:
    print(f"{brand} | {html.unescape(title)}")
print("brands", len(rows))

home = fetch("https://mealkitdeals.com/")
cards = re.findall(
    r'<p class="eyebrow">([^<]+)</p>\s*<h2><a[^>]*>([^<]+)</a></h2>',
    home,
)
print("=== home cards ===")
for brand, title in cards:
    print(f"{brand} | {html.unescape(title)}")
m = re.search(r"(\d+)\s+offers", home, re.I)
if m:
    print("offer_count_meta", m.group(1))
