"""Screenshot Hoot's pages with Playwright so a UI change can be checked visually.

    uv run --with playwright python .claude/skills/streamlit-verify/scripts/screenshot.py \
        --out /path/to/dir [--pages home,practice,jd,lab] [--base http://localhost:8501]

Waits for the Streamlit server, loads each page, waits until Streamlit stops "Running",
saves a full-page PNG per page and prints any browser console errors. Needs the app
already running (`uv run streamlit run app.py`). Never clicks anything, so it never
triggers an LLM call.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

PAGES = {"home": "", "practice": "practice", "jd": "jd", "lab": "lab", "privacy": "privacy"}


# When a sub-page URL (/practice) is opened directly, the Streamlit client first probes
# /practice/_stcore/health and /practice/_stcore/host-config, gets 404s, then falls back to the
# root. That is normal Streamlit behaviour and not a bug in the app, so it is not reported.
_NOISE = ("_stcore/health", "_stcore/host-config", "Failed to load resource")


def _is_noise(text: str) -> bool:
    return any(n in text for n in _NOISE)


def wait_for_server(base: str, timeout_s: float = 60) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/_stcore/health", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(1)
    sys.exit(f"Streamlit is not answering at {base}. Start it: uv run streamlit run app.py")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="http://localhost:8501")
    ap.add_argument("--out", required=True, help="directory for the PNGs")
    ap.add_argument("--pages", default=",".join(PAGES), help="comma list of " + ",".join(PAGES))
    ap.add_argument("--width", type=int, default=1400)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument(
        "--sidebar-collapsed", action="store_true", help="also shoot with the sidebar closed"
    )
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    wait_for_server(args.base)
    unknown = [p for p in args.pages.split(",") if p not in PAGES]
    if unknown:
        sys.exit(f"unknown pages {unknown}; choose from {list(PAGES)}")

    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name in args.pages.split(","):
            # One context per page: Streamlit remembers a collapsed sidebar across reloads
            # inside the same browser context, which would leak into the next page's shot.
            ctx = browser.new_context(viewport={"width": args.width, "height": args.height})
            page = ctx.new_page()
            page.on(
                "console",
                lambda m, n=name: (
                    errors.append(f"[{n}] {m.text}")
                    if m.type == "error" and not _is_noise(m.text)
                    else None
                ),
            )
            page.on("pageerror", lambda e, n=name: errors.append(f"[{n}] pageerror: {e}"))
            page.on(
                "response",
                lambda r, n=name: (
                    errors.append(f"[{n}] HTTP {r.status} {r.url}")
                    if r.status >= 400 and not _is_noise(r.url)
                    else None
                ),
            )
            page.goto(f"{args.base}/{PAGES[name]}", wait_until="networkidle")
            page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=30_000)
            # Streamlit shows a "Running" status widget while a script run is in flight.
            page.wait_for_selector(
                '[data-testid="stStatusWidget"]', state="detached", timeout=30_000
            )
            page.wait_for_timeout(500)  # let fonts and CSS transitions settle
            path = out / f"{name}.png"
            page.screenshot(path=str(path), full_page=True)
            print(f"{name:9} -> {path}")
            if args.sidebar_collapsed:
                btn = page.locator('[data-testid="stSidebarCollapseButton"] button')
                if btn.count():
                    btn.first.click()
                    page.wait_for_timeout(600)
                    path = out / f"{name}_collapsed.png"
                    page.screenshot(path=str(path), full_page=True)
                    print(f"{name:9} -> {path} (sidebar collapsed)")
            ctx.close()
        browser.close()

    if errors:
        print("\nBrowser console errors and failed requests (duplicates collapsed):")
        for e in dict.fromkeys(errors):
            print("  ", e)
    else:
        print("\nNo browser console errors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
