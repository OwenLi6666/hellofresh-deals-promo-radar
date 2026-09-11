import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import scraper

orig_add_holder = {}

html = (ROOT / "data/_browser_butcherbox.html").read_text(encoding="utf-8")

# Monkeypatch by wrapping extract and printing corpus path
from scraper import _MetaParser, PROMO_RE, _clean_title, _looks_like_real_promo, _score_offer
import re

parser = _MetaParser()
parser.feed(html)
corpus = []
if parser.title:
    corpus.append(parser.title.strip())
corpus.extend(parser.headings)
corpus.extend(parser.texts[:30])
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
print("CORPUS:")
for i, t in enumerate(corpus):
    print(i, repr(t[:160]))
    for m in PROMO_RE.finditer(t):
        start = max(0, m.start() - 50)
        end = min(len(t), m.end() + 80)
        window = t[start:end]
        for sent in re.split(r"[.!?\n]", t):
            if m.group(0).lower() in sent.lower() and 15 <= len(sent.strip()) <= 180:
                window = sent
                break
        window = window.strip(" -–|:;,.")
        cleaned = _clean_title(window)
        print("  match", m.group(0), "window", repr(window[:120]), "clean", repr(cleaned), "looks", _looks_like_real_promo(cleaned, None, None), "score", _score_offer(cleaned, None, None), "len", len(cleaned))
