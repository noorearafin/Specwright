"""Specwright — Streamlit UI for QA Agent.

PRD → Test Plan → Editable Test Cases → Scope Gate → Playwright TS suite.
Default LLM: Groq (free, fast). Fallback: Gemini, Ollama, Anthropic.

Run:  streamlit run app.py
"""
from __future__ import annotations

import io
import json
import os
import re
import traceback
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from providers import get_provider
from stages import stage1_plan, stage2_cases, stage2_regenerate, stage3_automate
from scope import (PRESETS, apply_scope, coverage_report, describe_scope,
                   load_saved_scopes, save_scope)
from exporters import run_exports, export_plan, build_rtm_rows, export_rtm
from integrations.jira_push import push_cases
from schema import validate_cases
from runner import run_suite


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
  @keyframes sw-skeleton {
    0%   { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }

  /* Hero header with animated gradient accent + shine sweep —
     a long slow loop so the shift reads as ambient, not busy */
  .sw-hero {
    position: relative;
    overflow: hidden;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #6d5bd0 100%);
    background-size: 220% 220%;
    animation: sw-gradient-shift 18s ease infinite, sw-fade-in-up 0.6s ease both;
    color: white;
    padding: 1.4rem 1.75rem;
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
    font-size: clamp(1.4rem, 1.1rem + 1.6vw, 1.9rem);
    font-weight: 700;
    letter-spacing: -0.5px;
    line-height: 1.2;
  }
  .sw-hero p {
    color: rgba(255,255,255,0.85);
    margin: 0.3rem 0 0;
    font-size: clamp(0.82rem, 0.74rem + 0.4vw, 0.95rem);
    letter-spacing: 0.01em;
  }

  /* Progress stepper — wraps on narrow screens instead of overflowing */
  .sw-stepper {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 0.5rem;
    margin: 0 0 0.6rem;
    padding: 0.75rem 0 0;
  }
  .sw-step {
    flex: 1;
    min-width: 110px;
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
  .sw-step:nth-child(6) { animation-delay: 0.40s; }
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
  .sw-step.locked {
    border-style: dashed;
    background: #fcfcfd;
    color: #9ca3af;
    cursor: not-allowed;
  }
  .sw-step.locked:hover { transform: none; box-shadow: none; }
  .sw-step.locked .sw-step-num { background: rgba(0,0,0,0.05); }

  /* Thin progress bar under the stepper — width = share of stages done */
  .sw-progress {
    height: 5px;
    border-radius: 999px;
    background: #ede9fe;
    margin: 0 0 1.25rem;
    overflow: hidden;
  }
  .sw-progress-fill {
    position: relative;
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, #667eea, #7c3aed);
    transition: width 0.6s ease;
    overflow: hidden;
  }
  /* Slow shimmer across the filled part only */
  .sw-progress-fill::after {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.45), transparent);
    animation: sw-shine 3.5s ease-in-out infinite;
  }

  /* Section cards - softer borders + gentle entrance + hover lift */
  [data-testid="stVerticalBlock"] > [style*="border"],
  [data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 14px !important;
    animation: sw-fade-in-up 0.5s ease both;
    transition: box-shadow 0.25s ease, transform 0.25s ease;
  }
  [data-testid="stVerticalBlock"] > [style*="border"]:hover,
  [data-testid="stVerticalBlockBorderWrapper"]:hover {
    box-shadow: 0 6px 22px rgba(0, 0, 0, 0.06);
  }

  /* Per-stage accent — one violet family, deepening tone per stage.
     Each stage card holds an invisible .sw-tone-N marker; :has() tints
     the card's left edge. No-op on browsers without :has(). */
  .sw-tone { display: none; }
  .element-container:has(.sw-tone),
  [data-testid="stElementContainer"]:has(.sw-tone) { display: none; }
  [data-testid="stVerticalBlockBorderWrapper"]:has(.sw-tone) {
    border-left: 4px solid #c4b5fd;
    overflow: hidden;
  }
  [data-testid="stVerticalBlockBorderWrapper"]:has(.sw-tone-2) { border-left-color: #a78bfa; }
  [data-testid="stVerticalBlockBorderWrapper"]:has(.sw-tone-3) { border-left-color: #8b5cf6; }
  [data-testid="stVerticalBlockBorderWrapper"]:has(.sw-tone-4) { border-left-color: #7c3aed; }
  [data-testid="stVerticalBlockBorderWrapper"]:has(.sw-tone-5) { border-left-color: #6d28d9; }
  [data-testid="stVerticalBlockBorderWrapper"]:has(.sw-tone-6) { border-left-color: #5b21b6; }

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

  /* Per-case result chips (Run panel) — pop in with a slight stagger */
  .sw-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin: 0.5rem 0 0.75rem;
  }
  .sw-chip {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 0.78rem;
    font-weight: 600;
    white-space: nowrap;
    animation: sw-pop 0.35s ease both;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }
  .sw-chip:hover {
    transform: translateY(-2px) scale(1.06);
    box-shadow: 0 3px 10px rgba(0, 0, 0, 0.12);
  }
  .sw-chip:nth-child(2n)  { animation-delay: 0.05s; }
  .sw-chip:nth-child(3n)  { animation-delay: 0.10s; }
  .sw-chip-pass { background: #d1fae5; color: #065f46; border: 1px solid #10b981; }
  .sw-chip-fail { background: #fee2e2; color: #991b1b; border: 1px solid #f87171; }
  .sw-chip-skip { background: #fef3c7; color: #92400e; border: 1px solid #fbbf24; }
  .sw-chip-none { background: #f3f4f6; color: #6b7280; border: 1px dashed #d1d5db; }

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
  [data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.02em;
  }
  [data-testid="stMetric"] [data-testid="stMetricLabel"] {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #64748b;
  }

  /* Dataframes / data editors — rounded frame to match the cards */
  [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
    border-radius: 12px;
    overflow: hidden;
  }

  /* Static tables — sticky header + gentle row hover */
  [data-testid="stTable"] thead th {
    position: sticky;
    top: 0;
    background: #f8fafc;
    z-index: 1;
  }
  [data-testid="stTable"] tbody tr { transition: background 0.15s ease; }
  [data-testid="stTable"] tbody tr:hover { background: #f5f3ff; }

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
  /* Secondary buttons — quiet ghost style in the same palette */
  .stButton > button[kind="secondary"] {
    background: transparent;
    border: 1px solid #ddd6fe;
    color: #5b21b6;
  }
  .stButton > button[kind="secondary"]:hover {
    border-color: #a78bfa;
    background: #f5f3ff;
    transform: translateY(-1px);
  }
  /* Keyboard focus — visible ring on every button */
  .stButton > button:focus-visible,
  [data-testid="stDownloadButton"] > button:focus-visible {
    outline: 3px solid rgba(124, 58, 237, 0.35);
    outline-offset: 2px;
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
  /* Busy state — spinner sits on a soft pulsing skeleton strip */
  [data-testid="stSpinner"] {
    padding: 0.6rem 0.9rem;
    border-radius: 10px;
    background: linear-gradient(90deg, #f5f3ff 25%, #ede9fe 50%, #f5f3ff 75%);
    background-size: 200% 100%;
    animation: sw-skeleton 1.6s ease-in-out infinite;
  }

  /* Status pills — compile badge and friends */
  .sw-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 0.8rem;
    font-weight: 600;
    animation: sw-pop 0.35s ease both;
  }
  .sw-pill-pass { background: #d1fae5; color: #065f46; border: 1px solid #10b981; }
  .sw-pill-fail { background: #fee2e2; color: #991b1b; border: 1px solid #f87171; }
  .sw-pill-skip { background: #fef3c7; color: #92400e; border: 1px solid #fbbf24; }

  /* Empty states — friendly per-stage placeholders */
  .sw-empty {
    text-align: center;
    padding: 1.6rem 1rem;
    border: 1px dashed #ddd6fe;
    border-radius: 12px;
    background: #fbfaff;
    animation: sw-fade-in 0.5s ease both;
  }
  .sw-empty-icon { font-size: 1.6rem; margin-bottom: 0.3rem; }
  .sw-empty-title { font-weight: 600; color: #4c1d95; font-size: 0.95rem; }
  .sw-empty-hint { color: #6b7280; font-size: 0.85rem; margin-top: 0.2rem; }

  /* Hide the default Streamlit header/menu for a cleaner look */
  #MainMenu {visibility: hidden;}
  footer {visibility: hidden;}

  /* Narrow screens (~400px) — hero, stepper and gutters stay comfortable */
  @media (max-width: 480px) {
    .sw-hero { padding: 1.1rem 1rem; border-radius: 12px; }
    .sw-stepper { gap: 0.35rem; }
    .sw-step {
      min-width: calc(33.3% - 0.35rem);
      font-size: 0.75rem;
      padding: 0.5rem 0.3rem;
    }
    .sw-chips { gap: 0.3rem; }
    .block-container { padding-left: 1rem !important; padding-right: 1rem !important; }
  }

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
    "project": None,            # active project slug under PROJECTS_DIR
    "stage3_done": False,
    "run_outcome": None,        # last run_suite() outcome dict
    "errors": [],               # list of {stage, short, detail, time}
}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)

# Projects live next to the app so work survives refreshes and restarts
PROJECTS_DIR = Path(__file__).parent / "projects"


def slugify(name: str) -> str:
    """Fold a project name to a safe folder slug: lowercase, [a-z0-9-]."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "default"


def list_projects() -> list[str]:
    """Existing project folders, sorted — empty on a fresh checkout."""
    if not PROJECTS_DIR.is_dir():
        return []
    return sorted(p.name for p in PROJECTS_DIR.iterdir() if p.is_dir())


def get_workspace() -> Path:
    """Folder of the active project — created on first write ("default"
    when the user never picked one)."""
    ws = PROJECTS_DIR / (st.session_state.project or "default")
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def reset_from(stage: int) -> None:
    if stage <= 1:
        st.session_state.plan = None
    if stage <= 2:
        st.session_state.cases = None
        st.session_state.cases_original = None
    if stage <= 3:
        st.session_state.stage3_done = False
        st.session_state.run_outcome = None


def load_project(slug: str) -> None:
    """Switch to project <slug> and rehydrate session state from its files.

    Each saved artifact restores its stage — prd.md, test_plan.md,
    test_cases.json, playwright.config.ts — so the user resumes exactly
    where they left off after a refresh, restart or project switch.
    """
    st.session_state.project = slug
    st.session_state.prd_text = ""
    reset_from(1)
    # Drop stale editor widget state so it re-seeds from the new project
    for wk in ("plan_edit", "case_editor"):
        st.session_state.pop(wk, None)

    ws = PROJECTS_DIR / slug
    prd_path = ws / "prd.md"
    if prd_path.exists():
        st.session_state.prd_text = prd_path.read_text()
    plan_path = ws / "test_plan.md"
    if plan_path.exists():
        st.session_state.plan = plan_path.read_text()
    cases_path = ws / "test_cases.json"
    if cases_path.exists():
        try:
            cases = json.loads(cases_path.read_text())
        except json.JSONDecodeError:
            cases = None
        if isinstance(cases, list) and cases:
            # Re-validate on load: the file may have been hand-edited and
            # exporters/Stage 3 assume schema-complete cases.
            cases = validate_cases(cases)
            st.session_state.cases = cases
            st.session_state.cases_original = json.loads(json.dumps(cases))
    if (ws / "playwright.config.ts").exists():
        st.session_state.stage3_done = True


# On app start (fresh session) pick a project and rehydrate it:
# "default" when present or nothing exists yet, else the first saved one.
if st.session_state.project is None:
    _existing = list_projects()
    _initial = "default" if ("default" in _existing or not _existing) else _existing[0]
    if (PROJECTS_DIR / _initial).is_dir():
        load_project(_initial)
    else:
        st.session_state.project = _initial


def current_stage() -> int:
    """Determine active step (1-6) based on what's done."""
    if st.session_state.run_outcome:
        return 6
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


def _empty_state(icon: str, title: str, hint: str) -> None:
    """Friendly placeholder shown before a stage has anything to display."""
    st.markdown(
        f'<div class="sw-empty">'
        f'<div class="sw-empty-icon">{icon}</div>'
        f'<div class="sw-empty-title">{title}</div>'
        f'<div class="sw-empty-hint">{hint}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _save_case_details(case_id: str, steps: list[dict],
                       preconditions: list[str]) -> None:
    """Write steps/preconditions into the matching case, persist and re-export."""
    for c in st.session_state.cases or []:
        if c.get("id") == case_id:
            c["steps"] = steps
            c["preconditions"] = preconditions
            break
    ws = get_workspace()
    (ws / "test_cases.json").write_text(
        json.dumps(st.session_state.cases, indent=2))
    try:
        run_exports(st.session_state.cases, ws,
                    ["csv", "excel", "jira", "testrail", "html", "markdown", "rtm"])
    except Exception as e:  # noqa: BLE001
        log_error("Case detail re-export", e)


def _case_detail_body(case: dict) -> None:
    """Steps + preconditions editor for one case (dialog or expander body)."""
    case_id = case.get("id", "")
    steps_df = pd.DataFrame(
        [{"Action": s.get("action", ""), "Data": s.get("data") or ""}
         for s in case.get("steps") or []],
        columns=["Action", "Data"],
    )
    edited_steps = st.data_editor(
        steps_df,
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "Action": st.column_config.TextColumn("Action", width="large"),
            "Data": st.column_config.TextColumn("Data"),
        },
        key=f"steps_editor_{case_id}",
    )
    precond_text = st.text_area(
        "Preconditions (one per line)",
        value="\n".join(case.get("preconditions") or []),
        key=f"precond_{case_id}",
    )
    if st.button("💾 Save case details", type="primary",
                 key=f"save_detail_{case_id}"):
        steps = []
        for _, srow in edited_steps.iterrows():
            action = "" if pd.isna(srow["Action"]) else str(srow["Action"]).strip()
            data = "" if pd.isna(srow["Data"]) else str(srow["Data"]).strip()
            if not action and not data:
                continue  # blank row left behind by the editor
            steps.append({"action": action, "data": data or None})
        preconditions = [ln.strip() for ln in precond_text.splitlines()
                         if ln.strip()]
        _save_case_details(case_id, steps, preconditions)
        st.toast(f"Saved {case_id} steps & preconditions", icon="✅")
        st.rerun()


if hasattr(st, "dialog"):
    @st.dialog("Edit steps & preconditions", width="large")
    def _case_detail_editor(case: dict) -> None:
        st.caption(f"{case.get('id', '')} — {case.get('title', '')}")
        _case_detail_body(case)


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
    st.markdown("### 📁 Project")
    projects = list_projects()
    current = st.session_state.project
    options = projects if current in projects else [current] + projects
    picked = st.selectbox(
        "Active project",
        options,
        index=options.index(current),
        help="Each project keeps its PRD, plan, cases and suite "
             "under ./projects/ — switching rehydrates where you left off.",
    )
    if picked != current:
        load_project(picked)
        st.rerun()

    new_project = st.text_input(
        "New project",
        placeholder="e.g. checkout-flow",
        help="Name is slugified to lowercase letters, digits and hyphens",
    )
    if st.button("➕ Create project", use_container_width=True,
                 disabled=not new_project.strip()):
        slug = slugify(new_project)
        (PROJECTS_DIR / slug).mkdir(parents=True, exist_ok=True)
        load_project(slug)
        st.rerun()

    st.divider()
    with st.expander("🔗 Jira integration"):
        st.text_input(
            "Base URL",
            placeholder="https://yourteam.atlassian.net",
            key="jira_base_url",
            help="Your Jira Cloud (or Server) root URL",
        )
        st.text_input(
            "Project key",
            placeholder="e.g. QA",
            key="jira_project_key",
        )
        st.caption("Tokens never pass through the UI — set the `JIRA_EMAIL` "
                   "and `JIRA_TOKEN` env vars before launching the app.")

    st.divider()
    st.markdown("### 🗂 Workspace")
    st.code(str(PROJECTS_DIR / current), language="text")
    if st.button("↺ Reload project from disk", use_container_width=True,
                 help="Discard unsaved session state and rehydrate from "
                      "the project's saved files"):
        load_project(current)
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
    ("Run", 6),
]
active = current_stage()
stepper_html = '<div class="sw-stepper">'
for label, num in STEPS:
    if num < active:
        cls, marker = "done", "✓"
    elif num == active:
        cls, marker = "active", str(num)
    else:
        cls, marker = "locked", str(num)
    stepper_html += (
        f'<div class="sw-step {cls}">'
        f'<span class="sw-step-num">{marker}</span>{label}'
        f'</div>'
    )
stepper_html += "</div>"
# Thin progress bar under the stepper — share of stages completed so far
pct = round((active - 1) / (len(STEPS) - 1) * 100)
stepper_html += (
    f'<div class="sw-progress" role="progressbar" aria-valuenow="{pct}" '
    f'aria-valuemin="0" aria-valuemax="100">'
    f'<div class="sw-progress-fill" style="width:{pct}%"></div></div>'
)
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
    # Invisible marker — CSS tints this card's left-edge accent
    st.markdown('<span class="sw-tone sw-tone-1"></span>', unsafe_allow_html=True)

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
                (get_workspace() / "prd.md").write_text(text)
    with tab_paste:
        pasted = st.text_area(
            "Paste here", height=200, label_visibility="collapsed",
            placeholder="# Feature X\n\n## REQ-1: ...",
            value=st.session_state.prd_text if not uploaded else "",
        )
        if pasted and pasted != st.session_state.prd_text:
            st.session_state.prd_text = pasted
            reset_from(1)
            (get_workspace() / "prd.md").write_text(pasted)
    with tab_sample:
        sample_path = Path(__file__).parent / "examples" / "login_prd.md"
        if sample_path.exists():
            if st.button("Load login PRD sample", use_container_width=True):
                st.session_state.prd_text = sample_path.read_text()
                reset_from(1)
                (get_workspace() / "prd.md").write_text(st.session_state.prd_text)
                st.rerun()

    if st.session_state.prd_text:
        with st.expander(f"📖 Preview ({len(st.session_state.prd_text):,} chars)"):
            st.markdown(st.session_state.prd_text)


# ══════════════════════════════════════════════════════════════════════════════
# Stage ② — Test Plan (editable + PDF/DOCX/HTML downloads)
# ══════════════════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.subheader("② Test Plan")
    st.markdown('<span class="sw-tone sw-tone-2"></span>', unsafe_allow_html=True)

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
            _empty_state("📝", "No plan yet",
                         "Click <b>Generate plan</b> to draft an IEEE-829 "
                         "test plan from your requirements.")

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
# Stage ③ — Test Cases (editable table + 7-format exports)
# ══════════════════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.subheader("③ Test Cases")
    st.markdown('<span class="sw-tone sw-tone-3"></span>', unsafe_allow_html=True)

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
                        "Exporting to 7 formats...",
                        run_exports, cases, get_workspace(),
                        ["csv", "excel", "jira", "testrail", "html", "markdown", "rtm"],
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
            _empty_state("🧾", "No test cases yet",
                         "Click <b>Generate cases</b> to turn the plan into "
                         "detailed, editable test cases.")

    if st.session_state.cases:
        cases = st.session_state.cases

        # Coverage integrity — flag requirements that generated zero cases
        # (from generation_report.json) and offer a targeted regeneration.
        report_path = get_workspace() / "generation_report.json"
        gen_report = {}
        if report_path.exists():
            try:
                gen_report = json.loads(report_path.read_text())
            except json.JSONDecodeError:
                gen_report = {}
        reqs_present = {c.get("requirement_id") for c in cases}
        missing = {
            req: entry for req, entry in gen_report.items()
            if (not entry.get("generated") or entry.get("error"))
            and req not in reqs_present
        }
        if missing:
            bullet_list = "\n".join(
                f"- **{req}** — estimated {entry.get('estimated', '?')} cases, "
                f"got 0{' · ' + str(entry['error']) if entry.get('error') else ''}"
                for req, entry in sorted(missing.items())
            )
            st.error(f"⚠️ Requirements with **zero generated cases**:\n\n{bullet_list}")
            if st.button("🔁 Regenerate missing", key="regen_missing"):
                llm = _run_safe("Initializing LLM...", get_provider, llm_cfg)
                if llm:
                    per_req = {req: int(entry.get("estimated") or 3)
                               for req, entry in missing.items()}
                    results = _run_safe(
                        f"Regenerating cases for {', '.join(per_req)}...",
                        stage2_regenerate, llm, st.session_state.prd_text,
                        st.session_state.plan, per_req, get_workspace(),
                    )
                    if results is not None:
                        merged = cases + [c for chunk in results.values()
                                          for c in chunk]
                        for idx, case in enumerate(merged, 1):
                            case["id"] = f"TC-{idx:03d}"
                        st.session_state.cases = merged
                        ws = get_workspace()
                        (ws / "test_cases.json").write_text(
                            json.dumps(merged, indent=2))
                        _run_safe(
                            "Re-exporting to 7 formats...",
                            run_exports, merged, ws,
                            ["csv", "excel", "jira", "testrail", "html", "markdown", "rtm"],
                        )
                        st.rerun()

        # Metrics row
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", len(cases))
        c2.metric("P0 (critical)", sum(1 for c in cases if c.get("priority") == "P0"))
        c3.metric("UI tests", sum(1 for c in cases if c.get("target") == "ui"))
        c4.metric("API tests", sum(1 for c in cases if c.get("target") == "api"))

        # Requirement traceability — same rows as the RTM export, kept
        # permanently visible so coverage gaps never hide behind a toast.
        st.markdown("##### 🧭 Requirement coverage (RTM)")
        rtm_rows = build_rtm_rows(cases, get_workspace())
        rtm_df = pd.DataFrame([{
            "Requirement": r["requirement"],
            "Coverage": "⚠️ GAP" if r["gap"] else "✓ OK",
            "Cases": r["total"],
            "P0": r["p0"],
            "P1": r["p1"],
            "P2": r["p2"],
            "Auto": r["automatable"],
            "Manual": r["manual"],
            "Case IDs": ", ".join(r["case_ids"]),
        } for r in rtm_rows])
        st.dataframe(rtm_df, use_container_width=True, hide_index=True)

        # Editable table via data_editor
        st.markdown("##### ✏️ Edit cases inline (add, remove, modify)")
        st.caption("Changes auto-save and re-export to all 7 formats on every edit.")

        df = pd.DataFrame([{
            "ID": c.get("id", ""),
            "REQ": c.get("requirement_id", ""),
            "Title": c.get("title", ""),
            "Steps": len(c.get("steps") or []),
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
                "Steps": st.column_config.NumberColumn(
                    "Steps", width="small",
                    help="Step count — 0 means the case has no steps yet"),
                "Type": st.column_config.SelectboxColumn("Type", options=[
                    "functional", "negative", "boundary", "security",
                    "accessibility", "performance", "contract",
                ]),
                "Target": st.column_config.SelectboxColumn("Target", options=["ui", "api", "manual"]),
                "Priority": st.column_config.SelectboxColumn("Priority", options=["P0", "P1", "P2"]),
                "Expected": st.column_config.TextColumn("Expected", width="large"),
                "Automatable": st.column_config.CheckboxColumn("Auto?"),
            },
            disabled=["Steps"],
            key="case_editor",
        )

        # Detect changes and re-save/re-export
        edited_cases = []
        for i, row in edited_df.iterrows():
            # Preserve original fields we don't expose in the editor.
            # Rows added in the grid start with empty steps/preconditions so
            # exporters and Stage 3 never see missing fields.
            original = next((c for c in cases if c.get("id") == row["ID"]), {})
            edited_cases.append({
                "steps": [],
                "preconditions": [],
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
                            ["csv", "excel", "jira", "testrail", "html", "markdown", "rtm"])
            except Exception as e:
                log_error("Stage 2 edit re-export", e)
            st.toast(f"Saved · {len(edited_cases)} cases", icon="✅")
            st.rerun()

        # Per-case detail editor — steps & preconditions don't fit the grid
        # above, so edit them here (dialog where supported, expander otherwise).
        st.markdown("##### 🪜 Steps & preconditions")
        st.caption("Pick a case to edit its steps and preconditions — "
                   "the grid above only shows the step count.")
        id_titles = {c.get("id", ""): c.get("title", "") for c in cases}
        dc1, dc2 = st.columns([3, 1])
        detail_id = dc1.selectbox(
            "Case to edit",
            list(id_titles),
            format_func=lambda cid: f"{cid} — {(id_titles.get(cid) or '')[:70]}",
            label_visibility="collapsed",
            key="detail_case_pick",
        )
        detail_case = next(
            (c for c in cases if c.get("id") == detail_id), None)
        if detail_case is not None:
            if hasattr(st, "dialog"):
                with dc2:
                    if st.button("✏️ Edit details", use_container_width=True,
                                 key="open_detail_editor"):
                        _case_detail_editor(detail_case)
            else:
                with st.expander(f"✏️ Edit {detail_id}", expanded=False):
                    _case_detail_body(detail_case)

        # Downloads — 7 formats, plus the direct Jira upsert
        st.markdown("##### 📦 Download test cases")
        ws = get_workspace()
        d = st.columns(8)
        _dl_button(d[0], ws / "test_cases.csv",          "CSV",       "text/csv", "cases")
        _dl_button(d[1], ws / "test_cases.xlsx",         "Excel",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "cases")
        _dl_button(d[2], ws / "test_cases.jira.csv",     "Jira",      "text/csv", "cases")
        _dl_button(d[3], ws / "test_cases.testrail.csv", "TestRail",  "text/csv", "cases")
        _dl_button(d[4], ws / "test_cases.html",         "HTML",      "text/html", "cases")
        _dl_button(d[5], ws / "test_cases.md",           "Markdown",  "text/markdown", "cases")
        _dl_button(d[6], ws / "test_rtm.csv",            "RTM",       "text/csv", "cases")

        # Push straight into Jira — upserts by specwright-<TC-ID> label so
        # repeated pushes update issues instead of duplicating them.
        jira_cfg = {
            "base_url": st.session_state.get("jira_base_url", ""),
            "project_key": st.session_state.get("jira_project_key", ""),
        }
        jira_ready = bool(jira_cfg["base_url"] and jira_cfg["project_key"])
        with d[7]:
            if st.button("🚀 Push to Jira", use_container_width=True,
                         key="push_jira", disabled=not jira_ready,
                         help="Upsert every case as a Jira issue — set the "
                              "base URL and project key in the sidebar"):
                result = _run_safe("Pushing cases to Jira...",
                                   push_cases, cases, jira_cfg)
                if result:
                    # Persist the issue keys stamped on each case
                    (ws / "test_cases.json").write_text(
                        json.dumps(cases, indent=2))
                    st.toast(f"Jira: {result['created']} created, "
                             f"{result['updated']} updated", icon="✅")
        if not jira_ready:
            st.caption("🔗 Configure Jira in the sidebar to enable the push.")


# ══════════════════════════════════════════════════════════════════════════════
# Stage ④ — Scope gate
# ══════════════════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.subheader("④ Automation Scope")
    st.markdown('<span class="sw-tone sw-tone-4"></span>', unsafe_allow_html=True)

    if not st.session_state.cases:
        _empty_state("🎯", "Nothing to scope yet",
                     "Generate test cases in Stage ③, then choose "
                     "what to automate here.")
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
            overwrite = st.checkbox(
                "Overwrite existing tests",
                help="Regenerate every selected file, even hand-edited ones. "
                     "Unchecked, only files whose cases changed are rewritten "
                     "(hand-edited files get a .new sibling instead)")
            if st.button("▶ Generate tests", type="primary",
                         disabled=not selected, use_container_width=True):
                llm = _run_safe("Initializing LLM...", get_provider, llm_cfg)
                if llm:
                    result = _run_safe(
                        f"Stage 3 — generating {len(selected)} Playwright tests...",
                        stage3_automate, llm, selected, get_workspace(),
                        all_cases=cases,
                        regen="all" if overwrite else "changed",
                    )
                    # None means _run_safe caught an error — don't mark done
                    if result is not None:
                        st.session_state.stage3_done = True
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# Stage ⑤ — Playwright suite + ZIP download
# ══════════════════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.subheader("⑤ Playwright Suite")
    st.markdown('<span class="sw-tone sw-tone-5"></span>', unsafe_allow_html=True)

    if not st.session_state.stage3_done:
        _empty_state("🎭", "No suite generated yet",
                     "Pick a scope in Stage ④ and generate tests — the "
                     "Playwright project appears here, ready to download.")
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

        # Compile-status badge from the Stage-3 verify gate (when it ran)
        verify_path = ws / "verify_report.json"
        if verify_path.exists():
            try:
                verify = json.loads(verify_path.read_text())
            except json.JSONDecodeError:
                verify = {}
            status = verify.get("status")
            if status == "passed":
                st.markdown(
                    '<span class="sw-pill sw-pill-pass">✓ Compile check '
                    'passed</span>', unsafe_allow_html=True)
                st.caption("tsc and `playwright test --list` are clean")
            elif status == "failed":
                broken = sorted(verify.get("errors", {}))
                st.markdown(
                    '<span class="sw-pill sw-pill-fail">✕ Compile check '
                    'failed</span>', unsafe_allow_html=True)
                st.caption(
                    f"{len(broken)} file(s) still broken after repair: "
                    f"{', '.join(f'`{f}`' for f in broken) or 'see AUTOMATION_REPORT.md'}")
            elif status == "skipped":
                reason = next(
                    (s.get("detail", "") for s in verify.get("steps", [])
                     if not s.get("ok")), "toolchain unavailable")
                st.markdown(
                    '<span class="sw-pill sw-pill-skip">◌ Compile check '
                    'skipped</span>', unsafe_allow_html=True)
                st.caption(reason)

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


# ══════════════════════════════════════════════════════════════════════════════
# Stage ⑥ — Run the suite, map results back to TC-IDs
# ══════════════════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.subheader("⑥ Run & Results")
    st.markdown('<span class="sw-tone sw-tone-6"></span>', unsafe_allow_html=True)

    if not st.session_state.stage3_done:
        _empty_state("🏁", "Nothing to run yet",
                     "Generate the Playwright suite in Stage ④ — results "
                     "map back to their TC-IDs here.")
    else:
        c1, c2, c3 = st.columns([2, 2, 1])
        base_url = c1.text_input(
            "BASE_URL", placeholder="http://localhost:3000",
            help="Passed to the suite as the BASE_URL env var (UI tests)")
        api_url = c2.text_input(
            "API_URL", placeholder="http://localhost:3000/api",
            help="Passed to the suite as the API_URL env var (API tests)")
        with c3:
            st.markdown('<div style="height:1.75rem"></div>', unsafe_allow_html=True)
            run_clicked = st.button("▶ Run suite", type="primary",
                                    use_container_width=True)

        if run_clicked:
            outcome = _run_safe(
                "Running Playwright suite (npx playwright test)...",
                run_suite, get_workspace(),
                base_url=base_url or None, api_url=api_url or None,
            )
            if outcome is not None:
                st.session_state.run_outcome = outcome
                if outcome["status"] == "completed" and st.session_state.cases:
                    # Persist the latest outcome on each case and re-export
                    # the RTM so it gains the Last Run column.
                    results = outcome["results"]
                    for case in st.session_state.cases:
                        if case.get("id") in results:
                            case["last_result"] = results[case["id"]]
                    ws = get_workspace()
                    (ws / "test_cases.json").write_text(
                        json.dumps(st.session_state.cases, indent=2))
                    try:
                        export_rtm(st.session_state.cases, ws,
                                   results={tc: r["status"]
                                            for tc, r in results.items()})
                    except Exception as e:  # noqa: BLE001
                        log_error("Run — RTM re-export", e)
                st.rerun()

        outcome = st.session_state.run_outcome
        if outcome and outcome["status"] == "error":
            st.error(f"🔴 Run failed: {outcome['error']}")
        elif outcome:
            results = outcome["results"]
            counts = Counter(r["status"] for r in results.values())

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Executed", len(results))
            m2.metric("Passed", counts.get("passed", 0))
            m3.metric("Failed", counts.get("failed", 0))
            m4.metric("Skipped", counts.get("skipped", 0))

            if not results:
                st.warning("Suite ran, but no TC-IDs were found in the test "
                           "titles — nothing to map back to cases.")
            else:
                # Per-case status chips (cases that never ran show as grey)
                st.markdown("##### 🏷 Per-case results")
                chip_cls = {"passed": "pass", "failed": "fail",
                            "skipped": "skip"}
                known_ids = {c.get("id") for c in (st.session_state.cases or [])}
                chips = []
                for tc in sorted(known_ids | set(results)):
                    r = results.get(tc)
                    if r:
                        cls = chip_cls.get(r["status"], "none")
                        label = f"{tc} · {r['status']} · {r['duration_ms']:,}ms"
                    else:
                        cls = "none"
                        label = f"{tc} · not run"
                    chips.append(f'<span class="sw-chip sw-chip-{cls}">{label}</span>')
                st.markdown(f'<div class="sw-chips">{"".join(chips)}</div>',
                            unsafe_allow_html=True)

                failed_cases = {tc: r for tc, r in results.items()
                                if r["status"] == "failed"}
                if failed_cases:
                    with st.expander(f"🔍 Failure details ({len(failed_cases)})"):
                        for tc, r in sorted(failed_cases.items()):
                            st.markdown(f"**{tc}**")
                            st.code(r["error"] or "no error message captured",
                                    language="text")

            # Per-requirement roll-up (joined through test_cases.json)
            if outcome["aggregate"]:
                st.markdown("##### 🧭 Per-requirement summary")
                status_label = {"passed": "🟢 passed", "failed": "🔴 failed",
                                "skipped": "🟡 skipped"}
                agg_df = pd.DataFrame([{
                    "Requirement": req,
                    "Status": status_label.get(e["status"], "⚪ not run"),
                    "Passed": e["passed"],
                    "Failed": e["failed"],
                    "Skipped": e["skipped"],
                    "Not run": e["not_run"],
                    "Total": e["total"],
                } for req, e in sorted(outcome["aggregate"].items())])
                st.dataframe(agg_df, use_container_width=True, hide_index=True)

            # Downloads — raw mapping + the RTM with its Last Run column
            ws = get_workspace()
            d1, d2 = st.columns(2)
            _dl_button(d1, ws / "results.json", "results.json",
                       "application/json", "run")
            _dl_button(d2, ws / "test_rtm.csv", "RTM (with Last Run)",
                       "text/csv", "run")