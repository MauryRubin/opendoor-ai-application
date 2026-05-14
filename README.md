# I Applied to Opendoor Using Only AI

When Opendoor's CEO challenged applicants to apply to the Operations AI Engineer role
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
git clone https://github.com/MauryRubin/opendoor-ai-application
cd opendoor-ai-application
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

Total Claude API cost for this application: **$1.74**

| Call | Tokens In | Tokens Out | Cost |
|------|-----------|------------|------|
| cover_letter_generation | 2,141 | 515 | $0.0141 |
| form_step_1 | 5,854 | 299 | $0.0220 |
| form_step_2 | 7,745 | 87 | $0.0245 |
| form_step_3 | 9,442 | 159 | $0.0307 |
| form_step_4 | 11,176 | 292 | $0.0379 |
| form_step_5 | 13,058 | 240 | $0.0428 |
| form_step_6 | 14,876 | 261 | $0.0485 |
| form_step_7 | 16,714 | 308 | $0.0548 |
| form_step_8 | 17,068 | 131 | $0.0532 |
| form_step_9 | 16,898 | 177 | $0.0533 |
| form_step_10 | 16,969 | 109 | $0.0525 |
| form_step_11 | 16,952 | 295 | $0.0553 |
| form_step_12 | 16,942 | 258 | $0.0547 |
| form_step_13 | 16,959 | 259 | $0.0548 |
| form_step_14 | 16,974 | 179 | $0.0536 |
| form_step_15 | 16,834 | 207 | $0.0536 |
| form_step_16 | 16,915 | 203 | $0.0538 |
| form_step_17 | 16,929 | 213 | $0.0540 |
| form_step_18 | 17,022 | 175 | $0.0537 |
| form_step_19 | 16,904 | 228 | $0.0541 |
| form_step_20 | 16,874 | 253 | $0.0544 |
| form_step_21 | 16,851 | 283 | $0.0548 |
| form_step_22 | 16,973 | 203 | $0.0540 |
| form_step_23 | 16,953 | 217 | $0.0541 |
| form_step_24 | 16,965 | 227 | $0.0543 |
| form_step_25 | 16,959 | 205 | $0.0540 |
| form_step_26 | 16,987 | 231 | $0.0544 |
| form_step_27 | 16,990 | 255 | $0.0548 |
| form_step_28 | 17,012 | 208 | $0.0542 |
| form_step_29 | 16,920 | 231 | $0.0542 |
| form_step_30 | 16,946 | 270 | $0.0549 |
| form_step_31 | 17,023 | 206 | $0.0542 |
| form_step_32 | 17,002 | 324 | $0.0559 |
| form_step_33 | 17,134 | 175 | $0.0540 |
| form_step_34 | 17,076 | 227 | $0.0546 |

## Why This Matters

This isn't just a job application — it's a working prototype of the kind of AI-powered
operational workflow I'd build at Opendoor every day.

It handles **ambiguity** (unknown form fields discovered via vision), integrates **multiple APIs**
(Claude, GitHub, Playwright), produces **auditable output** (screenshots, logs, cost tracking),
and runs **end-to-end without human intervention**.

That's the job description. This is the proof.

## Submitted

🕐 2026-05-14 02:12 UTC

---

Built with Claude API, Playwright, and a healthy appreciation for meta-humor.
