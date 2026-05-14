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


from apply import _inject_turnstile_token


@pytest.mark.unit
def test_inject_token_populates_response_input():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
        <html><body>
          <input name="cf-turnstile-response" id="cf-turnstile-response">
        </body></html>
        """)
        _inject_turnstile_token(page, "test_token_xyz")
        value = page.evaluate(
            "() => document.getElementById('cf-turnstile-response').value"
        )
        assert value == "test_token_xyz"
        browser.close()


@pytest.mark.unit
def test_inject_token_populates_response_textarea():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
        <html><body>
          <textarea name="cf-turnstile-response" id="cf-turnstile-response"></textarea>
        </body></html>
        """)
        _inject_turnstile_token(page, "longer_token_abc123")
        value = page.evaluate(
            "() => document.getElementById('cf-turnstile-response').value"
        )
        assert value == "longer_token_abc123"
        browser.close()
