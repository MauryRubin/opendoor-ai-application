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

Total Claude API cost for this application: **$2.03**

| Call | Tokens In | Tokens Out | Cost |
|------|-----------|------------|------|
| cover_letter_generation | 2,141 | 491 | $0.0138 |
| form_step_1 | 6,143 | 296 | $0.0229 |
| form_step_2 | 8,029 | 95 | $0.0255 |
| form_step_3 | 9,734 | 191 | $0.0321 |
| form_step_4 | 11,514 | 269 | $0.0386 |
| form_step_5 | 13,373 | 274 | $0.0442 |
| form_step_6 | 15,253 | 223 | $0.0491 |
| form_step_7 | 17,053 | 211 | $0.0543 |
| form_step_8 | 17,309 | 127 | $0.0538 |
| form_step_9 | 17,138 | 172 | $0.0540 |
| form_step_10 | 17,196 | 88 | $0.0529 |
| form_step_11 | 17,112 | 129 | $0.0533 |
| form_step_12 | 16,959 | 152 | $0.0532 |
| form_step_13 | 16,808 | 205 | $0.0535 |
| form_step_14 | 16,800 | 167 | $0.0529 |
| form_step_15 | 16,746 | 134 | $0.0522 |
| form_step_16 | 16,752 | 192 | $0.0531 |
| form_step_17 | 16,760 | 139 | $0.0524 |
| form_step_18 | 16,792 | 164 | $0.0528 |
| form_step_19 | 16,829 | 189 | $0.0533 |
| form_step_20 | 16,866 | 144 | $0.0528 |
| form_step_21 | 16,795 | 148 | $0.0526 |
| form_step_22 | 16,786 | 182 | $0.0531 |
| form_step_23 | 16,826 | 132 | $0.0525 |
| form_step_24 | 16,764 | 142 | $0.0524 |
| form_step_25 | 16,755 | 131 | $0.0522 |
| form_step_26 | 16,720 | 196 | $0.0531 |
| form_step_27 | 16,727 | 186 | $0.0530 |
| form_step_28 | 16,781 | 188 | $0.0532 |
| form_step_29 | 16,812 | 132 | $0.0524 |
| form_step_30 | 16,760 | 185 | $0.0531 |
| form_step_31 | 16,828 | 181 | $0.0532 |
| form_step_32 | 16,867 | 257 | $0.0545 |
| form_step_33 | 17,006 | 147 | $0.0532 |
| form_step_34 | 16,955 | 185 | $0.0536 |
| form_step_35 | 16,962 | 109 | $0.0525 |
| form_step_36 | 16,878 | 145 | $0.0528 |
| form_step_37 | 16,889 | 164 | $0.0531 |
| form_step_38 | 16,867 | 106 | $0.0522 |
| form_step_39 | 16,790 | 163 | $0.0528 |
| form_step_40 | 16,698 | 278 | $0.0543 |

## Why This Matters

This isn't just a job application — it's a working prototype of the kind of AI-powered
operational workflow I'd build at Opendoor every day.

It handles **ambiguity** (unknown form fields discovered via vision), integrates **multiple APIs**
(Claude, GitHub, Playwright), produces **auditable output** (screenshots, logs, cost tracking),
and runs **end-to-end without human intervention**.

That's the job description. This is the proof.

## Submitted

🕐 2026-05-14 04:48 UTC

---

Built with Claude API, Playwright, and a healthy appreciation for meta-humor.
