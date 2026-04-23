# 🚀 Publishing to GitHub — Step-by-Step Guide

I can't create the repository from here — that needs your GitHub account. Follow these steps to get it live in ~5 minutes.

## Method A — Using the GitHub CLI (fastest, recommended)

If you have `gh` installed ([install here](https://cli.github.com/)):

```bash
# 1. Go into the project folder
cd qa_agent_ui

# 2. Initialize git and make the first commit
git init
git add .
git commit -m "Initial commit: QA Agent — PRD to Playwright pipeline"

# 3. Log in to GitHub (if you haven't)
gh auth login

# 4. Create the repo AND push in one command
gh repo create qa-agent --public --source=. --remote=origin --push

# Done! Open it:
gh repo view --web
```

That's it. Replace `--public` with `--private` if you want.

---

## Method B — Using the GitHub web UI (no CLI needed)

### Step 1 — Create the empty repository

1. Go to **https://github.com/new**
2. **Repository name:** `qa-agent`
3. **Description:** `Turn a PRD into a runnable Playwright test suite. Free LLMs supported.`
4. **Public** (or Private — your call)
5. **Do NOT** check "Initialize this repository with a README" (we have one already)
6. **Do NOT** add `.gitignore` or license (we have those too)
7. Click **Create repository**

GitHub will show you a page with setup instructions. Keep it open.

### Step 2 — Push your code from your terminal

```bash
# Go into the project folder
cd qa_agent_ui

# Initialize git
git init
git branch -M main

# Stage and commit all files
git add .
git commit -m "Initial commit: QA Agent — PRD to Playwright pipeline"

# Add the GitHub remote (REPLACE YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/qa-agent.git

# Push!
git push -u origin main
```

If GitHub asks for a password, it actually wants a **Personal Access Token**:

1. Go to https://github.com/settings/tokens
2. **Generate new token (classic)**
3. Tick the `repo` scope
4. Copy the token and paste it as the password

(Alternatively, use SSH instead of HTTPS — see step 4 below.)

### Step 3 — Update the README username

Open `README.md` and replace `YOUR_USERNAME` with your actual GitHub username in 4 places (clone URLs). Then:

```bash
git add README.md
git commit -m "Update README with repo URL"
git push
```

### Step 4 (optional) — Switch to SSH so you never type your token again

```bash
# Generate an SSH key if you don't have one
ssh-keygen -t ed25519 -C "your_email@example.com"

# Copy the public key
cat ~/.ssh/id_ed25519.pub
# ssh-ed25519 AAAA... your_email@example.com  ← copy this whole line
```

1. Go to https://github.com/settings/ssh/new
2. **Title:** `My laptop` (or whatever)
3. Paste the key, click **Add SSH key**

Now switch the remote:

```bash
git remote set-url origin git@github.com:YOUR_USERNAME/qa-agent.git
git push
```

---

## After it's published

### Add topics for discoverability

On the repo page, click the ⚙️ next to **About** and add topics like:
`qa` `testing` `playwright` `llm` `gemini` `automation` `python` `streamlit` `test-automation`

### Add a social preview image

Settings → General → Social preview → upload a 1280×640 image of the Streamlit UI screenshot.

### Clone and verify

To prove everything works, clone to a fresh directory and run the install steps from the README:

```bash
cd /tmp
git clone https://github.com/YOUR_USERNAME/qa-agent.git
cd qa-agent
pip install -r requirements.txt
export GEMINI_API_KEY=your-key-here
streamlit run app.py
```

If that works, anyone in the world can now install and run your project in one copy-paste.

---

## Troubleshooting

**`remote: Permission denied`**
→ Your token has expired or doesn't have `repo` scope. Regenerate at https://github.com/settings/tokens.

**`failed to push some refs`**
→ The repo on GitHub already has a commit (e.g. from an auto-generated README). Do `git pull --rebase origin main` first, then push.

**`fatal: not a git repository`**
→ You forgot `git init`. Run it first.

**`.env` file accidentally committed**
→ Remove it from history: `git rm --cached .env && git commit -m "Remove .env"`. Rotate any exposed API keys.

**Files over 100 MB**
→ Shouldn't happen with this project, but if so: add the path to `.gitignore`, then `git rm --cached <path>`.

---

## Recommended next steps

Once it's live, these are high-value additions that take <1 hour each:

1. **Add a GitHub Actions workflow** (`.github/workflows/test.yml`) that runs `python -c "import app; import stages"` to catch import breakage on PRs
2. **Add screenshots** to the README — a shot of the Streamlit UI at each stage makes the project instantly understandable
3. **Create a GitHub Release** for v0.1.0 — tag it `v0.1.0`, write release notes, attach a ZIP
4. **Pin it to your profile** so it shows up front and center on your GitHub page

Good luck with the launch!
