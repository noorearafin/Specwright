<h1 align="center">🧪 QA Agent</h1>

<p align="center">
  <strong>Turn any requirements document into a full Playwright test suite — using a free LLM.</strong>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10+-blue.svg">
  <img alt="Streamlit" src="https://img.shields.io/badge/UI-Streamlit-FF4B4B">
  <img alt="Playwright" src="https://img.shields.io/badge/output-Playwright%20TS-2EAD33">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green.svg">
</p>

<p align="center">
  PRD/SRS/BRD → IEEE-829 Test Plan → 20–40 Test Cases → Playwright TypeScript suite,
  guided by <em>you</em>, powered by <em>free LLMs</em> (Gemini / Groq / Ollama).
</p>

---

## Why this exists

Writing test plans and test cases from requirements is the most mechanical part of QA work — it eats a day of a senior QA engineer's time for every medium-sized feature. This agent automates the mechanical part while keeping the human in the loop at every review gate:

- **Reads** your PRD/SRS/BRD in plain English
- **Writes** a proper IEEE-829 test plan you can sign off on
- **Generates** detailed test cases covering positive, negative, boundary, security, and accessibility paths
- **Exports** those cases to CSV, Excel, Jira, TestRail, HTML, or Markdown
- **Lets you choose scope** (smoke / regression / security / custom)
- **Generates** Playwright TypeScript code with Page Object Model structure

All with a free LLM. No vendor lock-in.

## Features

- 🧠 **Works with free LLMs** — Google Gemini, Groq, or local Ollama (no paid API needed)
- 📝 **IEEE-829 test plans** — scope, objectives, approach, environments, risks, criteria
- ✅ **Comprehensive test cases** — positive, negative, boundary, edge, security, accessibility, contract
- 📦 **6 export formats** — CSV, Excel (.xlsx), Jira CSV (Xray), TestRail CSV, HTML report, Markdown
- 🎯 **Interactive scope gate** — pick smoke / regression / security / accessibility / custom before automating
- 🎭 **Playwright TypeScript output** — Page Object Model, UI + API tests, Dotenv config, ready for CI
- 🖥️ **Two interfaces** — CLI for speed, Streamlit web UI for visibility
- 🔒 **Safe by design** — path traversal blocked, no overwrite without consent

## Pipeline

```
┌────────────────────┐
│  Requirements doc  │   (.md / .txt / pasted)
└─────────┬──────────┘
          ▼
   ┌─────────────┐
   │  Stage 1    │  →  IEEE-829 test plan
   │  Planner    │
   └─────┬───────┘
         ▼
   ┌─────────────┐
   │  Stage 2    │  →  JSON + CSV + Excel + Jira + TestRail + HTML + Markdown
   │  Case Writer│
   └─────┬───────┘
         ▼
   ┌─────────────┐
   │  Scope Gate │  ←  YOU pick: smoke / regression / security / custom
   └─────┬───────┘
         ▼
   ┌─────────────┐
   │  Stage 3    │  →  tests/pages/*.ts, tests/specs/*.ts, tests/api/*.ts
   │  Automator  │
   └─────────────┘
```

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/qa-agent.git
cd qa-agent
pip install -r requirements.txt
```

### 2. Get a free API key

| Provider | Sign-up | Free tier |
|----------|---------|-----------|
| **Google Gemini** (recommended) | https://aistudio.google.com/apikey | 15 req/min on 2.5 Flash |
| **Groq** | https://console.groq.com/keys | Generous free tier |
| **Ollama** (local, fully free) | https://ollama.com/download | Unlimited — runs on your machine |

```bash
export GEMINI_API_KEY="your-key-here"
```

### 3. Run it

**Web UI (recommended):**

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`.

**CLI:**

```bash
python qa_agent.py examples/login_prd.md ./output
```

That's it. You'll go through 5 steps: upload PRD → generate plan → generate cases → pick scope → download Playwright suite.

## Usage Guide

### Step-by-step walkthrough

#### Step 1: Provide a requirements document

Any of these work:
- Upload a `.md` or `.txt` file
- Paste the requirement text directly
- Use the included `examples/login_prd.md` to try it out

The document should have clear requirement IDs (REQ-1, REQ-2...) or the agent will assign them.

#### Step 2: Generate the test plan

Click **Generate plan**. Produces a full IEEE-829 test plan with 10 sections: scope, objectives, approach, features in/out, entry/exit criteria, environments, risks, deliverables, and a schedule estimate.

You can **edit the plan inline** before moving on. This is the first review gate.

#### Step 3: Generate test cases

Click **Generate cases**. Produces 15–40 structured test cases, each with ID, requirement link, type, target (ui/api/manual), priority, preconditions, steps, expected outcome, and an `automatable` flag.

They automatically export in all 6 formats. Second review gate — mark cases as `automatable: false` if they need human judgment (real inbox, CAPTCHA, screen reader).

#### Step 4: Choose automation scope

Before generating code, pick what's in scope:

| Preset            | Includes                                 | Typical use                  |
|-------------------|------------------------------------------|------------------------------|
| **Smoke**         | P0 happy paths only                      | CI gate on every PR          |
| **Regression**    | P0 + P1 functional/negative/boundary     | Nightly full run             |
| **Security**      | Security cases only                      | Pre-release security pass    |
| **Accessibility** | Accessibility cases only                 | Pre-UX-review pass           |
| **Everything**    | All automatable cases                    | Full release suite           |
| **Custom**        | Filter by priority / type / target       | One-off focused runs         |

#### Step 5: Generate & run Playwright tests

Click **Generate tests**. You get a complete Playwright project:

```
your-project/
├── playwright.config.ts
├── package.json
├── tsconfig.json
├── .env.example
├── AUTOMATION_REPORT.md
└── tests/
    ├── pages/           ← Page Object Model
    ├── specs/           ← UI tests
    ├── api/             ← API tests (Playwright request fixture)
    └── fixtures/        ← shared fixtures
```

Download the ZIP, then:

```bash
unzip qa_agent_output.zip -d my-tests
cd my-tests
npm install
npx playwright install
cp .env.example .env       # edit BASE_URL, TEST_USER, TEST_PASS
npx playwright test
```

### Running tests by priority or type

Tests are tagged with TC-ID, priority, and type:

```bash
npx playwright test --grep @P0              # smoke suite
npx playwright test --grep @security        # security only
npx playwright test --grep "@P0|@P1"        # regression
```

## Configuration

Copy `config.example.yaml` to `config.yaml` and edit the `llm` block:

```yaml
llm:
  provider: gemini              # gemini | groq | ollama | anthropic
  model: gemini-2.5-flash
  api_key: ${GEMINI_API_KEY}    # env var substitution
  temperature: 0.2

exports:
  - csv
  - excel
  - jira
  - testrail
  - html
  - markdown
```

## Project Structure

```
qa-agent/
├── app.py                      # Streamlit web UI
├── qa_agent.py                 # CLI entry point
├── stages.py                   # Stage 1/2/3 pipeline logic
├── exporters.py                # 6 export formats
├── scope.py                    # scope presets + filter
├── prompts.py                  # LLM system prompts
├── config.py                   # config loader
├── config.example.yaml         # sample config
├── providers/                  # LLM provider abstraction
│   ├── base.py
│   ├── gemini_provider.py
│   ├── groq_provider.py
│   ├── ollama_provider.py
│   └── anthropic_provider.py
├── examples/
│   └── login_prd.md            # sample PRD to try
├── requirements.txt
├── README.md
└── LICENSE
```

## LLM Provider Comparison

| Provider              | Cost | Speed  | Quality | Best for                              |
|-----------------------|------|--------|---------|---------------------------------------|
| Gemini 2.5 Flash      | Free | Good   | High    | Default — generous free tier          |
| Groq (Llama 3.3 70B)  | Free | Fast   | Good    | Rapid iteration, free tier            |
| Ollama (local)        | Free | Varies | Varies  | 100% private, offline, no API key     |
| Claude Sonnet 4.6     | Paid | Good   | Highest | Hardest-to-test features              |

Switch any time by editing `config.yaml` — no code changes.

## Safety Features

- **Path traversal blocked** — agent can't write outside the project root
- **Overwrite protection** — existing files are not replaced without explicit consent
- **Rate limit handling** — automatic retry with exponential backoff on free tier limits
- **Input sanitization** — LLM output cleaned of markdown fences and extraneous prose

## Requirements

- Python 3.10+
- Node.js 18+ (only to run the generated Playwright tests)
- A free API key from Gemini, Groq, or local Ollama installation
- ~50 MB disk space

## Contributing

PRs welcome! Areas where help is wanted:

- Additional LLM providers (Mistral, Cohere, local Llama.cpp)
- More export formats (Zephyr, qTest, Azure DevOps)
- Jira/Confluence direct integration (read requirements from a ticket)
- Test execution + result reporting in the UI
- Eval harness to measure generated-test quality

Open an issue first to discuss anything bigger than a bug fix.

## Roadmap

- [ ] **Jira/Confluence input** — pull requirements straight from a ticket
- [ ] **Test execution in UI** — run `npx playwright test` and show results
- [ ] **Eval harness** — benchmark generated test quality across provider/model combinations
- [ ] **Multi-user mode** — save projects, come back later, share with team
- [ ] **Cucumber BDD output** — optional `.feature` file generation
- [ ] **Cypress output** — alternative to Playwright
- [ ] **Mobile (Appium/Maestro)** — for mobile app QA

## FAQ

**Does this replace human QA engineers?**
No. It handles the mechanical part (writing plans, cases, and boilerplate code) so QA engineers can focus on exploratory testing, risk analysis, and the cases an LLM would miss. The review gates at Stage 1 and 2 are designed for human approval.

**What LLMs work best?**
Gemini 2.5 Flash is the default — good balance of quality and cost (free). For the hardest feature specs, Claude Sonnet 4.6 produces the most thorough test cases but it's paid. Groq is fastest if you care about iteration speed.

**Can it read Jira tickets?**
Not yet (on the roadmap). For now, copy-paste the ticket description into the UI or save as `.md`.

**What about mobile testing?**
Also on the roadmap. The current output is Playwright for web (UI + API). Mobile via Appium or Maestro is planned.

**How good are the generated tests?**
Good enough to run. You should review them before merging — like any generated code. The Page Object Model structure and resilient locators (`getByRole`, `getByLabel`) make them reasonably maintainable.

**Can I customize the prompts?**
Yes. All prompts live in `prompts.py`. Each stage has its own system prompt you can tune to your team's conventions.

## License

MIT — see [LICENSE](LICENSE).

## Credits

Built with [Streamlit](https://streamlit.io), [Playwright](https://playwright.dev),
[google-genai](https://github.com/googleapis/python-genai), [groq-python](https://github.com/groq/groq-python),
and [ollama-python](https://github.com/ollama/ollama-python).

---

<p align="center">
  <strong>Made for QA engineers who want to spend less time writing boilerplate
  and more time finding real bugs.</strong>
</p>
