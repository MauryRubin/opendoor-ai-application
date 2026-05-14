import pytest
from playwright.sync_api import sync_playwright

from apply import _extract_turnstile_sitekey


HTML_WITH_TURNSTILE = """
<html><body>
  <form>
    <input name="email">
    <div class="cf-turnstile" data-sitekey="0x4AAAAAAATestSiteKey"></div>
    <button>Submit</button>
  </form>
</body></html>
"""

HTML_NO_TURNSTILE = "<html><body><form><input name='email'></form></body></html>"


@pytest.mark.unit
def test_extract_sitekey_when_present():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(HTML_WITH_TURNSTILE)
        assert _extract_turnstile_sitekey(page) == "0x4AAAAAAATestSiteKey"
        browser.close()


@pytest.mark.unit
def test_extract_sitekey_returns_none_when_absent():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(HTML_NO_TURNSTILE)
        assert _extract_turnstile_sitekey(page) is None
        browser.close()
