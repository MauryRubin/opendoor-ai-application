#!/usr/bin/env python3
"""Diagnostic harness for the Rippling Turnstile auto-solver.

Two modes:

  Default — launch a fresh Playwright-managed Chromium (stealth applied,
  turnstile.render hook installed) and open the application URL.

  --cdp — attach to your real Chrome via the Chrome DevTools Protocol so
  the diagnostic uses your actual browser fingerprint and cookies. Useful
  when Cloudflare/Rippling is rejecting the Playwright-managed Chromium.

In both modes the script polls every 500ms for the hook's captured globals.
As soon as a sitekey is captured, it runs the same 2captcha solve +
callback delivery path that apply.py uses. Cost: ~$0.003 per Turnstile solve,
zero Claude API tokens.

Usage:
    source venv/bin/activate

    # Default — Playwright-managed Chromium
    python diagnose_captcha.py

    # Attach to your real Chrome (see CDP_INSTRUCTIONS below for setup)
    python diagnose_captcha.py --cdp
"""

import argparse
import time

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from apply import (
    APPLICATION_URL,
    TWOCAPTCHA_API_KEY,
    VIEWPORT,
    _install_turnstile_hook,
    solve_turnstile_if_present,
)

POLL_INTERVAL_SECONDS = 0.5
MAX_POLL_MINUTES = 10
INSPECT_WINDOW_SECONDS = 60
CDP_ENDPOINT = "http://localhost:9222"

CDP_INSTRUCTIONS = f"""
To use --cdp mode:

  1. Fully quit Chrome (Cmd+Q — all windows must be closed).
  2. Relaunch Chrome with the remote-debugging flag. From a terminal:

       open -a "Google Chrome" --args --remote-debugging-port=9222

     (Chrome opens to a blank tab. Do NOT navigate to Rippling yet.)
  3. Run this script:  python diagnose_captcha.py --cdp
  4. When the script says "Hook installed", navigate to the application URL
     in your Chrome window:

       {APPLICATION_URL}

  5. Fill the form and click Apply. The script will narrate state and
     auto-solve the Turnstile widget as soon as one renders.
"""


def _read_state(page) -> dict:
    """Snapshot turnstile-related globals + DOM state for one poll tick."""
    return page.evaluate(
        """() => ({
            sitekey: window.__cfTurnstileSitekey || null,
            renderCount: window.__cfTurnstileRenderCount || 0,
            callbackType: typeof window.__cfTurnstileCallback,
            widgetId: window.__cfTurnstileWidgetId || null,
            turnstileDefined: typeof window.turnstile,
            iframeCount: document.querySelectorAll(
                'iframe[src*="challenges.cloudflare.com"]'
            ).length,
        })"""
    )


def _fmt_state(state: dict) -> str:
    sitekey = state["sitekey"]
    sitekey_disp = (sitekey[:16] + "...") if sitekey else "None"
    return (
        f"sitekey={sitekey_disp} "
        f"renderCount={state['renderCount']} "
        f"cb={state['callbackType']} "
        f"iframes={state['iframeCount']} "
        f"turnstileDefined={state['turnstileDefined']}"
    )


def _find_rippling_page(context):
    """Return the first page in `context` whose URL contains 'rippling.com'."""
    for page in context.pages:
        try:
            if "rippling.com" in (page.url or ""):
                return page
        except Exception:
            continue
    return None


def _poll_and_solve(page) -> None:
    """Watch one page until a sitekey is captured, then run the solver."""
    last_state = None
    solved = False
    max_polls = int(MAX_POLL_MINUTES * 60 / POLL_INTERVAL_SECONDS)

    for _ in range(max_polls):
        try:
            state = _read_state(page)
        except Exception as e:
            print(f"  [poll] page state unavailable: {e}")
            return

        if state != last_state:
            print(f"  [poll] {_fmt_state(state)}")
            last_state = state

        if state["sitekey"] and not solved:
            print()
            print("  >> Sitekey captured. Calling solve_turnstile_if_present...")
            ok = solve_turnstile_if_present(page)
            solved = True
            print(f"  >> solve returned: {ok}")
            page.wait_for_timeout(5000)
            try:
                post = _read_state(page)
                print(f"  [post-solve] {_fmt_state(post)}")
            except Exception as e:
                print(f"  [post-solve] page state unavailable: {e}")
            return

        time.sleep(POLL_INTERVAL_SECONDS)

    print()
    print(f"  >> Timed out after {MAX_POLL_MINUTES} minutes without a sitekey capture.")


def _run_managed_chromium() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport=VIEWPORT,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        Stealth().apply_stealth_sync(context)
        _install_turnstile_hook(context)
        page = context.new_page()

        print(f"  Opening {APPLICATION_URL}")
        page.goto(APPLICATION_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        print()
        print("  >> Scroll to the bottom of the form, fill it out, click Apply.")
        print("  >> Polling every 500ms. Ctrl+C to abort.")
        print()

        _poll_and_solve(page)

        print()
        print(f"  >> Keeping browser open {INSPECT_WINDOW_SECONDS}s for inspection.")
        time.sleep(INSPECT_WINDOW_SECONDS)

        context.close()
        browser.close()


def _run_cdp_attached() -> None:
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(CDP_ENDPOINT)
        except Exception as e:
            print()
            print(f"  ERROR: could not connect to Chrome at {CDP_ENDPOINT}: {e}")
            print(CDP_INSTRUCTIONS)
            return

        if not browser.contexts:
            print("  ERROR: connected, but Chrome has no contexts open.")
            return
        context = browser.contexts[0]
        _install_turnstile_hook(context)

        print()
        print(f"  >> Connected to Chrome at {CDP_ENDPOINT}.")
        print("  >> Hook installed on the default context.")
        print(f"  >> Now navigate to the application URL in your Chrome window:")
        print(f"     {APPLICATION_URL}")
        print()
        print("  >> Waiting up to 5 minutes for a tab with rippling.com to appear...")

        deadline = time.time() + 300
        page = None
        while time.time() < deadline:
            page = _find_rippling_page(context)
            if page:
                break
            time.sleep(1)

        if not page:
            print()
            print("  >> No rippling.com tab appeared within 5 minutes. Aborting.")
            return

        print(f"  >> Found tab: {page.url}")
        print("  >> Fill the form and click Apply. Polling every 500ms.")
        print()

        _poll_and_solve(page)

        print()
        print("  >> Diagnostic complete. Your Chrome stays open — close this script with Ctrl+C.")
        # Don't close the user's Chrome on exit. Just detach and let them
        # inspect/close their browser themselves.
        time.sleep(INSPECT_WINDOW_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Turnstile auto-solve diagnostic.")
    parser.add_argument(
        "--cdp",
        action="store_true",
        help="Attach to your real Chrome via CDP at localhost:9222 (see --cdp-help).",
    )
    parser.add_argument(
        "--cdp-help",
        action="store_true",
        help="Print setup instructions for --cdp mode and exit.",
    )
    args = parser.parse_args()

    if args.cdp_help:
        print(CDP_INSTRUCTIONS)
        return

    load_dotenv()

    print("=" * 64)
    print("  TURNSTILE DIAGNOSTIC HARNESS")
    print("=" * 64)
    print(f"  Mode: {'CDP-attached real Chrome' if args.cdp else 'Playwright-managed Chromium'}")
    print(f"  Application URL: {APPLICATION_URL}")
    print(f"  2captcha key set: {bool(TWOCAPTCHA_API_KEY)}")

    if args.cdp:
        _run_cdp_attached()
    else:
        _run_managed_chromium()


if __name__ == "__main__":
    main()
