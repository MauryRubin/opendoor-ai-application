#!/usr/bin/env python3
"""Diagnostic harness for the Rippling Turnstile auto-solver.

Opens the application URL in real Chromium (stealth + turnstile.render hook
installed), then waits for the user to fill the form by hand. Polls every
500ms for state, and as soon as a sitekey is captured runs the same
2captcha solve + callback delivery path that apply.py uses.

The goal: prove out the captcha fix in isolation, without burning Claude
API tokens on the agent form-fill loop. Cost: ~$0.003 for one Turnstile solve.

Usage:
    source venv/bin/activate
    python diagnose_captcha.py
"""

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


def main() -> None:
    load_dotenv()

    print("=" * 64)
    print("  TURNSTILE DIAGNOSTIC HARNESS")
    print("=" * 64)
    print(f"  Application URL: {APPLICATION_URL}")
    print(f"  2captcha key set: {bool(TWOCAPTCHA_API_KEY)}")
    print()

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
        print("  >> FILL THE FORM BY HAND, then click Apply.")
        print("  >> I'll watch for Turnstile and auto-solve.")
        print("  >> Polling every 500ms. Ctrl+C to abort.")
        print()

        last_state = None
        solved = False
        max_polls = int(MAX_POLL_MINUTES * 60 / POLL_INTERVAL_SECONDS)

        for _ in range(max_polls):
            try:
                state = _read_state(page)
            except Exception as e:
                print(f"  [poll] page state unavailable: {e}")
                break

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
                break

            time.sleep(POLL_INTERVAL_SECONDS)
        else:
            print()
            print(f"  >> Timed out after {MAX_POLL_MINUTES} minutes without a sitekey capture.")

        print()
        print(f"  >> Diagnostic complete. Keeping browser open {INSPECT_WINDOW_SECONDS}s for inspection.")
        time.sleep(INSPECT_WINDOW_SECONDS)

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
