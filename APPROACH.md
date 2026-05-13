# How I Approached This: Applying to Opendoor Using Only AI

## The Challenge

Opendoor's founder posted that anyone who applies to the Operations AI Engineer role using **only AI** — including filling out the forms and creating the documents — and explains how they did it, gets moved straight to final round interviews. Extra points for creativity.

I decided to take that literally.

## My Thought Process

### Step 1: Treat the application as the interview

The job is about building AI-powered operational workflows. So instead of just using ChatGPT to write a cover letter and calling it a day, I asked: what if the application itself *is* a working prototype of the kind of thing I'd build at Opendoor?

That reframing changed everything. I wasn't just applying — I was building a portfolio piece that demonstrates the exact skills the role requires.

### Step 2: Define the agent's scope

I wanted the agent to handle the entire pipeline end-to-end with zero human intervention:

1. Parse my resume from a PDF
2. Generate a tailored cover letter
3. Open the actual application form in a real browser
4. Figure out what fields exist (without hardcoding anything)
5. Fill every field, upload documents, and submit
6. Record the whole thing as a GIF
7. Push everything to a public GitHub repo

The cover letter links to the repo. The repo contains the cover letter. The snake eats its own tail.

### Step 3: Choose the right architecture

I made a few deliberate architectural decisions:

**Single file, not a framework.** The entire agent lives in one Python script (`apply.py`). This isn't because I don't know how to structure code — it's because the audience is a hiring team who will spend 2 minutes scanning this. One file is scannable. A 12-module package is not.

**Vision-based form filling, not DOM scraping.** Instead of inspecting the HTML and writing brittle CSS selectors, the agent takes a screenshot of the form and sends it to Claude's vision API. Claude sees what a human sees and decides what to click and type. This means the agent works on *any* form — not just this specific Rippling page. That's the kind of generalizable thinking an AI Ops Engineer needs.

**Playwright, not Selenium.** Modern, async-capable, built-in video recording, better file upload handling. The right tool for the job.

### Step 4: Build it with AI (meta-level)

I used Claude Code (Anthropic's AI coding assistant) to plan and build the entire agent. So even the code that applies to the job was written by AI. The layers of meta here are:

- AI wrote the agent
- The agent uses AI to fill out the form
- The agent uses AI to write the cover letter
- The cover letter explains that AI did all of this
- The repo documents the whole process

### Step 5: Solve the chicken-and-egg problem

The cover letter needs to link to the GitHub repo. But the repo needs to contain the cover letter. My solution:

1. Create the repo first with a placeholder README
2. Now the URL is known
3. Generate the cover letter with the repo URL baked in
4. Push everything to the repo after the application is submitted

Simple sequencing, but you have to think about it upfront.

### Step 6: Add observability

Every AI-powered system needs monitoring. The agent logs:

- Every Claude API call with token counts and costs
- Every action taken (clicks, keystrokes, uploads)
- Screenshots at every step
- Total runtime and cost

The README includes a cost table showing exactly what the application cost in API tokens. This demonstrates the kind of cost-awareness you need when deploying AI in production.

## Why This Approach Maps to the Role

| Job Requirement | How This Agent Demonstrates It |
|----------------|-------------------------------|
| Transform ambiguous challenges into system designs | Unknown form fields → vision-based discovery |
| Build AI-powered internal tools | This is literally an AI-powered tool |
| API integration | Claude API, GitHub API, Playwright |
| Evaluate build vs. integrate decisions | Built custom agent instead of using a no-code form filler |
| Establish monitoring for model performance | Token logging, cost tracking, screenshot audit trail |
| AI coding assistants (Claude, Cursor) | The entire project was built with Claude Code |
| Agentic AI frameworks | The form-filling loop is an agentic workflow with tool use |
| High agency | You're reading this, so it worked |

## Tech Stack

- **Python** — the agent runtime
- **Claude API (Sonnet)** — vision-based form analysis + cover letter generation
- **Playwright** — browser automation
- **PyMuPDF** — resume PDF parsing
- **fpdf2** — cover letter PDF rendering
- **Pillow** — GIF generation from screenshots
- **Claude Code** — built the entire project

## What I'd Do Differently With More Time

- Add a `--preview` mode that generates a side-by-side comparison of what the agent "sees" vs. what it decides to do at each step
- Build a simple web dashboard that replays the application process step-by-step
- Add retry logic with alternative strategies (e.g., fall back to DOM-based filling if vision-based clicking misses)
- Support multiple job applications by parameterizing the job description and URL

## The Bottom Line

The founder asked candidates to apply using only AI. Most people will paste their resume into ChatGPT, copy a cover letter, and manually fill the form. That's using AI as a writing tool.

I built an autonomous agent that handles the entire pipeline — parsing, writing, browsing, filling, uploading, recording, and documenting — without touching the keyboard. That's using AI as an operations engineer.

That's the difference between using AI and building with AI. And that's what this role is about.
