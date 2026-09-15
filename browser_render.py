# ::ILANG
# [TYPE:tool][FILE:browser_render.py]
# ::OBJECTIVE{fetch_public_page_after_js}
#   target: 无登录、无验证码，用 Chromium 渲染公开页后返回 HTML
# ::BOUNDARY{never:登录|绕验证码|访问 robots 禁止的 URL}
"""Optional Playwright render fetch. Used only for providers listed in site.ilang RENDER_JS."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

RENDER_TIMEOUT_MS = 45_000
RENDER_SETTLE_MS = 2_500

# Realistic desktop UA; still identifies as our indexer in comment form via Accept-Language only.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def playwright_available() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def fetch_rendered(url: str) -> tuple[int, str, str]:
    """
    Load `url` in headless Chromium and return (status, final_url, html).
    On failure returns (0, url, '__ERROR__:RenderError:...').
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return 0, url, "__ERROR__:ImportError:playwright not installed"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent=BROWSER_UA,
                    locale="en-US",
                    viewport={"width": 1280, "height": 900},
                )
                page = context.new_page()
                resp = page.goto(url, wait_until="domcontentloaded", timeout=RENDER_TIMEOUT_MS)
                page.wait_for_timeout(RENDER_SETTLE_MS)
                try:
                    page.wait_for_load_state("networkidle", timeout=15_000)
                except Exception:  # noqa: BLE001 — networkidle often never fires on SPAs
                    pass
                html = page.content()
                final = page.url
                status = resp.status if resp else 200
                return status, final, html
            finally:
                browser.close()
    except Exception as e:  # noqa: BLE001
        return 0, url, f"__ERROR__:RenderError:{type(e).__name__}:{e}"
