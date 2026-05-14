#!/usr/bin/env python3
"""
AI Job Application Agent
========================
This script autonomously applies to a job posting configured in job.json.
It parses a resume, generates a cover letter, fills the ATS form using
Claude's vision API, and documents the entire process in a public GitHub repo.

Applicant details come from applicant.json (gitignored). Job details and
narrative framing come from job.json.

Usage:
    python apply.py --dry-run    # Fill form without submitting
    python apply.py              # Full run with submission
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import fitz  # pymupdf
import imageio.v3 as iio
from dotenv import load_dotenv
from fpdf import FPDF
from PIL import Image
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent

load_dotenv(BASE_DIR / ".env", override=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
TWOCAPTCHA_API_KEY = os.getenv("TWOCAPTCHA_API_KEY")
TWOCAPTCHA_TURNSTILE_COST_USD = 0.003
MODEL = "claude-sonnet-4-20250514"


def _load_json_config(path: Path, hint: str) -> dict:
    if not path.exists():
        sys.stderr.write(
            f"ERROR: {path.name} not found at {path}.\n{hint}\n"
        )
        sys.exit(1)
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"ERROR: {path.name} is not valid JSON: {exc}\n")
        sys.exit(1)


APPLICANT = _load_json_config(
    BASE_DIR / "applicant.json",
    "Copy applicant.example.json to applicant.json and fill in your details.",
)
JOB = _load_json_config(
    BASE_DIR / "job.json",
    "Create job.json describing the role you are applying to "
    "(see README for the schema).",
)

GITHUB_USERNAME = APPLICANT["github_username"]
REPO_NAME = JOB["repo_name"]
REPO_URL = f"https://github.com/{GITHUB_USERNAME}/{REPO_NAME}"
APPLICATION_URL = JOB["application_url"]

APPLICANT.setdefault("github", f"https://github.com/{GITHUB_USERNAME}")
APPLICANT.setdefault("portfolio", REPO_URL)

RESUME_PATH = BASE_DIR / APPLICANT["resume_filename"]
OUTPUT_DIR = BASE_DIR / "output"
SCREENSHOTS_DIR = OUTPUT_DIR / "screenshots"
COVER_LETTER_PATH = OUTPUT_DIR / "cover_letter.pdf"
GIF_PATH = OUTPUT_DIR / "application_recording.gif"
LOG_PATH = OUTPUT_DIR / "run_log.json"

VIEWPORT = {"width": 1280, "height": 900}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

run_log = {
    "start_time": None,
    "end_time": None,
    "api_calls": [],
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "total_cost_usd": 0.0,
    "steps": [],
    "dry_run": False,
}


def log_api_call(purpose, input_tokens, output_tokens):
    cost = (input_tokens * 3.0 / 1_000_000) + (output_tokens * 15.0 / 1_000_000)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "purpose": purpose,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 4),
    }
    run_log["api_calls"].append(entry)
    run_log["total_input_tokens"] += input_tokens
    run_log["total_output_tokens"] += output_tokens
    run_log["total_cost_usd"] = round(run_log["total_cost_usd"] + cost, 4)
    print(f"  [API] {purpose}: {input_tokens}in/{output_tokens}out (${cost:.4f})")


def log_step(description, screenshot_path=None):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "description": description,
        "screenshot": str(screenshot_path) if screenshot_path else None,
    }
    run_log["steps"].append(entry)
    print(f"  [STEP] {description}")


def save_log():
    with open(LOG_PATH, "w") as f:
        json.dump(run_log, f, indent=2)


# ---------------------------------------------------------------------------
# Phase 1: Resume Parsing
# ---------------------------------------------------------------------------


def parse_resume() -> str:
    print("\n📄 Phase 1: Parsing resume...")
    doc = fitz.open(str(RESUME_PATH))
    text = ""
    for page in doc:
        text += page.get_text()
    page_count = len(doc)
    doc.close()
    print(f"  Extracted {len(text)} characters from {page_count} pages")
    return text


# ---------------------------------------------------------------------------
# Phase 2: GitHub Repo Bootstrap
# ---------------------------------------------------------------------------


def bootstrap_github_repo():
    print("\n🐙 Phase 2: Bootstrapping GitHub repo...")
    from github import Github, GithubException

    g = Github(GITHUB_TOKEN)
    user = g.get_user()

    # Check if repo already exists
    try:
        repo = user.get_repo(REPO_NAME)
        print(f"  Repo already exists: {REPO_URL}")
    except GithubException:
        repo = user.create_repo(
            REPO_NAME,
            description=(
                f"I applied to {JOB['company']} using only AI. "
                "This repo documents the process."
            ),
            auto_init=False,
        )
        print(f"  Created repo: {REPO_URL}")

    # Clone locally if not already cloned
    repo_dir = BASE_DIR / REPO_NAME
    if not repo_dir.exists():
        clone_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{REPO_NAME}.git"
        subprocess.run(
            ["git", "clone", clone_url, str(repo_dir)],
            capture_output=True,
            text=True,
        )

    # Ensure there's at least one commit (needed if repo was created without auto_init)
    readme_path = repo_dir / "README.md"
    if not readme_path.exists():
        placeholder_readme = (
            "# This repo is being built by an AI agent right now.\n\n"
            "Check back in an hour for the full story.\n"
        )
        readme_path.write_text(placeholder_readme)

        # Configure git user for this repo
        subprocess.run(
            ["git", "config", "user.email", APPLICANT["email"]],
            capture_output=True, text=True, cwd=str(repo_dir),
        )
        subprocess.run(
            ["git", "config", "user.name", APPLICANT["name"]],
            capture_output=True, text=True, cwd=str(repo_dir),
        )

        for cmd in [
            ["git", "add", "."],
            ["git", "commit", "-m", "Initial placeholder - agent is running"],
            ["git", "branch", "-M", "main"],
            ["git", "push", "-u", "origin", "main"],
        ]:
            subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_dir))

    print(f"  Repo ready: {REPO_URL}")
    return REPO_URL


# ---------------------------------------------------------------------------
# Phase 3: Cover Letter Generation
# ---------------------------------------------------------------------------


def generate_cover_letter(client: anthropic.Anthropic, resume_text: str) -> str:
    print("\n✉️  Phase 3: Generating cover letter...")

    company = JOB["company"]
    role = JOB["role_title"]
    location = JOB["location"]
    challenger = JOB.get("challenger_title", "hiring team")
    greeting = JOB.get("hiring_team_greeting", f"Dear {company} Hiring Team,")
    narrative_hook = JOB.get(
        "narrative_hook",
        f"{company}'s {challenger} challenged applicants to apply to the {role} "
        "role using only AI for a chance to skip to the final round",
    )

    prompt = f"""Write a cover letter for {APPLICANT['name']} applying to the {role} role at {company} in {location}.

CRITICAL CONTEXT: This cover letter is being generated by an AI agent that the applicant built. The same agent that writes this letter also:
- Parsed the resume from a PDF
- Created a GitHub repository to document the process
- Will fill out the ATS application form using Claude's vision API
- Will record the entire process as a GIF

NARRATIVE HOOK (the reason this AI-driven application is appropriate):
{narrative_hook}

The GitHub repo documenting this process is at: {REPO_URL}

JOB DESCRIPTION:
{JOB['job_description']}

RESUME TEXT (this is your source of truth for the applicant's background — do NOT invent facts not present here):
{resume_text}

INSTRUCTIONS:
1. Open with a hook that acknowledges the meta-nature — this letter was written by AI, as challenged by the {challenger}. Keep it confident, not gimmicky.
2. Highlight why the applicant fits the role. Pull specific evidence (companies, accomplishments, credentials) ONLY from the resume text above. Do not fabricate.
3. Connect the application itself to the role: this agent IS an AI-powered operational workflow — it handles ambiguity (unknown form fields), integrates multiple APIs, and produces auditable output.
4. Include the GitHub repo link naturally.
5. Close with confidence — forward-looking, not begging.

TONE: Professional, slightly playful, self-aware. The reader is the {company} hiring team who explicitly invited this approach.

FORMAT: Plain text paragraphs. No bullet points. Keep it under 400 words. Do not include a header/address block — just the body text starting with "{greeting}".
"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    log_api_call(
        "cover_letter_generation",
        response.usage.input_tokens,
        response.usage.output_tokens,
    )

    letter_text = response.content[0].text
    print(f"  Generated {len(letter_text)} character cover letter")
    return letter_text


def _latin1_safe(text: str) -> str:
    replacements = {
        "—": "--",
        "–": "-",
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "…": "...",
        " ": " ",
        "•": "*",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", "replace").decode("latin-1")


_URL_PATTERN = re.compile(r"(https?://[^\s)]+)")


_URL_TRAIL_PUNCT = ".,;:!?\"')]}>"


def _split_url_and_trailing(raw: str) -> tuple[str, str]:
    """Strip trailing punctuation / em-dash from URL; return (url, trailing)."""
    trailing = ""
    while raw and raw[-1] in _URL_TRAIL_PUNCT:
        trailing = raw[-1] + trailing
        raw = raw[:-1]
    if raw.endswith("--"):
        trailing = "--" + trailing
        raw = raw[:-2]
    return raw, trailing


def _write_paragraph_with_links(pdf, paragraph: str, line_height: float = 6.0):
    """Render a paragraph with auto-wrap, turning URLs into clickable blue links."""
    parts = _URL_PATTERN.split(paragraph)
    for part in parts:
        if not part:
            continue
        if _URL_PATTERN.match(part):
            url, trailing = _split_url_and_trailing(part)
            pdf.set_text_color(0, 0, 200)
            pdf.set_font("Helvetica", "U", size=11)
            pdf.write(line_height, url, link=url)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Helvetica", "", size=11)
            if trailing:
                pdf.write(line_height, trailing)
        else:
            pdf.write(line_height, part)
    pdf.ln(line_height + 4)


def render_cover_letter_pdf(letter_text: str):
    print("  Rendering cover letter to PDF...")
    letter_text = _latin1_safe(letter_text)
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.set_font("Helvetica", size=11)

    header_name = _latin1_safe(APPLICANT["name"])
    header_meta_parts = [APPLICANT.get("email", ""), APPLICANT.get("phone", "")]
    city = APPLICANT.get("city", "")
    province = APPLICANT.get("province", "")
    if city and province:
        header_meta_parts.append(f"{city}, {province}")
    elif city:
        header_meta_parts.append(city)
    header_meta = _latin1_safe(" | ".join(p for p in header_meta_parts if p))

    pdf.set_font("Helvetica", "B", size=14)
    pdf.cell(0, 10, header_name, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", size=9)
    pdf.cell(0, 5, header_meta, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(10)

    pdf.set_font("Helvetica", "", size=11)
    for paragraph in letter_text.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        _write_paragraph_with_links(pdf, paragraph)

    pdf.output(str(COVER_LETTER_PATH))
    print(f"  Saved to {COVER_LETTER_PATH}")


# ---------------------------------------------------------------------------
# Phase 4: Vision-Based Agentic Form Filling
# ---------------------------------------------------------------------------

FORM_TOOLS = [
    {
        "name": "click",
        "description": "Click at specific pixel coordinates on the page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X pixel coordinate"},
                "y": {"type": "integer", "description": "Y pixel coordinate"},
                "reason": {
                    "type": "string",
                    "description": "What you are clicking and why",
                },
            },
            "required": ["x", "y", "reason"],
        },
    },
    {
        "name": "type_text",
        "description": "Type text into the currently focused input field. Click the field first if it is not focused.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text to type"},
                "reason": {"type": "string", "description": "Which field this fills"},
            },
            "required": ["text", "reason"],
        },
    },
    {
        "name": "clear_and_type",
        "description": "Select all text in the focused field, delete it, then type new text. Use when a field has pre-filled or incorrect content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The new text to type"},
                "reason": {"type": "string", "description": "Which field this fills"},
            },
            "required": ["text", "reason"],
        },
    },
    {
        "name": "select_dropdown",
        "description": "Click a dropdown to open it, then click the desired option. Call this AFTER clicking the dropdown open — provide coordinates of the option to select.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {
                    "type": "integer",
                    "description": "X coordinate of the option",
                },
                "y": {
                    "type": "integer",
                    "description": "Y coordinate of the option",
                },
                "option_text": {
                    "type": "string",
                    "description": "Text of the option to select",
                },
            },
            "required": ["x", "y", "option_text"],
        },
    },
    {
        "name": "upload_file",
        "description": "Upload a file (resume or cover letter) to a file input. Click the upload area first, then call this.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_type": {
                    "type": "string",
                    "enum": ["resume", "cover_letter"],
                    "description": "Which file to upload",
                },
            },
            "required": ["file_type"],
        },
    },
    {
        "name": "scroll",
        "description": "Scroll the page to see more content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                },
                "pixels": {
                    "type": "integer",
                    "description": "Number of pixels to scroll (default 400)",
                },
            },
            "required": ["direction"],
        },
    },
    {
        "name": "press_key",
        "description": "Press a keyboard key (e.g. Tab, Enter, Escape, Backspace).",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key name to press"},
            },
            "required": ["key"],
        },
    },
    {
        "name": "wait",
        "description": "Wait for the page to update (e.g., after clicking a button or uploading a file).",
        "input_schema": {
            "type": "object",
            "properties": {
                "seconds": {
                    "type": "number",
                    "description": "Seconds to wait (max 5)",
                },
            },
            "required": ["seconds"],
        },
    },
    {
        "name": "done",
        "description": "Signal that the form has been fully submitted and you see a confirmation page, OR that you've encountered something requiring human intervention (CAPTCHA, error).",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["submitted", "needs_human", "error"],
                },
                "message": {
                    "type": "string",
                    "description": "Description of the current state",
                },
            },
            "required": ["status", "message"],
        },
    },
]

def _extract_turnstile_sitekey(page) -> "str | None":
    """Find the Cloudflare Turnstile sitekey on the page, if present."""
    locator = page.locator("[data-sitekey]").first
    if locator.count() == 0:
        return None
    return locator.get_attribute("data-sitekey")

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
        "cost_usd": TWOCAPTCHA_TURNSTILE_COST_USD,
    })
    run_log["total_cost_usd"] = round(run_log["total_cost_usd"] + TWOCAPTCHA_TURNSTILE_COST_USD, 4)
    return True

def _build_form_fill_system(resume_text: str) -> str:
    return f"""You are an AI agent filling out a job application form on behalf of an applicant.
You can see a screenshot of the current browser page. Your job is to identify form fields, look up the correct answer in the reference material below, and fill them accurately.

APPLICANT REFERENCE DATA (JSON — your primary source for basic identity fields like name, email, phone, address, work authorization, current role):
{json.dumps(APPLICANT, indent=2)}

RESUME TEXT (your source of truth for work history, education, skills, accomplishments, and any field asking about background):
{resume_text}

ROLE CONTEXT:
- Company: {JOB['company']}
- Role: {JOB['role_title']}
- Location: {JOB['location']}

FILES AVAILABLE FOR UPLOAD (use the upload_file tool with these file_type values):
- "resume" — the applicant's resume PDF ({APPLICANT.get('resume_filename', 'resume.pdf')})
- "cover_letter" — the AI-generated cover letter (cover_letter.pdf)

HOW TO ANSWER FIELDS:
- For each form field, FIRST identify what it is asking for from the screenshot.
- THEN look up the answer:
  - Identity / contact / authorization fields → APPLICANT JSON above.
  - Experience / education / skills / past employers / accomplishments → RESUME TEXT above.
  - Role-targeting fields (e.g. "which position?") → ROLE CONTEXT above.
  - Voluntary disclosure / EEO fields (gender, ethnicity, race, veteran status, disability status, pronouns) → use APPLICANT.eeo_responses if present, otherwise select the option closest to "Prefer not to answer" / "Decline to disclose" / "I don't wish to answer". NEVER guess these from the resume.
  - Consent / opt-in fields (SMS updates, marketing emails, "I agree to terms", privacy policy, application status updates) → use APPLICANT.consent_responses if present, with these defaults if a specific field isn't listed:
      * SMS / text-message updates → DECLINE / select "No" (privacy-preserving default)
      * Marketing / promotional email → DECLINE / select "No"
      * Application status updates → ACCEPT / select "Yes" (applicant wants to hear back)
      * Required terms-of-service / privacy-policy / "I confirm the information is accurate" → ACCEPT / check the box (otherwise the form cannot be submitted)
- If a field has no obvious match in any reference material, choose the safest reasonable answer from what IS present. Do NOT invent facts about the applicant that aren't in the resume or applicant data.
- For free-form "Why this company?" or "Why this role?" boxes, draw on the resume + role context to write a brief, honest answer.

FILE UPLOAD RULES (important — past runs got stuck here):
- The form has separate inputs for resume and cover letter. Each upload_file call routes correctly based on the file_type argument.
- Upload each file EXACTLY ONCE. Do not re-upload to "fix" what looks wrong in a screenshot — the screenshots are slow to refresh.
- After calling upload_file once for "resume" and once for "cover_letter", consider the upload section done and MOVE ON, even if the previewed filename looks confusing. Trust the tool calls succeeded.

RULES:
1. Examine the screenshot carefully. Describe what you see before acting.
2. Perform ONE logical action per turn (e.g., click a field, then type in the next turn — or click and type if the field is clearly ready).
3. For dropdowns: first click to open, wait for the next screenshot, then select the option.
4. For file uploads: click the upload button/area, then use the upload_file tool. See FILE UPLOAD RULES above.
5. CAPTCHA HANDLING — If you see a Cloudflare Turnstile widget, "Verify you are human" checkbox, reCAPTCHA, or any human-verification challenge:
   a. CLICK THE CHECKBOX directly at its center coordinates. The browser has been patched to look human; clicking the checkbox is what Turnstile needs to trigger its (invisible) verification check.
   b. IMMEDIATELY after the click, call `wait` with seconds=8. Turnstile runs verification invisibly during this wait — DO NOT re-click or panic if no visible change happens for 5-10 seconds.
   c. On the next turn, look at the new screenshot:
      - If the checkbox now shows a green checkmark, the page has progressed, OR a confirmation message appears → continue toward Submit / confirmation.
      - If the page shows a "verification failed" message or the checkbox is still empty after the wait → call wait again with seconds=5, then re-check.
   d. Repeat the wait/check cycle up to 3 times if needed.
   e. ONLY after 3 full cycles where the CAPTCHA still blocks progress should you call done with status "needs_human".
   f. If you see a confirmation page ("Application submitted", "Thank you", "We've received your application", "Application sent", etc.) call done with status "submitted".
6. When all fields are filled and you see a Submit/Apply button, click it (unless in dry-run mode — I will tell you if dry-run is active).
7. After submission, if you see a confirmation page, call done with status "submitted".
8. If a field is already filled correctly, skip it. Do not re-fill or re-upload already-completed fields.
9. Be precise with coordinates — click the CENTER of input fields and buttons.
10. If you need to see more of the page, use the scroll tool.
11. Make forward progress. Don't loop back to re-check fields you've already completed — fill from top to bottom and only revisit if you hit a validation error after attempting Submit.
12. CRITICAL: Before declaring "done", scroll all the way to the bottom of the form and confirm the Submit / Apply button is ENABLED (not grayed out). A grayed-out Apply button means a required field is still unanswered — usually a consent radio, terms checkbox, or skipped dropdown further down. Find it, fill it, then verify Apply is enabled. Only THEN click Submit (or in dry-run mode, call done with status "submitted").
13. Required radio groups (e.g. "Yes / No - I consent to receiving text messages") MUST have one option selected. If neither is selected, the form won't submit. Use the consent rules above to pick the correct option.
"""


def take_screenshot(page, step_num: int) -> tuple[str, Path]:
    path = SCREENSHOTS_DIR / f"step_{step_num:03d}.png"
    page.screenshot(path=str(path))
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return b64, path


def execute_tool(page, tool_name: str, tool_input: dict, dry_run: bool) -> str:
    if tool_name == "click":
        page.mouse.click(tool_input["x"], tool_input["y"])
        time.sleep(0.5)
        return f"Clicked ({tool_input['x']}, {tool_input['y']}): {tool_input.get('reason', '')}"

    elif tool_name == "type_text":
        page.keyboard.type(tool_input["text"], delay=30)
        time.sleep(0.3)
        return f"Typed: {tool_input['text'][:50]}..."

    elif tool_name == "clear_and_type":
        page.keyboard.press("Meta+a")
        time.sleep(0.1)
        page.keyboard.press("Backspace")
        time.sleep(0.1)
        page.keyboard.type(tool_input["text"], delay=30)
        time.sleep(0.3)
        return f"Cleared and typed: {tool_input['text'][:50]}..."

    elif tool_name == "select_dropdown":
        page.mouse.click(tool_input["x"], tool_input["y"])
        time.sleep(0.5)
        return f"Selected dropdown option: {tool_input.get('option_text', '')}"

    elif tool_name == "upload_file":
        file_type = tool_input["file_type"]
        file_path = (
            str(RESUME_PATH) if file_type == "resume" else str(COVER_LETTER_PATH)
        )
        file_inputs = page.query_selector_all('input[type="file"]')
        if file_inputs:
            # Route by file_type — most ATS forms list resume first, cover
            # letter second. Using [-1] for everything sent both files to
            # whichever input came last in the DOM (the cover-letter slot).
            if file_type == "resume":
                target = file_inputs[0]
                slot = "first"
            else:
                target = file_inputs[-1] if len(file_inputs) > 1 else file_inputs[0]
                slot = "last" if len(file_inputs) > 1 else "first"
            target.set_input_files(file_path)
            time.sleep(1)
            return (
                f"Uploaded {file_type} to {slot} file input "
                f"({len(file_inputs)} file inputs present): {file_path}"
            )
        else:
            try:
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    page.mouse.click(
                        VIEWPORT["width"] // 2, VIEWPORT["height"] // 2
                    )
                file_chooser = fc_info.value
                file_chooser.set_files(file_path)
                time.sleep(1)
                return f"Uploaded {file_type} via file chooser"
            except Exception as e:
                return f"Failed to upload {file_type}: {e}"

    elif tool_name == "scroll":
        direction = tool_input["direction"]
        pixels = tool_input.get("pixels", 400)
        delta = pixels if direction == "down" else -pixels
        page.mouse.wheel(0, delta)
        time.sleep(0.5)
        return f"Scrolled {direction} {pixels}px"

    elif tool_name == "press_key":
        page.keyboard.press(tool_input["key"])
        time.sleep(0.3)
        return f"Pressed key: {tool_input['key']}"

    elif tool_name == "wait":
        seconds = min(tool_input.get("seconds", 2), 5)
        time.sleep(seconds)
        return f"Waited {seconds}s"

    elif tool_name == "done":
        return f"DONE: [{tool_input['status']}] {tool_input['message']}"

    return f"Unknown tool: {tool_name}"


def fill_form(client: anthropic.Anthropic, resume_text: str, dry_run: bool) -> str:
    print("\n🌐 Phase 4: Filling application form...")
    if dry_run:
        print("  ⚠️  DRY RUN MODE — will not click Submit")

    form_fill_system = _build_form_fill_system(resume_text)
    done_status: str = "max_steps_reached"

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
        # Patch ~15 fingerprint vectors Cloudflare Turnstile inspects
        # (navigator.plugins/languages, canvas/WebGL hash, permissions API,
        # chrome runtime, navigator.webdriver, etc.).
        Stealth().apply_stealth_sync(context)
        page = context.new_page()

        print(f"  Navigating to {APPLICATION_URL}")
        page.goto(APPLICATION_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        step = 0
        max_steps = 80
        messages = []
        done = False

        while step < max_steps and not done:
            step += 1
            print(f"\n  --- Step {step} ---")

            screenshot_b64, screenshot_path = take_screenshot(page, step)

            # Auto-solve Cloudflare Turnstile so the agent never has to handle it
            if _extract_turnstile_sitekey(page):
                solved = solve_turnstile_if_present(page)
                if solved:
                    # Give Cloudflare's callback a moment, then re-screenshot
                    page.wait_for_timeout(3000)
                    screenshot_b64, screenshot_path = take_screenshot(page, step)

            dry_run_note = ""
            if dry_run:
                dry_run_note = (
                    "\n\nDRY RUN MODE IS ACTIVE. When you would click Submit/Apply, "
                    "instead call done with status 'submitted' and message 'Dry run complete — "
                    "form is filled and ready for real submission'. Do NOT actually click Submit."
                )

            user_message = {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": screenshot_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": f"Step {step}. Look at this screenshot and decide what to do next. "
                        f"Describe what you see, then use a tool to take the next action.{dry_run_note}",
                    },
                ],
            }
            messages.append(user_message)

            try:
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=2048,
                    system=form_fill_system,
                    messages=messages,
                    tools=FORM_TOOLS,
                )
            except Exception as e:
                print(f"  API error: {e}")
                time.sleep(2)
                continue

            log_api_call(
                f"form_step_{step}",
                response.usage.input_tokens,
                response.usage.output_tokens,
            )

            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            tool_results = []
            for block in assistant_content:
                if block.type == "text":
                    print(f"  🤖 {block.text[:200]}")
                elif block.type == "tool_use":
                    print(f"  🔧 {block.name}({json.dumps(block.input)[:100]})")
                    result = execute_tool(page, block.name, block.input, dry_run)
                    log_step(result, screenshot_path)
                    print(f"  ✅ {result}")

                    if block.name == "done":
                        done = True
                        done_status = block.input.get("status", "submitted")

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )

            if tool_results and not done:
                messages.append({"role": "user", "content": tool_results})

            # Keep conversation manageable — only keep last 10 exchanges
            if len(messages) > 20:
                messages = messages[-20:]

        if not done:
            print(f"  ⚠️  Reached max steps ({max_steps}) without completion")

        # Human fallback: if the agent gave up on CAPTCHA, keep the browser
        # open so Maury can click the checkbox himself, then re-check the
        # page state to see if submission actually completed.
        if done_status == "needs_human" and not dry_run:
            print(
                "\n  ⚠️  Agent could not pass the CAPTCHA on its own.\n"
                "  ⏳ The browser will stay OPEN for 90 seconds.\n"
                "  👉 Solve the CAPTCHA in the browser window now.\n"
                "  The script will re-check the page state when the window closes."
            )
            time.sleep(90)

            print("\n  Re-checking final page state...")
            final_b64, final_path = take_screenshot(page, step + 1)
            log_step("Final state after human-fallback window", final_path)
            done_status = _verify_submission(client, final_b64)
        else:
            take_screenshot(page, step + 1)

        print("  Closing browser...")
        context.close()
        browser.close()

    return done_status


def _verify_submission(client: anthropic.Anthropic, screenshot_b64: str) -> str:
    """Ask Claude whether the screenshot shows a successful submission."""
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=64,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Look at this screenshot of a job application page. "
                                "Did the application submit successfully? Look for "
                                "confirmation text like 'Application submitted', "
                                "'Thank you', 'We received your application', "
                                "'Application sent', or similar success messaging. "
                                "Respond with EXACTLY ONE of these two words and "
                                "nothing else: submitted OR not_submitted"
                            ),
                        },
                    ],
                }
            ],
        )
        log_api_call(
            "captcha_recheck",
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        verdict = response.content[0].text.strip().lower()
        if verdict.startswith("submitted"):
            print("  ✅ Confirmation detected — application appears submitted.")
            return "submitted"
        print(f"  ✗ No confirmation detected (verdict: {verdict[:80]!r})")
    except Exception as e:
        print(f"  Could not verify final state: {e}")
    return "needs_human"


# ---------------------------------------------------------------------------
# Phase 5: GIF Generation
# ---------------------------------------------------------------------------


def generate_gif():
    print("\n🎬 Phase 5: Generating GIF from screenshots...")
    screenshots = sorted(SCREENSHOTS_DIR.glob("step_*.png"))
    if not screenshots:
        print("  No screenshots found, skipping GIF generation")
        return

    frames = []
    for path in screenshots:
        img = Image.open(path)
        img = img.resize((960, int(960 * img.height / img.width)), Image.LANCZOS)
        frames.append(img)

    if frames:
        durations = [1500] * len(frames)  # 1.5 seconds per frame
        frames[0].save(
            str(GIF_PATH),
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=0,
            optimize=True,
        )
        size_mb = GIF_PATH.stat().st_size / (1024 * 1024)
        print(f"  Created GIF: {GIF_PATH} ({size_mb:.1f} MB, {len(frames)} frames)")
    else:
        print("  No frames to create GIF from")


# ---------------------------------------------------------------------------
# Phase 6: Final GitHub Push
# ---------------------------------------------------------------------------

README_TEMPLATE = """# I Applied to {company} Using Only AI

{company_quote_block}When {company}'s {challenger_title} challenged applicants to apply to the {role} role
using **only AI** for a chance to skip to the final round, I took it literally.

This repo contains the agent that did it — and the proof that it worked.

## The Recording

![Application Demo](output/application_recording.gif)

## What This Agent Does

```
Resume PDF ──→ Parse ──→ Structured Data ──→ Cover Letter (Claude API)
                                                    │
                                                    ▼
GitHub Repo ←── Push ←── GIF ←── Screenshots ←── Form Fill (Playwright + Claude Vision)
     │                                                │
     └── README (this file) ──────────────────────────┘
```

1. **Parses** my resume PDF and extracts structured data
2. **Creates** this GitHub repo (solving the chicken-and-egg: the cover letter links here)
3. **Generates** a tailored, self-referential cover letter using Claude's API
4. **Opens** the ATS form in a real browser
5. **Uses Claude's vision API** to dynamically discover and fill every field
6. **Uploads** my resume and the AI-generated cover letter
7. **Records** the entire process as a GIF
8. **Pushes** everything to this repo

## Tech Stack

| Component | Tool | Purpose |
|-----------|------|---------|
| Brain | Claude API (Sonnet) | Vision-based form analysis + cover letter generation |
| Hands | Playwright | Browser automation |
| Eyes | Screenshots → Claude Vision | Dynamic form field discovery |
| Memory | PyMuPDF | Resume PDF parsing |
| Pen | fpdf2 | Cover letter PDF rendering |
| Camera | Pillow + imageio | GIF recording |

## The Cover Letter

The cover letter references this repo. This repo contains the cover letter.
The snake eats its own tail.

📄 [Read the cover letter](output/cover_letter.pdf)

## How to Run It Yourself

```bash
git clone {repo_url}
cd {repo_name}
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Set your API keys
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY and GITHUB_TOKEN

# Add your personal details (gitignored)
cp applicant.example.json applicant.json
# Edit applicant.json with your name, email, phone, etc.

# Edit job.json to point at the role you are applying to.

# Dry run (fills form without submitting)
python apply.py --dry-run

# Real run
python apply.py
```

## Cost

Total Claude API cost for this application: **${total_cost:.2f}**

| Call | Tokens In | Tokens Out | Cost |
|------|-----------|------------|------|
{cost_table}

## Why This Matters

This isn't just a job application — it's a working prototype of the kind of AI-powered
operational workflow I'd build at {company} every day.

It handles **ambiguity** (unknown form fields discovered via vision), integrates **multiple APIs**
(Claude, GitHub, Playwright), produces **auditable output** (screenshots, logs, cost tracking),
and runs **end-to-end without human intervention**.

That's the job description. This is the proof.

## Submitted

🕐 {timestamp}

---

Built with Claude API, Playwright, and a healthy appreciation for meta-humor.
"""


def update_readme_and_push():
    print("\n📝 Phase 6: Updating README and pushing to GitHub...")

    cost_rows = []
    for call in run_log["api_calls"]:
        cost_rows.append(
            f"| {call['purpose']} | {call['input_tokens']:,} | "
            f"{call['output_tokens']:,} | ${call['cost_usd']:.4f} |"
        )
    cost_table = "\n".join(cost_rows)

    company_quote = JOB.get("company_quote", "").strip()
    company_quote_block = (
        f"> {company_quote}\n\n" if company_quote else ""
    )

    readme = README_TEMPLATE.format(
        company=JOB["company"],
        role=JOB["role_title"],
        challenger_title=JOB.get("challenger_title", "hiring team"),
        company_quote_block=company_quote_block,
        repo_url=REPO_URL,
        repo_name=REPO_NAME,
        total_cost=run_log["total_cost_usd"],
        cost_table=cost_table,
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )

    repo_dir = BASE_DIR / REPO_NAME
    if not repo_dir.exists():
        clone_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{REPO_NAME}.git"
        subprocess.run(
            ["git", "clone", clone_url, str(repo_dir)],
            capture_output=True,
            text=True,
        )

    (repo_dir / "README.md").write_text(readme)

    # Copy artifacts into the repo
    output_repo = repo_dir / "output"
    output_repo.mkdir(exist_ok=True)
    screenshots_repo = output_repo / "screenshots"
    screenshots_repo.mkdir(exist_ok=True)

    import shutil

    for src in [COVER_LETTER_PATH, GIF_PATH, LOG_PATH]:
        if src.exists():
            shutil.copy2(src, output_repo / src.name)

    for src in SCREENSHOTS_DIR.glob("step_*.png"):
        shutil.copy2(src, screenshots_repo / src.name)

    # Copy source files (NEVER copy applicant.json — it contains personal data and is gitignored)
    for src_name in [
        "apply.py",
        "requirements.txt",
        ".env.example",
        ".gitignore",
        "applicant.example.json",
        "job.json",
    ]:
        src = BASE_DIR / src_name
        if src.exists():
            shutil.copy2(src, repo_dir / src_name)

    if RESUME_PATH.exists():
        shutil.copy2(RESUME_PATH, repo_dir / RESUME_PATH.name)

    for cmd in [
        ["git", "add", "."],
        [
            "git",
            "commit",
            "-m",
            "Add complete application: agent, cover letter, recording, and documentation",
        ],
        ["git", "push", "origin", "main"],
    ]:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(repo_dir)
        )
        if result.returncode != 0 and "nothing to commit" not in result.stdout:
            print(f"  Git warning: {result.stderr[:200]}")

    print(f"  Pushed to {REPO_URL}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="AI Job Application Agent")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fill form without submitting",
    )
    parser.add_argument(
        "--skip-github",
        action="store_true",
        help="Skip GitHub repo creation/push (for testing)",
    )
    parser.add_argument(
        "--skip-form",
        action="store_true",
        help="Skip form filling (for testing cover letter generation)",
    )
    args = parser.parse_args()

    run_log["start_time"] = datetime.now(timezone.utc).isoformat()
    run_log["dry_run"] = args.dry_run

    print("=" * 60)
    print(f"  AI APPLICATION AGENT — {JOB['company'].upper()}")
    print("  " + ("DRY RUN" if args.dry_run else "LIVE RUN"))
    print("=" * 60)

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set. Add it to .env")
        sys.exit(1)

    if not RESUME_PATH.exists():
        print(f"ERROR: Resume not found at {RESUME_PATH}")
        sys.exit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)
    SCREENSHOTS_DIR.mkdir(exist_ok=True)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Phase 1
    resume_text = parse_resume()

    # Phase 2
    if not args.skip_github:
        bootstrap_github_repo()

    # Phase 3
    cover_letter_text = generate_cover_letter(client, resume_text)
    render_cover_letter_pdf(cover_letter_text)

    # Phase 4
    form_status = "skipped"
    if not args.skip_form:
        form_status = fill_form(client, resume_text, dry_run=args.dry_run)
        run_log["form_fill_status"] = form_status

    # Phase 5
    generate_gif()

    # Phase 6
    run_log["end_time"] = datetime.now(timezone.utc).isoformat()
    save_log()

    push_ok = (
        args.skip_form
        or args.dry_run
        or form_status == "submitted"
    )
    if not args.skip_github:
        if push_ok:
            update_readme_and_push()
        else:
            print(
                f"\n⚠️  Skipping GitHub push because form submission did not complete "
                f"(status: {form_status}).\n"
                f"   Complete the application in the browser, then re-run to push artifacts."
            )

    print("\n" + "=" * 60)
    print("  COMPLETE!")
    print(f"  Total API cost: ${run_log['total_cost_usd']:.2f}")
    print(f"  Total API calls: {len(run_log['api_calls'])}")
    print(f"  Screenshots: {len(list(SCREENSHOTS_DIR.glob('step_*.png')))}")
    print(f"  Cover letter: {COVER_LETTER_PATH}")
    print(f"  GIF: {GIF_PATH}")
    print(f"  Log: {LOG_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
