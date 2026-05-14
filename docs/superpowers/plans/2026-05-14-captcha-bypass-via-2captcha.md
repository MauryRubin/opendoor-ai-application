# CAPTCHA Bypass via 2captcha Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Submit the Opendoor application reliably by solving Cloudflare Turnstile via the 2captcha API instead of asking the AI vision model to click the checkbox (which Cloudflare detected as bot-like and rejected three times in a row).

**Architecture:** When Turnstile is detected on the page, the script auto-extracts the sitekey, sends it + the page URL to the 2captcha API, waits 20-60s for a valid token, injects the token into the Turnstile response field via JavaScript, and dispatches the change events that Cloudflare's callback listens for. The AI agent never sees, clicks, or thinks about the CAPTCHA.

**Tech Stack:**
- Python 3.9 + Playwright (existing)
- `2captcha-python>=1.2.0` (new — official 2captcha SDK)
- 2captcha.com account, funded with ~$1 (each Turnstile solve costs ~$0.003)

**Why 2captcha (and not more stealth):** Stealth-only approaches we already tried failed because Cloudflare fingerprints multi-dimensional signals (TLS, canvas, WebGL, behavioral timing, IP reputation, etc.) that browser patches cannot fully spoof. 2captcha works because the token is generated on real browsers with real human + AI labor; Cloudflare cannot distinguish it from a legitimate solve. This is the industry-standard path.

**Honest narrative for the README:** The AI agent handles 100% of the application except one external API call to a CAPTCHA-solving service. This is *correct* architectural choice — CAPTCHAs are explicitly designed to require human intervention, so delegating that one step to a paid human-in-the-loop service is more honest engineering than pretending to defeat Cloudflare's fingerprinting. Update the README to call this out as a design decision, not a workaround.

---

## Prerequisites (USER ACTION, before any task)

- [ ] Sign up at https://2captcha.com (free, ~2 min)
- [ ] Add $1 to your balance via Stripe checkout (≈ 300 Turnstile solves)
- [ ] Copy your API key from the Dashboard
- [ ] Edit `/Users/sydneymalek/Code/opendoor/.env` and add:
  ```
  TWOCAPTCHA_API_KEY=<paste your key>
  ```

## File Structure

- Modify: `/Users/sydneymalek/Code/opendoor/apply.py` — add ~80 lines (helpers + integration point in form-fill loop)
- Modify: `/Users/sydneymalek/Code/opendoor/requirements.txt` — add 2captcha SDK
- Modify: `/Users/sydneymalek/Code/opendoor/.env.example` — document the new env var
- Create: `/Users/sydneymalek/Code/opendoor/test_captcha.py` — pytest unit tests for the parse + inject helpers
- Modify: `/Users/sydneymalek/Code/opendoor/apply.py` README template — note the 2captcha design decision

Helpers live in `apply.py` (project follows single-file convention; ~80 lines is acceptable).

---

### Task 1: Add 2captcha dependency and env var

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`

- [ ] **Step 1: Add dependency**

Edit `/Users/sydneymalek/Code/opendoor/requirements.txt` — add a line:
```
2captcha-python>=1.2.0
```

- [ ] **Step 2: Install**

```bash
cd /Users/sydneymalek/Code/opendoor && source venv/bin/activate && pip install -r requirements.txt
```

Expected: `Successfully installed 2captcha-python-...`

- [ ] **Step 3: Document env var**

Edit `/Users/sydneymalek/Code/opendoor/.env.example`:
```
ANTHROPIC_API_KEY=your_api_key_here
GITHUB_TOKEN=your_github_token_here
TWOCAPTCHA_API_KEY=your_2captcha_api_key_here
```

- [ ] **Step 4: Verify import works**

```bash
source venv/bin/activate && python -c "from twocaptcha import TwoCaptcha; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .env.example
git commit -m "feat: add 2captcha SDK dep and env var"
```

---

### Task 2: Sitekey extraction (with test)

**Files:**
- Create: `/Users/sydneymalek/Code/opendoor/test_captcha.py`
- Modify: `/Users/sydneymalek/Code/opendoor/apply.py`

- [ ] **Step 1: Write the failing test**

Create `/Users/sydneymalek/Code/opendoor/test_captcha.py`:
```python
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
```

- [ ] **Step 2: Install pytest if missing**

```bash
source venv/bin/activate && pip install pytest && pip freeze | grep pytest
```
Expected: `pytest==<version>`

- [ ] **Step 3: Run test, verify failure**

```bash
cd /Users/sydneymalek/Code/opendoor && source venv/bin/activate && pytest test_captcha.py -v
```
Expected: 2 errors with `ImportError: cannot import name '_extract_turnstile_sitekey' from 'apply'`

- [ ] **Step 4: Implement the function**

Add to `/Users/sydneymalek/Code/opendoor/apply.py`, immediately before `_build_form_fill_system`:
```python
def _extract_turnstile_sitekey(page) -> str | None:
    """Find the Cloudflare Turnstile sitekey on the page, if present."""
    locator = page.locator("[data-sitekey]").first
    if locator.count() == 0:
        return None
    return locator.get_attribute("data-sitekey")
```

- [ ] **Step 5: Run tests, verify pass**

```bash
pytest test_captcha.py -v
```
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add test_captcha.py apply.py
git commit -m "feat: extract Cloudflare Turnstile sitekey from page"
```

---

### Task 3: Token injection (with test)

**Files:**
- Modify: `test_captcha.py`
- Modify: `apply.py`

- [ ] **Step 1: Add failing test**

Append to `/Users/sydneymalek/Code/opendoor/test_captcha.py`:
```python
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
```

- [ ] **Step 2: Run, verify fails**

```bash
pytest test_captcha.py -v
```
Expected: ImportError on `_inject_turnstile_token`

- [ ] **Step 3: Implement**

Add to `apply.py` immediately after `_extract_turnstile_sitekey`:
```python
def _inject_turnstile_token(page, token: str) -> None:
    """Inject a solved Turnstile token into the page's response field
    and fire input/change events so Cloudflare's callback observes the change."""
    page.evaluate(
        """(token) => {
            const selector = 'input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]';
            document.querySelectorAll(selector).forEach((el) => {
                el.value = token;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            });
        }""",
        token,
    )
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest test_captcha.py -v
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add test_captcha.py apply.py
git commit -m "feat: inject Turnstile token and fire change events"
```

---

### Task 4: Orchestrator `solve_turnstile_if_present`

**Files:**
- Modify: `apply.py`

This task has no unit test — it makes a real HTTP call to 2captcha. It will be integration-tested via Stage 4 in Task 7.

- [ ] **Step 1: Add the env var read at module scope**

In `apply.py`, near the existing env var reads (after `GITHUB_TOKEN = os.getenv(...)`):
```python
TWOCAPTCHA_API_KEY = os.getenv("TWOCAPTCHA_API_KEY")
```

- [ ] **Step 2: Add the orchestrator**

In `apply.py`, immediately after `_inject_turnstile_token`:
```python
def solve_turnstile_if_present(page) -> bool:
    """If a Turnstile widget is visible on the page, solve it via 2captcha
    and inject the resulting token. Returns True if there was nothing to solve
    OR the solve succeeded; False if a Turnstile was present but solving failed.
    """
    sitekey = _extract_turnstile_sitekey(page)
    if not sitekey:
        return True

    if not TWOCAPTCHA_API_KEY:
        print("  ⚠️  Turnstile detected but TWOCAPTCHA_API_KEY is not set — cannot solve.")
        return False

    from twocaptcha import TwoCaptcha
    solver = TwoCaptcha(TWOCAPTCHA_API_KEY)
    page_url = page.url

    print(f"  🔓 Solving Turnstile via 2captcha (sitekey={sitekey[:16]}...)")
    try:
        result = solver.turnstile(sitekey=sitekey, url=page_url)
    except Exception as exc:
        print(f"  ❌ 2captcha solve failed: {exc}")
        return False

    token = result.get("code") if isinstance(result, dict) else None
    if not token:
        print(f"  ❌ 2captcha returned no token: {result}")
        return False

    print(f"  ✅ Got token ({len(token)} chars) — injecting into page")
    _inject_turnstile_token(page, token)

    run_log["api_calls"].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "purpose": "twocaptcha_turnstile_solve",
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.003,
    })
    run_log["total_cost_usd"] = round(run_log["total_cost_usd"] + 0.003, 4)
    return True
```

- [ ] **Step 3: Verify syntax**

```bash
source venv/bin/activate && python -c "import ast; ast.parse(open('apply.py').read()); print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add apply.py
git commit -m "feat: add 2captcha Turnstile orchestrator"
```

---

### Task 5: Integrate auto-solve into form-fill loop

**Files:**
- Modify: `apply.py`

The agent should NEVER see the CAPTCHA. The system silently solves it before each agent turn.

- [ ] **Step 1: Add auto-solve after each screenshot**

In `apply.py`, in `fill_form`, find the lines:
```python
            screenshot_b64, screenshot_path = take_screenshot(page, step)
```

Immediately AFTER that line (still inside the `while` loop), insert:
```python

            # Auto-solve Cloudflare Turnstile so the agent never has to handle it
            if _extract_turnstile_sitekey(page):
                solved = solve_turnstile_if_present(page)
                if solved:
                    # Give Cloudflare's callback a moment, then re-screenshot
                    page.wait_for_timeout(3000)
                    screenshot_b64, screenshot_path = take_screenshot(page, step)
```

- [ ] **Step 2: Verify syntax**

```bash
python -c "import ast; ast.parse(open('apply.py').read()); print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add apply.py
git commit -m "feat: auto-solve Turnstile transparently before each agent turn"
```

---

### Task 6: Update agent prompt — stop trying to click CAPTCHAs

**Files:**
- Modify: `apply.py` (`_build_form_fill_system`)

- [ ] **Step 1: Replace the CAPTCHA rule**

In `_build_form_fill_system`, find the rule starting with `5. CAPTCHA HANDLING` (currently a long multi-line block with cycle counts) and replace the ENTIRE rule 5 (lines `5. CAPTCHA HANDLING — ...` through `f. If you see a confirmation page ... call done with status "submitted".`) with:
```
5. CAPTCHA HANDLING — Cloudflare Turnstile is automatically solved by the system BEFORE you see each screenshot. You will rarely see one. If you DO see a "Verify you are human" widget, just call the `wait` tool with seconds=5 — the system will solve it on the next cycle. NEVER click a Turnstile checkbox yourself; the click pattern is what Cloudflare uses to flag bots.
```

- [ ] **Step 2: Verify syntax**

```bash
python -c "import ast; ast.parse(open('apply.py').read()); print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add apply.py
git commit -m "feat: tell agent the system solves CAPTCHAs, not the agent"
```

---

### Task 7: Update README narrative

**Files:**
- Modify: `apply.py` (`README_TEMPLATE`)

Add an explicit "Design choices" section to be honest about the 2captcha dependency.

- [ ] **Step 1: Find the "Why This Matters" section**

In `apply.py`, find the line in `README_TEMPLATE`:
```
## Why This Matters
```

- [ ] **Step 2: Insert a "Design Choices" section just BEFORE that line**

Add this block right before `## Why This Matters`:
```
## Design Choices

**One external service: 2captcha.** The agent handles 100% of the application except for solving Cloudflare Turnstile (the "Verify you are human" CAPTCHA Rippling shows on submit). For that one step the agent calls the 2captcha API, which returns a valid token in ~30 seconds. CAPTCHAs are *literally designed* to require human intervention, so delegating that single step to a paid solving service is the honest architectural choice — more honest than pretending to defeat Cloudflare's anti-bot fingerprinting. Cost: ~$0.003 per solve.

Everything else (parsing the resume, writing the cover letter, navigating the form, picking dropdown options, uploading files, choosing consent answers, clicking Submit, verifying success, pushing the artifacts) runs locally on the Anthropic + Playwright stack.

```

- [ ] **Step 3: Verify syntax**

```bash
python -c "import ast; ast.parse(open('apply.py').read()); print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add apply.py
git commit -m "docs: explain the 2captcha design choice in README"
```

---

### Task 8: Stage 4 — real submission

- [ ] **Step 1: Verify 2captcha balance > $0.05**

Visit https://2captcha.com/enterpage and confirm balance.

- [ ] **Step 2: Verify .env**

```bash
cd /Users/sydneymalek/Code/opendoor && awk -F'=' '/^TWOCAPTCHA_API_KEY=/ {print "key length:", length($2)}' .env
```
Expected: `key length:` followed by a number (typically 32).

- [ ] **Step 3: Run Stage 4**

```bash
source venv/bin/activate && rm -rf output/ && python apply.py 2>&1
```

- [ ] **Step 4: Watch the console**

Expected sequence after Apply is clicked:
- Turnstile appears in the page
- Auto-detected after the screenshot
- Console prints: `🔓 Solving Turnstile via 2captcha (sitekey=...)`
- 20-60 second wait while 2captcha solves
- Console prints: `✅ Got token (≈2000 chars) — injecting into page`
- Page re-screenshots, CAPTCHA gone, form submits
- Confirmation page appears
- Agent calls `done(status="submitted")`
- Phase 6 pushes to GitHub

- [ ] **Step 5: Confirm submission**

- Check email at maurydr1@gmail.com for the Opendoor confirmation
- Visit https://github.com/MauryRubin/opendoor-ai-application — the README should show today's timestamp + `submitted` status

---

## Self-Review

**Spec coverage:**
- "fullproof way to beat the captcha" → Tasks 2-5 add 2captcha integration. ✓
- "on Rippling" → Helpers use Cloudflare Turnstile selectors, which is what Rippling uses. ✓

**Placeholder scan:** No TODOs / "add error handling" / "similar to Task N". Every code block is complete. ✓

**Type consistency:** `_extract_turnstile_sitekey`, `_inject_turnstile_token`, `solve_turnstile_if_present` — names are consistent across all task references. ✓

**No undefined references:** Every function used in a later task is defined in an earlier task. ✓
