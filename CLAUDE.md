# Opendoor AI Application Agent

## What This Project Is

A Python agent that autonomously applies to Opendoor's Operations AI Engineer role (Toronto) using only AI — as challenged by the founder. The agent parses a resume, generates a self-referential cover letter, fills the Rippling ATS form via Playwright + Claude Vision, records a GIF, and pushes everything to a public GitHub repo.

## Current Status

**The code is written and ready to test.** All files are in place. The previous session was blocked by a corporate SSL proxy (Netskope) — that's the only reason we stopped.

## Where to Pick Up

### 1. Set up the environment
```bash
cd ~/Documents/coding/opendoor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Create `.env` with fresh API keys
```bash
cp .env.example .env
# Edit .env with:
#   ANTHROPIC_API_KEY=sk-ant-...
#   GITHUB_TOKEN=ghp_...
```
The old keys from the previous session should be rotated — generate new ones at:
- Anthropic: https://console.anthropic.com/ → Settings → API Keys
- GitHub: https://github.com/settings/tokens → Generate new token (classic) with `repo` scope

### 3. Test in stages
```bash
# Stage 1: Test resume parsing + cover letter generation (no browser, no GitHub)
python apply.py --skip-form --skip-github --dry-run

# Stage 2: Test with GitHub repo creation
python apply.py --skip-form --dry-run

# Stage 3: Full dry run (fills form but doesn't submit)
python apply.py --dry-run

# Stage 4: Real submission
python apply.py
```

### 4. After submission
- Review the GitHub repo at https://github.com/MauryRubin/opendoor-ai-application
- The README, GIF, cover letter, and screenshots are pushed automatically
- Check `output/run_log.json` for the full API cost breakdown

## Key Files

| File | Purpose |
|------|---------|
| `apply.py` | The single main script — all logic lives here |
| `requirements.txt` | Python dependencies |
| `.env` | API keys (gitignored, must create) |
| `.env.example` | Template for .env |
| `Maury_Rubin_Resume.pdf` | Source resume |
| `output/` | Created at runtime — cover letter, GIF, screenshots, logs |

## Architecture

The agent runs 7 phases sequentially:
1. **Resume parsing** — PyMuPDF extracts text from the PDF
2. **GitHub repo bootstrap** — Creates public repo with placeholder README (solves chicken-and-egg with cover letter URL)
3. **Cover letter generation** — Claude API writes a self-referential cover letter, rendered to PDF via fpdf2
4. **Form filling** — Playwright opens the Rippling form; Claude Vision sees screenshots and decides what to click/type via tool use (agentic loop)
5. **GIF generation** — Screenshots stitched into an animated GIF
6. **Final GitHub push** — README with narrative, GIF, cost breakdown, and all artifacts
7. **Logging** — Every API call tracked with token counts and costs

## Applicant Details (hardcoded in apply.py)

- **Name**: Maury Daniel Rubin
- **Email**: maurydr1@gmail.com
- **Phone**: (647) 287-3417
- **GitHub**: MauryRubin
- **LinkedIn**: https://www.linkedin.com/in/mauryrubin/
- **Work auth**: Canadian citizen, no sponsorship needed

## If Something Goes Wrong

- **SSL errors**: You're probably behind a corporate proxy. Use a personal machine.
- **Form filling gets stuck**: The `--dry-run` flag stops before submit. Check `output/screenshots/` to see what the agent saw at each step.
- **CAPTCHA**: The agent will detect it and pause. Fill it manually, then re-run.
- **GitHub repo already exists**: The script handles this — it'll clone and update the existing repo.
- **Cover letter quality**: Re-run with `--skip-form --skip-github` to regenerate just the cover letter. Edit the prompt in the `generate_cover_letter` function if needed.

## Application URL

https://ats.rippling.com/en-CA/opendoor/jobs/f572e889-0644-4590-8a5a-64f73d7db17d/apply
