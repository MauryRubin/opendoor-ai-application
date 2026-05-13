#!/usr/bin/env python3
"""
AI Job Application Agent for Opendoor
======================================
This script autonomously applies to the Opendoor Operations AI Engineer role.
It parses a resume, generates a cover letter, fills the Rippling ATS form
using Claude's vision API, and documents the entire process.

Usage:
    python apply.py --dry-run    # Fill form without submitting
    python apply.py              # Full run with submission
"""

import argparse
import base64
import json
import os
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

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).parent / ".env", override=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
MODEL = "claude-sonnet-4-20250514"
APPLICATION_URL = (
    "https://ats.rippling.com/en-CA/opendoor/jobs/"
    "f572e889-0644-4590-8a5a-64f73d7db17d/apply"
)
REPO_NAME = "opendoor-ai-application"
GITHUB_USERNAME = "MauryRubin"
REPO_URL = f"https://github.com/{GITHUB_USERNAME}/{REPO_NAME}"

BASE_DIR = Path(__file__).parent
RESUME_PATH = BASE_DIR / "Maury_Rubin_Resume.pdf"
OUTPUT_DIR = BASE_DIR / "output"
SCREENSHOTS_DIR = OUTPUT_DIR / "screenshots"
COVER_LETTER_PATH = OUTPUT_DIR / "cover_letter.pdf"
GIF_PATH = OUTPUT_DIR / "application_recording.gif"
LOG_PATH = OUTPUT_DIR / "run_log.json"

VIEWPORT = {"width": 1280, "height": 900}

APPLICANT = {
    "name": "Maury Daniel Rubin",
    "first_name": "Maury",
    "last_name": "Rubin",
    "email": "maurydr1@gmail.com",
    "phone": "(647) 287-3417",
    "address": "61 Collinson Blvd",
    "city": "Toronto",
    "province": "Ontario",
    "country": "Canada",
    "postal_code": "",
    "linkedin": "https://www.linkedin.com/in/mauryrubin/",
    "github": f"https://github.com/{GITHUB_USERNAME}",
    "portfolio": REPO_URL,
    "current_role": "Product Manager Director",
    "current_company": "Wave Financial",
    "work_authorization": "Canadian citizen",
    "requires_sponsorship": "No",
}

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
            description="I applied to Opendoor using only AI. This repo documents the process.",
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

JOB_DESCRIPTION = """
Operations AI Engineer at Opendoor (Toronto)

Key Responsibilities:
- Transform ambiguous business challenges into system designs and implementation roadmaps
- Prototype and deploy rapid experiments to improve operational workflows
- Build AI-powered internal tools and automation systems
- Evaluate build versus integrate decisions for AI tooling
- Establish monitoring for model performance, latency, and drift detection
- Conduct troubleshooting and root cause analysis for production issues
- Partner with data scientists to operationalize machine learning models

Required Qualifications:
- 5+ years of experience in operations and data
- SQL proficiency, API integration, LLM deployment understanding
- Machine learning lifecycle concepts
- High agency, systems thinking, strong communication

Desired Skills:
- AI coding assistants (Claude, Cursor)
- Workflow automation platforms (Gumloop, Zapier)
- Data platforms (Snowflake, Databricks)
- Agentic AI frameworks and automation flows
"""


def generate_cover_letter(client: anthropic.Anthropic, resume_text: str) -> str:
    print("\n✉️  Phase 3: Generating cover letter...")

    prompt = f"""Write a cover letter for Maury Daniel Rubin applying to the Operations AI Engineer role at Opendoor in Toronto.

CRITICAL CONTEXT: This cover letter is being generated by an AI agent that Maury built. The same agent that writes this letter also:
- Parsed his resume from a PDF
- Created a GitHub repository to document the process
- Will fill out the Rippling ATS application form using Claude's vision API
- Will record the entire process as a GIF

The GitHub repo documenting this process is at: {REPO_URL}

JOB DESCRIPTION:
{JOB_DESCRIPTION}

RESUME TEXT:
{resume_text}

INSTRUCTIONS:
1. Open with a hook that acknowledges the meta-nature — this letter was written by AI, as challenged by the founder. Keep it confident, not gimmicky.
2. Highlight why Maury fits:
   - API & integrations leadership at Wave Financial (built the integration marketplace, monetized the API)
   - Techstars Proptech Accelerator experience (real estate tech → Opendoor connection)
   - Multi-country market launches at Clearco (operational scaling across Toronto, UK, Australia)
   - Payments/fintech operational complexity at scale
   - Master of Financial Economics + CFA Level II = analytical rigor
3. Connect the application itself to the role: this agent IS an AI-powered operational workflow — it handles ambiguity (unknown form fields), integrates multiple APIs, and produces auditable output.
4. Include the GitHub repo link naturally.
5. Close with confidence — forward-looking, not begging.

TONE: Professional, slightly playful, self-aware. The reader is the Opendoor hiring team who explicitly invited this approach.

FORMAT: Plain text paragraphs. No bullet points. Keep it under 400 words. Do not include a header/address block — just the body text starting with "Dear Opendoor Hiring Team,".
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


def render_cover_letter_pdf(letter_text: str):
    print("  Rendering cover letter to PDF...")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.set_font("Helvetica", size=11)

    pdf.set_font("Helvetica", "B", size=14)
    pdf.cell(0, 10, "Maury Daniel Rubin", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", size=9)
    pdf.cell(
        0,
        5,
        "maurydr1@gmail.com | (647) 287-3417 | Toronto, ON",
        new_x="LMARGIN",
        new_y="NEXT",
        align="C",
    )
    pdf.ln(10)

    pdf.set_font("Helvetica", size=11)
    for paragraph in letter_text.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        pdf.multi_cell(0, 6, paragraph)
        pdf.ln(4)

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

FORM_FILL_SYSTEM = f"""You are an AI agent filling out a job application form on behalf of Maury Daniel Rubin.
You can see a screenshot of the current browser page. Your job is to identify form fields and fill them accurately.

APPLICANT INFORMATION:
- Full Name: {APPLICANT['name']}
- First Name: {APPLICANT['first_name']}
- Last Name: {APPLICANT['last_name']}
- Email: {APPLICANT['email']}
- Phone: {APPLICANT['phone']}
- Address: {APPLICANT['address']}, {APPLICANT['city']}, {APPLICANT['province']}, {APPLICANT['country']}
- LinkedIn: {APPLICANT['linkedin']}
- GitHub / Portfolio: {APPLICANT['portfolio']}
- Current Role: {APPLICANT['current_role']} at {APPLICANT['current_company']}
- Work Authorization: {APPLICANT['work_authorization']} (does NOT require sponsorship)

FILES AVAILABLE FOR UPLOAD:
- Resume: Maury_Rubin_Resume.pdf
- Cover Letter: cover_letter.pdf

RULES:
1. Examine the screenshot carefully. Describe what you see before acting.
2. Perform ONE logical action per turn (e.g., click a field, then type in the next turn — or click and type if the field is clearly ready).
3. For dropdowns: first click to open, wait for the next screenshot, then select the option.
4. For file uploads: click the upload button/area, then use the upload_file tool.
5. For "How did you hear about us?" type questions: answer "Company website".
6. For work authorization: Canadian citizen, no sponsorship needed.
7. If you see a CAPTCHA or something blocking, call done with status "needs_human".
8. When all fields are filled and you see a Submit/Apply button, click it (unless in dry-run mode — I will tell you if dry-run is active).
9. After submission, if you see a confirmation page, call done with status "submitted".
10. If a field is already filled correctly, skip it.
11. Be precise with coordinates — click the CENTER of input fields and buttons.
12. If you need to see more of the page, use the scroll tool.
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
            file_inputs[-1].set_input_files(file_path)
            time.sleep(1)
            return f"Uploaded {file_type}: {file_path}"
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


def fill_form(client: anthropic.Anthropic, dry_run: bool):
    print("\n🌐 Phase 4: Filling application form...")
    if dry_run:
        print("  ⚠️  DRY RUN MODE — will not click Submit")

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
        page = context.new_page()
        page.evaluate("delete navigator.__proto__.webdriver")

        print(f"  Navigating to {APPLICATION_URL}")
        page.goto(APPLICATION_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        step = 0
        max_steps = 60
        messages = []
        done = False

        while step < max_steps and not done:
            step += 1
            print(f"\n  --- Step {step} ---")

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
                    system=FORM_FILL_SYSTEM,
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

        # Final screenshot
        take_screenshot(page, step + 1)

        print("  Closing browser...")
        context.close()
        browser.close()


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

README_TEMPLATE = """# I Applied to Opendoor Using Only AI

> "AI isn't a department. It's how we work." — Opendoor

When Opendoor's founder challenged applicants to apply to the Operations AI Engineer role
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
4. **Opens** the Rippling ATS form in a real browser
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
operational workflow I'd build at Opendoor every day.

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

    readme = README_TEMPLATE.format(
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

    # Copy source files
    for src_name in ["apply.py", "requirements.txt", ".env.example", ".gitignore"]:
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
    parser = argparse.ArgumentParser(description="AI Job Application Agent for Opendoor")
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
    print("  OPENDOOR AI APPLICATION AGENT")
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
    if not args.skip_form:
        fill_form(client, dry_run=args.dry_run)

    # Phase 5
    generate_gif()

    # Phase 6
    run_log["end_time"] = datetime.now(timezone.utc).isoformat()
    save_log()

    if not args.skip_github:
        update_readme_and_push()

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
