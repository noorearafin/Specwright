"""Specwright — Streamlit UI for QA Agent.

PRD → Test Plan → Editable Test Cases → Scope Gate → Playwright TS suite.
Default LLM: Groq (free, fast). Fallback: Gemini, Ollama, Anthropic.

Run:  streamlit run app.py
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import traceback
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from providers import get_provider
from stages import stage1_plan, stage2_cases, stage3_automate
from scope import (PRESETS, apply_scope, coverage_report, describe_scope,
                   load_saved_scopes, save_scope)
from exporters import run_exports, export_plan


# ══════════════════════════════════════════════════════════════════════════════
# Page setup
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Specwright",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
CUSTOM_CSS = """
<style>
  /* ═══════════════════ Keyframes ═══════════════════ */
  @keyframes sw-gradient-shift {
    0%   { background-position: 0% 50%; }
    50%  { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
  }
  @keyframes sw-fade-in-up {
    from { opacity: 0; transform: translateY(14px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes sw-fade-in {
    from { opacity: 0; }
    to   { opacity: 1; }
  }
  @keyframes sw-pulse-glow {
    0%, 100% { box-shadow: 0 2px 8px rgba(124, 58, 237, 0.18); }
    50%      { box-shadow: 0 3px 12px rgba(124, 58, 237, 0.30); }
  }
  @keyframes sw-shine {
    0%   { transform: translateX(-120%) skewX(-20deg); }
    60%, 100% { transform: translateX(220%) skewX(-20deg); }
  }
  @keyframes sw-pop {
    0%   { transform: scale(0.7); opacity: 0; }
    70%  { transform: scale(1.08); }
    100% { transform: scale(1); opacity: 1; }
  }
  @keyframes sw-shake {
    0%, 100% { transform: translateX(0); }
    20%      { transform: translateX(-6px); }
    40%      { transform: translateX(5px); }
    60%      { transform: translateX(-3px); }
    80%      { transform: translateX(2px); }
  }
  @keyframes sw-check-pop {
    0%   { transform: scale(0); }
    60%  { transform: scale(1.25); }
    100% { transform: scale(1); }
  }

  /* Hero header with animated gradient accent + shine sweep */
  .sw-hero {
    position: relative;
    overflow: hidden;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #6d5bd0 100%);
    background-size: 200% 200%;
    animation: sw-gradient-shift 12s ease infinite, sw-fade-in-up 0.6s ease both;
    color: white;
    padding: 1.5rem 1.75rem;
    border-radius: 14px;
    margin-bottom: 1.25rem;
    box-shadow: 0 4px 20px rgba(102, 126, 234, 0.25);
  }
  /* Diagonal light sweep across the hero — subtle, slow, with a long pause */
  .sw-hero::after {
    content: "";
    position: absolute;
    top: 0; left: 0;
    width: 40%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.10), transparent);
    animation: sw-shine 11s ease-in-out infinite;
    pointer-events: none;
  }
  .sw-hero h1 {
    color: white !important;
    margin: 0;
    font-size: 1.9rem;
    font-weight: 700;
    letter-spacing: -0.5px;
  }
  .sw-hero p {
    color: rgba(255,255,255,0.85);
    margin: 0.35rem 0 0;
    font-size: 0.95rem;
  }

  /* Progress stepper */
  .sw-stepper {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    margin: 0 0 1.5rem;
    padding: 0.75rem 0;
  }
  .sw-step {
    flex: 1;
    padding: 0.6rem 0.5rem;
    text-align: center;
    border-radius: 10px;
    border: 1px solid #e5e7eb;
    background: #f9fafb;
    font-size: 0.82rem;
    color: #6b7280;
    font-weight: 500;
    transition: transform 0.2s ease, box-shadow 0.2s ease,
                background 0.3s ease, border-color 0.3s ease, color 0.3s ease;
    position: relative;
    animation: sw-fade-in-up 0.5s ease both;
  }
  /* Stagger the steps as they fade in */
  .sw-step:nth-child(1) { animation-delay: 0.05s; }
  .sw-step:nth-child(2) { animation-delay: 0.12s; }
  .sw-step:nth-child(3) { animation-delay: 0.19s; }
  .sw-step:nth-child(4) { animation-delay: 0.26s; }
  .sw-step:nth-child(5) { animation-delay: 0.33s; }
  .sw-step:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  }
  .sw-step.done {
    background: #d1fae5;
    border-color: #10b981;
    color: #065f46;
  }
  .sw-step.active {
    background: #ede9fe;
    border-color: #7c3aed;
    color: #5b21b6;
    font-weight: 600;
    animation: sw-fade-in-up 0.5s ease both, sw-pulse-glow 3.2s ease-in-out infinite 0.5s;
  }
  .sw-step-num {
    display: inline-block;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: rgba(0,0,0,0.1);
    color: inherit;
    font-size: 0.7rem;
    line-height: 20px;
    text-align: center;
    margin-right: 0.3rem;
    font-weight: 700;
    transition: background 0.3s ease, transform 0.3s ease;
  }
  .sw-step.done .sw-step-num {
    background: #10b981;
    color: white;
    animation: sw-check-pop 0.4s ease both;
  }
  .sw-step.active .sw-step-num { background: #7c3aed; color: white; }

  /* Section cards - softer borders + gentle entrance + hover lift */
  [data-testid="stVerticalBlock"] > [style*="border"] {
    border-radius: 12px !important;
    animation: sw-fade-in-up 0.5s ease both;
    transition: box-shadow 0.25s ease, transform 0.25s ease;
  }
  [data-testid="stVerticalBlock"] > [style*="border"]:hover {
    box-shadow: 0 6px 22px rgba(0, 0, 0, 0.06);
  }

  /* Priority badges in data_editor */
  .sw-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 0.75rem;
    font-weight: 600;
    transition: transform 0.15s ease;
  }
  .sw-badge:hover { transform: scale(1.08); }
  .sw-badge-p0 { background: #fee2e2; color: #991b1b; }
  .sw-badge-p1 { background: #fef3c7; color: #92400e; }
  .sw-badge-p2 { background: #f3f4f6; color: #374151; }

  /* Error banner — shakes in to draw attention */
  .sw-error {
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 10px;
    padding: 0.75rem 1rem;
    margin: 0.5rem 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    animation: sw-shake 0.5s ease both;
  }
  .sw-error-text {
    color: #991b1b;
    font-weight: 500;
    font-size: 0.9rem;
  }

  /* Metric cards with subtle color + pop-in + hover lift */
  [data-testid="stMetric"] {
    background: #f8fafc;
    padding: 0.75rem;
    border-radius: 10px;
    border: 1px solid #e2e8f0;
    transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
    animation: sw-pop 0.45s ease both;
  }
  [data-testid="stMetric"]:hover {
    transform: translateY(-3px);
    box-shadow: 0 6px 16px rgba(102, 126, 234, 0.12);
    border-color: #c7d2fe;
  }

  /* Buttons — lift + animated shine sweep on hover */
  .stButton > button {
    transition: transform 0.15s ease, box-shadow 0.2s ease, background 0.2s ease;
  }
  .stButton > button:active { transform: translateY(1px) scale(0.99); }
  .stButton > button[kind="primary"] {
    position: relative;
    overflow: hidden;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border: none;
    font-weight: 600;
    box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
  }
  .stButton > button[kind="primary"]::after {
    content: "";
    position: absolute;
    top: 0; left: 0;
    width: 35%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.35), transparent);
    transform: translateX(-150%) skewX(-20deg);
    transition: none;
  }
  .stButton > button[kind="primary"]:hover {
    box-shadow: 0 6px 16px rgba(102, 126, 234, 0.45);
    transform: translateY(-1px);
  }
  .stButton > button[kind="primary"]:hover::after {
    animation: sw-shine 0.9s ease;
  }

  /* Download buttons — subtle lift */
  [data-testid="stDownloadButton"] > button {
    transition: transform 0.15s ease, box-shadow 0.2s ease;
  }
  [data-testid="stDownloadButton"] > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  }

  /* Tabs — animated underline + hover color */
  .stTabs [data-baseweb="tab"] {
    transition: color 0.2s ease;
  }
  .stTabs [data-baseweb="tab-highlight"] {
    transition: all 0.25s ease;
  }

  /* Sidebar tighter + gentle slide-in */
  section[data-testid="stSidebar"] > div {
    padding-top: 1rem;
    animation: sw-fade-in 0.6s ease both;
  }

  /* Success / info / toast alerts fade up into view */
  [data-testid="stAlert"] {
    animation: sw-fade-in-up 0.4s ease both;
  }

  /* Slightly livelier default spinner */
  [data-testid="stSpinner"] > div {
    border-top-color: #7c3aed !important;
  }

  /* Hide the default Streamlit header/menu for a cleaner look */
  #MainMenu {visibility: hidden;}
  footer {visibility: hidden;}

  /* Respect users who prefer reduced motion — disable all animation */
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation-duration: 0.001ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.001ms !important;
    }
  }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Session state
# ══════════════════════════════════════════════════════════════════════════════
DEFAULTS = {
    "prd_text": "",
    "plan": None,
    "cases": None,
    "cases_original": None,     # track edits vs initial
    "scope_selection": "regression",
    "custom_priorities": [],
    "custom_types": [],
    "custom_targets": [],
    "workspace": None,
    "stage3_done": False,
    "errors": [],               # list of {stage, short, detail, time}
}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)


def get_workspace() -> Path:
    if st.session_state.workspace is None:
        st.session_state.workspace = Path(tempfile.mkdtemp(prefix="specwright_"))
    return st.session_state.workspace


def reset_from(stage: int) -> None:
    if stage <= 1:
        st.session_state.plan = None
    if stage <= 2:
        st.session_state.cases = None
        st.session_state.cases_original = None
    if stage <= 3:
        st.session_state.stage3_done = False


def current_stage() -> int:
    """Determine active step (1-5) based on what's done."""
    if st.session_state.stage3_done:
        return 5
    if st.session_state.cases:
        return 4
    if st.session_state.plan:
        return 3
    if st.session_state.prd_text:
        return 2
    return 1


def log_error(stage: str, exc: Exception) -> None:
    """Record an error for collapsed display."""
    st.session_state.errors.append({
        "stage": stage,
        "short": f"{type(exc).__name__}: {str(exc)[:120]}",
        "detail": f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}",
        "time": datetime.now().strftime("%H:%M:%S"),
    })


def _run_safe(stage_label: str, fn, *args, **kwargs):
    """Run fn under a spinner. On error, log and return None — caller handles UI."""
    try:
        with st.spinner(stage_label):
            return fn(*args, **kwargs)
    except SystemExit as e:
        log_error(stage_label, Exception(str(e)))
    except Exception as e:  # noqa: BLE001
        log_error(stage_label, e)
    return None


def _dl_button(col, path: Path, label: str, mime: str, key_suffix: str = "") -> None:
    if path.exists():
        col.download_button(
            f"⬇ {label}",
            data=path.read_bytes(),
            file_name=path.name,
            mime=mime,
            use_container_width=True,
            key=f"dl_{path.name}_{key_suffix}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Sidebar — Provider config (Groq default)
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### ⚙️ LLM Provider")

    provider_choice = st.selectbox(
        "Provider",
        ["groq", "gemini", "ollama", "anthropic"],
        index=0,
        help="Groq is recommended — free, fast, stable.",
    )

    MODEL_DEFAULTS = {
        "groq": "llama-3.3-70b-versatile",
        "gemini": "gemini-2.5-flash",
        "ollama": "llama3.1:8b",
        "anthropic": "claude-sonnet-4-6",
    }
    KEY_ENV = {
        "groq": "GROQ_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "ollama": None,
        "anthropic": "ANTHROPIC_API_KEY",
    }
    model = st.text_input("Model", value=MODEL_DEFAULTS[provider_choice])

    env_name = KEY_ENV[provider_choice]
    api_key = ""
    if env_name:
        existing = os.environ.get(env_name, "")
        if existing:
            st.success(f"✓ `{env_name}` found in environment")
            api_key = existing
        else:
            api_key = st.text_input(
                f"{env_name}",
                type="password",
                help=f"Or set {env_name} env var and restart",
            )
    else:
        st.info("Ollama runs locally — make sure `ollama serve` is running.")

    temperature = st.slider("Temperature", 0.0, 1.0, 0.2, 0.1)

    llm_cfg = {
        "provider": provider_choice,
        "model": model,
        "api_key": api_key or None,
        "temperature": temperature,
    }

    # Quick-links
    st.markdown("### 🔗 Get a free API key")
    if provider_choice == "groq":
        st.markdown("[Groq Console →](https://console.groq.com/keys)")
    elif provider_choice == "gemini":
        st.markdown("[Google AI Studio →](https://aistudio.google.com/apikey)")
    elif provider_choice == "anthropic":
        st.markdown("[Anthropic Console →](https://console.anthropic.com/)")
    elif provider_choice == "ollama":
        st.markdown("[Download Ollama →](https://ollama.com/download)")

    st.divider()
    st.markdown("### 🗂 Workspace")
    ws = get_workspace()
    st.code(str(ws), language="text")
    if st.button("🗑 Reset workspace", use_container_width=True):
        for k in DEFAULTS:
            st.session_state[k] = DEFAULTS[k]
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# Hero + progress stepper
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(
    """<div class="sw-hero">
    <h1>🧪 Specwright</h1>
    <p>PRD → Test Plan → Test Cases → Playwright TypeScript suite</p>
    </div>""",
    unsafe_allow_html=True,
)

STEPS = [
    ("Requirements", 1),
    ("Test Plan", 2),
    ("Test Cases", 3),
    ("Scope", 4),
    ("Suite", 5),
]
active = current_stage()
stepper_html = '<div class="sw-stepper">'
for label, num in STEPS:
    cls = "done" if num < active else ("active" if num == active else "")
    stepper_html += (
        f'<div class="sw-step {cls}">'
        f'<span class="sw-step-num">{num}</span>{label}'
        f'</div>'
    )
stepper_html += "</div>"
st.markdown(stepper_html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Error banner — collapsed, clickable for details
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.errors:
    n = len(st.session_state.errors)
    latest = st.session_state.errors[-1]
    err_col1, err_col2, err_col3 = st.columns([5, 1, 1])
    with err_col1:
        st.markdown(
            f'<div class="sw-error">'
            f'<span class="sw-error-text">⚠️ {latest["stage"]} — '
            f'{n} error{"s" if n > 1 else ""} occurred. Click for details.</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with err_col2:
        show_details = st.toggle("Details", key="show_error_details")
    with err_col3:
        if st.button("Clear", use_container_width=True, key="clear_errors"):
            st.session_state.errors = []
            st.rerun()

    if show_details:
        tabs = st.tabs([f"#{i + 1} · {e['stage'][:15]}" for i, e in enumerate(st.session_state.errors)])
        for tab, err in zip(tabs, st.session_state.errors):
            with tab:
                st.caption(f"Time: {err['time']}")
                st.error(err["short"])
                with st.expander("Full traceback", expanded=True):
                    st.code(err["detail"], language="text")


# ══════════════════════════════════════════════════════════════════════════════
# Stage ① — Requirements
# ══════════════════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.subheader("① Requirements")

    tab_upload, tab_paste, tab_sample = st.tabs(
        ["📎 Upload file", "✍️ Paste text", "📋 Use sample"]
    )
    with tab_upload:
        uploaded = st.file_uploader(
            "PRD / SRS / BRD", type=["md", "txt"], label_visibility="collapsed",
        )
        if uploaded:
            text = uploaded.read().decode("utf-8", errors="replace")
            if text != st.session_state.prd_text:
                st.session_state.prd_text = text
                reset_from(1)
    with tab_paste:
        pasted = st.text_area(
            "Paste here", height=200, label_visibility="collapsed",
            placeholder="# Feature X\n\n## REQ-1: ...",
            value=st.session_state.prd_text if not uploaded else "",
        )
        if pasted and pasted != st.session_state.prd_text:
            st.session_state.prd_text = pasted
            reset_from(1)
    with tab_sample:
        sample_path = Path(__file__).parent / "examples" / "login_prd.md"
        if sample_path.exists():
            if st.button("Load login PRD sample", use_container_width=True):
                st.session_state.prd_text = sample_path.read_text()
                reset_from(1)
                st.rerun()

    if st.session_state.prd_text:
        with st.expander(f"📖 Preview ({len(st.session_state.prd_text):,} chars)"):
            st.markdown(st.session_state.prd_text)


# ══════════════════════════════════════════════════════════════════════════════
# Stage ② — Test Plan (editable + PDF/DOCX/HTML downloads)
# ══════════════════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.subheader("② Test Plan")

    col1, col2 = st.columns([1, 3])
    with col1:
        can_run = bool(st.session_state.prd_text) and (api_key or provider_choice == "ollama")
        if st.button("▶ Generate plan", type="primary",
                     disabled=not can_run, use_container_width=True):
            llm = _run_safe("Initializing LLM...", get_provider, llm_cfg)
            if llm:
                plan = _run_safe(
                    f"Stage 1 — {provider_choice} writing test plan...",
                    stage1_plan, llm, st.session_state.prd_text, get_workspace(),
                )
                if plan:
                    st.session_state.plan = plan
                    # Export plan in 3 formats immediately
                    _run_safe(
                        "Exporting plan to PDF/DOCX/HTML...",
                        export_plan, plan, get_workspace(), ["html", "pdf", "docx"],
                    )
                    reset_from(2)
                    st.rerun()
        if not can_run:
            if not st.session_state.prd_text:
                st.caption("⚠️ Add requirements first")
            else:
                st.caption("⚠️ Add API key in sidebar")

    with col2:
        if st.session_state.plan:
            st.success(f"✓ Plan generated · {len(st.session_state.plan):,} chars")
        else:
            st.info("Click **Generate plan** to produce an IEEE-829 test plan.")

    if st.session_state.plan:
        with st.expander("📝 Review & edit the plan", expanded=False):
            edited = st.text_area(
                "Markdown", value=st.session_state.plan, height=400,
                label_visibility="collapsed", key="plan_edit",
            )
            save_col, _ = st.columns([1, 5])
            with save_col:
                if st.button("💾 Save edits", use_container_width=True):
                    st.session_state.plan = edited
                    (get_workspace() / "test_plan.md").write_text(edited)
                    # Re-export after edits
                    export_plan(edited, get_workspace(), ["html", "pdf", "docx"])
                    st.toast("Saved & re-exported", icon="✅")

        # Download row — MD / HTML / PDF / DOCX
        st.markdown("##### 📦 Download")
        ws = get_workspace()
        d = st.columns(4)
        _dl_button(d[0], ws / "test_plan.md",   "Markdown", "text/markdown", "plan")
        _dl_button(d[1], ws / "test_plan.html", "HTML",     "text/html",     "plan")
        _dl_button(d[2], ws / "test_plan.pdf",  "PDF",      "application/pdf", "plan")
        _dl_button(d[3], ws / "test_plan.docx", "DOCX",
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                   "plan")


# ══════════════════════════════════════════════════════════════════════════════
# Stage ③ — Test Cases (editable table + 6-format exports)
# ══════════════════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.subheader("③ Test Cases")

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("▶ Generate cases", type="primary",
                     disabled=not st.session_state.plan, use_container_width=True):
            llm = _run_safe("Initializing LLM...", get_provider, llm_cfg)
            if llm:
                cases = _run_safe(
                    f"Stage 2 — {provider_choice} writing test cases (2-pass)...",
                    stage2_cases, llm, st.session_state.prd_text,
                    st.session_state.plan, get_workspace(),
                )
                if cases:
                    st.session_state.cases = cases
                    st.session_state.cases_original = json.loads(json.dumps(cases))
                    _run_safe(
                        "Exporting to 6 formats...",
                        run_exports, cases, get_workspace(),
                        ["csv", "excel", "jira", "testrail", "html", "markdown"],
                    )
                    reset_from(3)
                    st.rerun()
        if not st.session_state.plan:
            st.caption("⚠️ Generate the plan first")

    with col2:
        if st.session_state.cases:
            cases = st.session_state.cases
            automatable = sum(1 for c in cases if c.get("automatable", True))
            st.success(f"✓ {len(cases)} cases · {automatable} automatable")
        else:
            st.info("Click **Generate cases** to produce detailed test cases.")

    if st.session_state.cases:
        cases = st.session_state.cases

        # Metrics row
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", len(cases))
        c2.metric("P0 (critical)", sum(1 for c in cases if c.get("priority") == "P0"))
        c3.metric("UI tests", sum(1 for c in cases if c.get("target") == "ui"))
        c4.metric("API tests", sum(1 for c in cases if c.get("target") == "api"))

        # Editable table via data_editor
        st.markdown("##### ✏️ Edit cases inline (add, remove, modify)")
        st.caption("Changes auto-save and re-export to all 6 formats on every edit.")

        df = pd.DataFrame([{
            "ID": c.get("id", ""),
            "REQ": c.get("requirement_id", ""),
            "Title": c.get("title", ""),
            "Type": c.get("type", ""),
            "Target": c.get("target", ""),
            "Priority": c.get("priority", ""),
            "Page": c.get("page", ""),
            "Expected": c.get("expected", ""),
            "Automatable": c.get("automatable", True),
        } for c in cases])

        edited_df = st.data_editor(
            df,
            use_container_width=True,
            num_rows="dynamic",
            hide_index=True,
            height=420,
            column_config={
                "ID": st.column_config.TextColumn("ID", width="small"),
                "REQ": st.column_config.TextColumn("REQ", width="small"),
                "Title": st.column_config.TextColumn("Title", width="large"),
                "Type": st.column_config.SelectboxColumn("Type", options=[
                    "functional", "negative", "boundary", "security",
                    "accessibility", "performance", "contract",
                ]),
                "Target": st.column_config.SelectboxColumn("Target", options=["ui", "api", "manual"]),
                "Priority": st.column_config.SelectboxColumn("Priority", options=["P0", "P1", "P2"]),
                "Expected": st.column_config.TextColumn("Expected", width="large"),
                "Automatable": st.column_config.CheckboxColumn("Auto?"),
            },
            key="case_editor",
        )

        # Detect changes and re-save/re-export
        edited_cases = []
        for i, row in edited_df.iterrows():
            # Preserve original fields we don't expose in the editor
            original = next((c for c in cases if c.get("id") == row["ID"]), {})
            edited_cases.append({
                **original,
                "id": row["ID"],
                "requirement_id": row["REQ"],
                "title": row["Title"],
                "type": row["Type"],
                "target": row["Target"],
                "priority": row["Priority"],
                "page": row["Page"] or None,
                "expected": row["Expected"],
                "automatable": bool(row["Automatable"]),
            })

        if edited_cases != cases:
            st.session_state.cases = edited_cases
            ws = get_workspace()
            (ws / "test_cases.json").write_text(json.dumps(edited_cases, indent=2))
            try:
                run_exports(edited_cases, ws,
                            ["csv", "excel", "jira", "testrail", "html", "markdown"])
            except Exception as e:
                log_error("Stage 2 edit re-export", e)
            st.toast(f"Saved · {len(edited_cases)} cases", icon="✅")
            st.rerun()

        # Downloads — 6 formats
        st.markdown("##### 📦 Download test cases")
        ws = get_workspace()
        d = st.columns(6)
        _dl_button(d[0], ws / "test_cases.csv",          "CSV",       "text/csv", "cases")
        _dl_button(d[1], ws / "test_cases.xlsx",         "Excel",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "cases")
        _dl_button(d[2], ws / "test_cases.jira.csv",     "Jira",      "text/csv", "cases")
        _dl_button(d[3], ws / "test_cases.testrail.csv", "TestRail",  "text/csv", "cases")
        _dl_button(d[4], ws / "test_cases.html",         "HTML",      "text/html", "cases")
        _dl_button(d[5], ws / "test_cases.md",           "Markdown",  "text/markdown", "cases")


# ══════════════════════════════════════════════════════════════════════════════
# Stage ④ — Scope gate
# ══════════════════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.subheader("④ Automation Scope")

    if not st.session_state.cases:
        st.info("Generate test cases first.")
    else:
        cases = st.session_state.cases

        st.markdown("**Choose what to automate:**")
        saved_scopes = load_saved_scopes()
        preset_cols = st.columns(len(PRESETS) + 1)
        preset_keys = list(PRESETS.keys()) + ["custom"]

        for col, key in zip(preset_cols, preset_keys):
            with col:
                is_active = st.session_state.scope_selection == key
                if key == "custom":
                    count = "—"
                    desc = "Pick filters"
                else:
                    preset = {k: v for k, v in PRESETS[key].items() if k != "description"}
                    count = f"{len(apply_scope(cases, preset))}"
                    desc = PRESETS[key].get("description", "")

                btn_label = f"{'✓ ' if is_active else ''}{key.title()}\n\n{count} cases"
                if st.button(btn_label, key=f"preset_{key}", use_container_width=True,
                             type="primary" if is_active else "secondary"):
                    st.session_state.scope_selection = key
                    st.rerun()
                st.caption(desc)

        if saved_scopes:
            saved_pick = st.selectbox(
                "💾 Saved scopes (scopes.yaml)",
                ["—"] + list(saved_scopes),
                format_func=lambda k: k if k == "—"
                else f"{k} — {describe_scope(saved_scopes[k])}",
            )
            if saved_pick != "—":
                st.session_state.scope_selection = f"saved:{saved_pick}"

        sel_key = st.session_state.scope_selection
        if sel_key == "custom":
            st.markdown("**Custom filters:**")
            automatable = [c for c in cases if c.get("automatable", True)]
            all_prios = sorted({c.get("priority", "?") for c in automatable})
            all_types = sorted({c.get("type", "?") for c in automatable})
            all_tgts = sorted({c.get("target", "?") for c in automatable})
            all_reqs = sorted({c.get("requirement_id", "?") for c in automatable})

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.session_state.custom_priorities = st.multiselect(
                    "Priorities", all_prios, default=all_prios)
            with c2:
                st.session_state.custom_types = st.multiselect(
                    "Types", all_types, default=all_types)
            with c3:
                st.session_state.custom_targets = st.multiselect(
                    "Targets", all_tgts, default=all_tgts)
            with c4:
                custom_reqs = st.multiselect(
                    "Requirements", all_reqs, default=all_reqs)

            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                custom_grep = st.text_input(
                    "Keyword / regex", placeholder="e.g. login|password",
                    help="Matches title, steps and expected result (case-insensitive)")
            with c2:
                custom_limit = st.number_input(
                    "Max cases (0 = no cap)", min_value=0, value=0,
                    help="Caps the selection, keeping highest-priority cases first")
            with c3:
                custom_manual = st.checkbox(
                    "Include manual cases",
                    help="Also select cases flagged automatable=false")

            scope = {
                "priorities": st.session_state.custom_priorities,
                "types": st.session_state.custom_types,
                "targets": st.session_state.custom_targets,
                "requirements": custom_reqs,
                "grep": custom_grep or None,
                "limit": int(custom_limit) or None,
                "include_manual": custom_manual or None,
            }
            scope = {k: v for k, v in scope.items() if v}

            nc1, nc2 = st.columns([2, 1])
            scope_name = nc1.text_input(
                "Save as named scope", placeholder="e.g. payments-smoke")
            if nc2.button("💾 Save scope", disabled=not scope_name,
                          use_container_width=True):
                save_scope(scope_name, scope)
                st.toast(f"Scope '{scope_name}' saved to scopes.yaml", icon="💾")
                st.rerun()
        elif sel_key.startswith("saved:"):
            scope = saved_scopes.get(sel_key[6:], {})
        else:
            scope = {k: v for k, v in PRESETS[sel_key].items()
                     if k != "description"}

        selected = apply_scope(cases, scope)
        cov = coverage_report(cases, selected)

        st.divider()
        if cov["uncovered"]:
            st.warning(
                f"⚠ No cases selected for requirement(s): "
                f"{', '.join(cov['uncovered'])} — widen the scope if unintended.")
        c1, c2 = st.columns([3, 1])
        c1.info(f"**{len(selected)} cases** will be automated "
                f"({len(cov['covered'])}/{cov['total_requirements']} requirements covered) "
                f"· {describe_scope(scope)}")
        with c2:
            if st.button("▶ Generate tests", type="primary",
                         disabled=not selected, use_container_width=True):
                llm = _run_safe("Initializing LLM...", get_provider, llm_cfg)
                if llm:
                    _run_safe(
                        f"Stage 3 — generating {len(selected)} Playwright tests...",
                        stage3_automate, llm, selected, get_workspace(),
                    )
                    st.session_state.stage3_done = True
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# Stage ⑤ — Playwright suite + ZIP download
# ══════════════════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.subheader("⑤ Playwright Suite")

    if not st.session_state.stage3_done:
        st.info("Run Stage ④ to generate Playwright tests.")
    else:
        ws = get_workspace()
        generated = sorted(
            str(p.relative_to(ws))
            for p in ws.rglob("*")
            if p.is_file() and (
                "tests" in p.parts
                or p.name in {
                    "playwright.config.ts", "package.json", "tsconfig.json",
                    ".env.example", "AUTOMATION_REPORT.md",
                }
            )
        )

        st.success(f"✓ {len(generated)} files generated")

        with st.expander("📁 File tree", expanded=True):
            for f in generated:
                st.code(f, language="text")

        ts_files = [f for f in generated if f.endswith((".ts", ".md", ".json"))]
        if ts_files:
            selected_file = st.selectbox("Preview file", ts_files)
            if selected_file:
                content = (ws / selected_file).read_text()
                ext = selected_file.split(".")[-1]
                lang = {"ts": "typescript", "md": "markdown", "json": "json"}.get(ext, "text")
                st.code(content, language=lang, line_numbers=True)

        # ZIP download — everything
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in ws.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(ws))
        zip_buf.seek(0)

        st.download_button(
            "⬇ Download full project (.zip)",
            data=zip_buf.getvalue(),
            file_name="specwright_output.zip",
            mime="application/zip",
            use_container_width=True,
            type="primary",
        )