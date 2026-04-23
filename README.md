<h1 align="center">🧪 Specwright</h1>

<p align="center">
  <strong>Turn any requirements document into a runnable Playwright test suite — in minutes, with a free LLM.</strong>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10+-blue.svg">
  <img alt="Streamlit" src="https://img.shields.io/badge/UI-Streamlit-FF4B4B">
  <img alt="Playwright" src="https://img.shields.io/badge/output-Playwright%20TS-2EAD33">
  <img alt="LLM" src="https://img.shields.io/badge/LLM-Groq%20%7C%20Gemini%20%7C%20Ollama-8A2BE2">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green.svg">
</p>

<p align="center">
  PRD / SRS / BRD → IEEE-829 Test Plan → AI-sized Test Cases → Playwright TypeScript suite —
  with a <em>polished web UI</em>, inline editing, and six export formats.
</p>

---

## Why Specwright

Writing test plans and cases from requirements is the most mechanical part of QA work — it eats a day of a senior engineer's time per feature. Specwright automates that part while keeping humans in the loop at every review gate:

- **Reads** your PRD/SRS/BRD in plain English
- **Writes** a full IEEE-829 test plan you can edit and sign off on
- **Figures out** how many test cases each requirement needs — no hardcoded "always 20" heuristic
- **Exports** plans to PDF / DOCX / HTML / Markdown, cases to CSV / Excel / Jira / TestRail / HTML / Markdown
- **Lets you edit** cases inline with auto re-export to all six formats
- **Generates** a production-grade Playwright TypeScript suite with Page Object Model

No paid API required. Runs entirely on free LLMs. Single-user by default.

---

## Features

- 🧠 **Free LLMs** — defaults to **Groq** (fastest, most stable free tier); also supports Google Gemini, local Ollama, and Anthropic Claude
- 🎯 **AI-sized coverage** — the LLM itself decides case counts per requirement based on complexity, not a fixed "15-40" rule
- 🧩 **Chunked generation** — Stage 2 automatically splits into per-requirement calls when the provider's output cap would cause JSON truncation
- 📝 **IEEE-829 test plans** — scope, objectives, approach, environments, risks, exit criteria — in 10 sections
- ✏️ **Editable cases** — every cell editable inline; changes auto-save and re-export to all formats
- 📦 **10 export formats total**
  - Test plan: Markdown, HTML (styled), **PDF, DOCX**
  - Test cases: CSV, Excel, Jira (Xray), TestRail, HTML, Markdown
- 🎯 **Interactive scope gate** — smoke / regression / security / accessibility / custom presets
- 🎭 **Playwright TypeScript** — Page Object Model, UI + API tests, Dotenv config, ready for CI
- 🎨 **Polished web UI** — gradient hero, progress stepper, metric cards, priority-tinted tables
- 🧯 **Collapsed error UI** — problems shown as one-line banners; click to expand full traceback
- 🔒 **Safe by design** — path traversal blocked, no overwrite without consent, rate-limit auto-retry

---

## Pipeline

```
┌────────────────────┐
│ Requirements doc   │   .md / .txt / pasted
└─────────┬──────────┘
          ▼
   ┌─────────────┐
   │ Stage 1     │  →  test_plan.md  +  HTML / PDF / DOCX
   │ Planner     │
   └─────┬───────┘
         ▼
   ┌─────────────┐     Pass 1: LLM decides cases per requirement
   │ Stage 2     │     Pass 2: Generates (chunked if needed)
   │ Case Writer │  →  test_cases.json  +  6 export formats
   └─────┬───────┘         (editable inline, auto re-exports)
         ▼
   ┌─────────────┐
   │ Scope Gate  │  ←  Smoke / Regression / Security / Custom
   └─────┬───────┘
         ▼
   ┌─────────────┐
   │ Stage 3     │  →  tests/pages/*.ts + tests/specs/*.ts
   │ Automator   │     + tests/api/*.ts + playwright.config.ts
   └─────────────┘
```

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/specwright.git
cd specwright
pip install -r requirements.txt
```

### 2. Get a free API key

| Provider | Sign-up | Free tier | Notes |
|----------|---------|-----------|-------|
| **Groq** (default) | https://console.groq.com/keys | Generous free tier | Fast, reliable — recommended |
| **Google Gemini** | https://aistudio.google.com/apikey | 15 req/min on 2.5 Flash | Can be rate-limited under load |
| **Ollama** (local) | https://ollama.com/download | Unlimited — runs on your machine | 100% private, offline |
| **Anthropic Claude** | https://console.anthropic.com/ | Paid | Highest quality |

Windows PowerShell:

```powershell
$env:GROQ_API_KEY = "your-key-here"
```

macOS / Linux:

```bash
export GROQ_API_KEY="your-key-here"
```

### 3. Run the web UI

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`. No browser? Click the link Streamlit prints.

**Windows tip:** if `streamlit` isn't recognized, use `python -m streamlit run app.py` instead.

### 4. First run

1. Click **Use sample** → Load login PRD sample
2. Click **▶ Generate plan** — IEEE-829 plan appears in ~10 seconds
3. Click **▶ Generate cases** — cases appear in a filterable, editable table
4. Pick a scope preset (e.g. **Regression**)
5. Click **▶ Generate tests** — Playwright TypeScript files produced
6. Click **⬇ Download full project (.zip)**

That's the full loop.

---

## Screenshots

<!-- Drop real screenshots here. Filenames:
     docs/hero.png        - hero + stepper at the top of the app
     docs/cases.png       - editable test cases table
     docs/scope.png       - scope preset cards with live counts
     docs/downloads.png   - one-click download row (6 formats)
-->

> Screenshots coming soon — run the app to see it live.

---

## Usage Guide

### Step 1 — Provide a requirements document

Three ways:
- **Upload** a `.md` or `.txt` file
- **Paste** the requirement text
- **Load the sample** (included login PRD with 5 requirements)

Requirement IDs (REQ-1, REQ-2…) are extracted automatically. If missing, the agent assigns them.

### Step 2 — Generate the test plan

Click **▶ Generate plan**. Produces a full IEEE-829 test plan with:

1. Scope
2. Test objectives mapped to requirement IDs
3. Test approach (levels & types)
4. Features to test
5. Features NOT to test
6. Entry & exit criteria
7. Test environments
8. Risks & mitigations
9. Deliverables
10. Schedule estimate

**Review gate #1:** edit the plan inline, click Save, then re-export to all 4 formats with one button.

### Step 3 — Generate test cases (two-pass, AI-sized)

Click **▶ Generate cases**. This runs a **two-pass process**:

- **Pass 1 — Estimator.** The LLM scans the PRD and plan, returns a JSON breakdown like:
  ```json
  {
    "cases_per_requirement": {"REQ-1": 6, "REQ-2": 4, "REQ-3": 10},
    "reasoning": "REQ-3 has rate limiter + 4 sub-rules, needs more coverage"
  }
  ```
- **Pass 2 — Generator.** Uses the estimate to produce exactly the planned count of cases.
  - If total fits in the provider's output budget → one call
  - If it doesn't → chunks per-requirement, merges results, renumbers IDs globally

Each case has:

```json
{
  "id": "TC-007",
  "requirement_id": "REQ-2",
  "title": "Login rejects SQL injection in email",
  "type": "security",
  "target": "ui",
  "priority": "P0",
  "preconditions": [...],
  "steps": [...],
  "expected": "...",
  "automatable": true
}
```

**Review gate #2:** the table is editable inline. Change priorities, types, titles, automation flags, or remove rows entirely. **Every edit auto re-exports all 6 formats** — CSV, Excel, Jira, TestRail, HTML, Markdown — so your downloads always reflect the latest state.

### Step 4 — Choose automation scope

Visual preset cards with live counts:

| Preset            | Includes                                 | Typical use               |
|-------------------|------------------------------------------|----------------------------|
| **Smoke**         | P0 happy paths only                      | CI gate on every PR        |
| **Regression**    | P0 + P1 functional / negative / boundary | Nightly full run           |
| **Security**      | Security cases only                      | Pre-release security pass  |
| **Accessibility** | Accessibility cases only                 | Pre-UX review              |
| **Everything**    | All automatable cases                    | Full release suite         |
| **Custom**        | Filter by priority / type / target       | One-off focused runs       |

### Step 5 — Generate & run Playwright tests

Click **▶ Generate tests**. You get a complete Playwright project:

```
your-project/
├── playwright.config.ts
├── package.json
├── tsconfig.json
├── .env.example
├── AUTOMATION_REPORT.md
└── tests/
    ├── pages/           ← Page Object Model classes
    ├── specs/           ← UI tests (use { page })
    ├── api/             ← API tests (Playwright request fixture)
    └── fixtures/        ← shared test fixtures
```

Download the ZIP, then:

```bash
unzip specwright_output.zip -d my-tests
cd my-tests
npm install
npx playwright install
cp .env.example .env       # edit BASE_URL, TEST_USER, TEST_PASS
npx playwright test
```

### Running tests by priority or type

Every generated test is tagged with its TC-ID, priority, and type:

```bash
npx playwright test --grep @P0              # smoke suite
npx playwright test --grep @security        # security only
npx playwright test --grep "@P0|@P1"        # regression
```

---

## Configuration

Copy `config.example.yaml` to `config.yaml` and edit the `llm` block. Groq is the default:

```yaml
llm:
  provider: groq                    # groq | gemini | ollama | anthropic
  model: llama-3.3-70b-versatile
  api_key: ${GROQ_API_KEY}          # env var substitution
  temperature: 0.2

exports:
  - csv
  - excel
  - jira
  - testrail
  - html
  - markdown
```

To switch providers mid-session, just change the sidebar dropdown in the UI — no restart.

---

## Project Structure

```
specwright/
├── app.py                      # Streamlit web UI
├── qa_agent.py                 # CLI entry point (alternative)
├── stages.py                   # Stage 1/2/3 pipeline (two-pass Stage 2)
├── exporters.py                # 10 export formats (6 cases + 4 plans)
├── scope.py                    # Scope presets + filter
├── prompts.py                  # LLM system prompts
├── config.py                   # Config loader
├── config.example.yaml         # Sample config (Groq default)
├── providers/
│   ├── base.py                 # Abstract LLMProvider + max_output_tokens
│   ├── groq_provider.py
│   ├── gemini_provider.py
│   ├── ollama_provider.py
│   └── anthropic_provider.py
├── examples/
│   └── login_prd.md            # Sample PRD to try
├── requirements.txt
├── README.md
├── LICENSE
└── PUBLISHING.md               # Guide to pushing to GitHub
```

---

## LLM Provider Comparison

| Provider              | Cost | Speed  | Quality | Free-tier cap | Best for                              |
|-----------------------|------|--------|---------|---------------|----------------------------------------|
| **Groq** (default)    | Free | Fastest | Good    | 8K output     | Rapid iteration, most stable |
| Gemini 2.5 Flash      | Free | Good   | High    | 8K output     | When Groq is over quota      |
| Ollama (local)        | Free | Varies | Varies  | ∞             | 100% private, offline, no key|
| Claude Sonnet 4.6     | Paid | Good   | Highest | 32K output    | Hardest-to-test features      |

The pipeline automatically chunks generation when a provider's output cap would cause truncation — so even Groq's 8K cap produces complete test cases for large PRDs via per-requirement chunking.

---

## UI Highlights

- **Gradient hero header** and sidebar-driven config
- **5-step progress stepper** across the top — completed steps turn green, current step highlighted
- **Metric cards** for case totals, P0 count, UI / API split
- **`st.data_editor` table** — every cell editable, add/delete rows, auto re-exports on change
- **Priority color coding** in the table (P0 red, P1 amber, P2 gray)
- **Collapsed errors** — one-line banner with "Details" toggle instead of giant stack traces
- **Multiple errors accumulate** in tabs for comparison

---

## Safety Features

- **Path traversal blocked** — agent can't write outside the project root
- **Overwrite protection** — existing files are not replaced without explicit consent
- **Rate-limit auto-retry** — exponential backoff (10s → 20s → 40s → 80s → 160s) on 429, 503, 502, 504
- **Server-overload handling** — 503 UNAVAILABLE from Gemini triggers the same retry chain
- **Input sanitization** — LLM output cleaned of markdown fences and extraneous prose
- **JSON fallback parsing** — if the LLM returns `{"test_cases": [...]}` instead of `[...]`, the wrapper is auto-stripped
- **No test execution on untrusted code** — generated tests only run against your app

---

## Requirements

- Python 3.10+
- Node.js 18+ (only to run the generated Playwright tests — not to run Specwright itself)
- A free API key from Groq, Gemini, or local Ollama installation
- ~80 MB disk space (including reportlab and python-docx for plan exports)

---

## Troubleshooting

**`streamlit: command not found` (Windows)**
→ Use `python -m streamlit run app.py`.

**`No module named 'providers'`**
→ You're running from the wrong folder, or the ZIP was extracted one level too deep. Run `dir` and confirm `app.py`, `providers/`, `stages.py` are all in the current folder.

**`ValueError: Could not parse JSON` in Stage 2**
→ The LLM's output was truncated by the provider's token cap. Update to the latest version — the two-pass + chunked generation in Stage 2 fixes this automatically.

**`503 UNAVAILABLE` or `429 rate limited`**
→ Automatic retry with exponential backoff kicks in. If it still fails after 5 attempts, switch the sidebar Provider to a different LLM.

**Error shows as one line at the top of the page**
→ This is intentional. Toggle **Details** next to the banner to see the full traceback. **Clear** wipes the error log.

---

## Contributing

PRs welcome. Areas where help is wanted:

- Additional LLM providers (Mistral, Cohere, local Llama.cpp)
- More export formats (Zephyr, qTest, Azure DevOps)
- Jira / Confluence direct integration — read requirements from a ticket
- Test execution + result reporting in the UI
- Eval harness to measure generated-test quality across providers

Open an issue first to discuss anything bigger than a bug fix.

---

## Roadmap

- [ ] **Jira / Confluence input** — pull requirements straight from a ticket
- [ ] **In-UI test execution** — run `npx playwright test` and show results
- [ ] **Eval harness** — benchmark generated test quality across provider / model combinations
- [ ] **Multi-user mode** — save projects, come back later, share with team
- [ ] **Cucumber BDD output** — optional `.feature` file generation
- [ ] **Cypress output** — alternative to Playwright
- [ ] **Mobile (Appium / Maestro)** — for mobile app QA
- [ ] **Jira direct push** — create test issues via API instead of CSV import

---

## FAQ

**Does this replace human QA engineers?**
No. It handles the mechanical parts — plans, cases, boilerplate code — so engineers can focus on exploratory testing, risk analysis, and the cases an LLM would miss. Review gates at Stages 1, 2, and 4 are designed for human approval.

**Why Groq as default instead of Gemini?**
Groq has proven more stable under load. Gemini 2.5 Flash occasionally returns `503 UNAVAILABLE` during peak hours, whereas Groq typically responds in 1–2 seconds with high availability. Both are free.

**Can I edit cases after generation?**
Yes. The Stage 3 table is fully editable — change any cell, add rows, delete rows. Every edit triggers auto re-export to all 6 download formats.

**How does the two-pass case generation work?**
Pass 1 asks the LLM to count how many cases each requirement needs, based on complexity. Pass 2 generates exactly that many cases, chunking per-requirement if the total would exceed the LLM's output cap. The result is complete, parseable JSON every time — no truncation.

**What LLMs work best for hard features?**
For deeply complex security / crypto / banking features, Claude Sonnet 4.6 produces the most thorough test cases. For everyday web-app features, Groq's Llama 3.3 70B is indistinguishable from paid models. Gemini 2.5 Pro is strong when Groq is over quota.

**Can I read Jira tickets?**
Not yet — on the roadmap. For now, copy-paste the ticket description into the Paste tab or save it as `.md`.

**What about mobile testing?**
Also on the roadmap. Current output is Playwright for web (UI + API). Mobile via Appium or Maestro is planned.

**How good are the generated tests?**
Good enough to run. Review them before merging — like any generated code. The Page Object Model structure and resilient locators (`getByRole`, `getByLabel`, `getByText`) make them maintainable.

**Can I customize the prompts?**
Yes. All prompts live in `prompts.py`. Each stage has its own system prompt you can tune to your team's conventions.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Credits

Built with:
- [Streamlit](https://streamlit.io) — web UI
- [Playwright](https://playwright.dev) — test framework
- [groq-python](https://github.com/groq/groq-python) — default LLM provider
- [google-genai](https://github.com/googleapis/python-genai) — Gemini provider
- [ollama-python](https://github.com/ollama/ollama-python) — local LLM provider
- [reportlab](https://www.reportlab.com/) — PDF generation
- [python-docx](https://github.com/python-openxml/python-docx) — DOCX generation
- [openpyxl](https://openpyxl.readthedocs.io/) — Excel export

---

<p align="center">
  <strong>Made for QA engineers who want to spend less time writing boilerplate
  and more time finding real bugs.</strong>
</p>