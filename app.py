"""QA Agent — Streamlit UI

Single-page app that walks through the pipeline:
  1. Configure LLM provider
  2. Upload/paste PRD
  3. Generate test plan
  4. Generate test cases → download in 6 formats
  5. Pick scope (preset or custom)
  6. Generate Playwright suite → download ZIP

Run:  streamlit run app.py
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import traceback
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

from providers import get_provider
from stages import stage1_plan, stage2_cases, stage3_automate
from scope import PRESETS, apply_scope
from exporters import run_exports


# ──────────────────────────────────────────────────────────────────────────────
# Page setup & state
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="QA Agent",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

DEFAULTS = {
    "prd_text": "",
    "plan": None,
    "cases": None,
    "scope_selection": "regression",
    "custom_priorities": [],
    "custom_types": [],
    "custom_targets": [],
    "workspace": None,           # Path to temp dir with everything
    "stage3_done": False,
    "error": None,
}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)


def get_workspace() -> Path:
    if st.session_state.workspace is None:
        st.session_state.workspace = Path(tempfile.mkdtemp(prefix="qa_agent_"))
    return st.session_state.workspace


def reset_from(stage: int) -> None:
    """Clear downstream state when upstream inputs change."""
    if stage <= 1:
        st.session_state.plan = None
    if stage <= 2:
        st.session_state.cases = None
    if stage <= 3:
        st.session_state.stage3_done = False


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar — provider config
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ LLM Provider")
    provider_choice = st.selectbox(
        "Provider",
        ["gemini", "groq", "ollama", "anthropic"],
        index=0,
        help="Gemini is the recommended free default.",
    )

    MODEL_DEFAULTS = {
        "gemini": "gemini-2.5-flash",
        "groq": "llama-3.3-70b-versatile",
        "ollama": "llama3.1:8b",
        "anthropic": "claude-sonnet-4-6",
    }
    KEY_ENV = {
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
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
                help=f"Or set {env_name} env var and restart the app",
            )
    else:
        st.info("Ollama runs locally — make sure `ollama serve` is running.")

    temperature = st.slider("Temperature", 0.0, 1.0, 0.2, 0.1,
                            help="Lower = more deterministic.")

    llm_cfg = {
        "provider": provider_choice,
        "model": model,
        "api_key": api_key or None,
        "temperature": temperature,
    }

    st.divider()
    st.markdown("### 🗂 Workspace")
    ws = get_workspace()
    st.code(str(ws), language="text")
    if st.button("🗑 Reset workspace", use_container_width=True):
        for k in DEFAULTS:
            st.session_state[k] = DEFAULTS[k]
        st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# Main header
# ──────────────────────────────────────────────────────────────────────────────
st.title("🧪 QA Agent")
st.caption("PRD → Test Plan → Test Cases → Playwright TypeScript suite")

if st.session_state.error:
    st.error(st.session_state.error)
    if st.button("Dismiss error"):
        st.session_state.error = None
        st.rerun()


def _run_safe(label: str, fn, *args, **kwargs):
    """Wrap a stage call; show spinner; capture errors to session."""
    try:
        with st.spinner(label):
            return fn(*args, **kwargs)
    except SystemExit as e:
        st.session_state.error = f"Setup issue: {e}"
        st.rerun()
    except Exception as e:  # noqa: BLE001
        st.session_state.error = f"{type(e).__name__}: {e}\n\n```\n{traceback.format_exc()}\n```"
        st.rerun()


def _dl_button(col, path: Path, label: str, mime: str) -> None:
    """Render a download button for a file in the workspace, if it exists."""
    if path.exists():
        col.download_button(
            f"⬇ {label}",
            data=path.read_bytes(),
            file_name=path.name,
            mime=mime,
            use_container_width=True,
            key=f"dl_{path.name}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Stage 0 — PRD input
# ══════════════════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.subheader("① Requirements")

    tab_upload, tab_paste, tab_sample = st.tabs(
        ["📎 Upload file", "✍️ Paste text", "📋 Use sample"]
    )
    with tab_upload:
        uploaded = st.file_uploader("PRD / SRS / BRD", type=["md", "txt"],
                                    label_visibility="collapsed")
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
        with st.expander(f"Preview ({len(st.session_state.prd_text)} chars)"):
            st.markdown(st.session_state.prd_text)


# ══════════════════════════════════════════════════════════════════════════════
# Stage 1 — Test Plan
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
                    reset_from(2)
                    st.rerun()
        if not can_run and st.session_state.prd_text:
            st.caption("⚠️ Add API key above")
        elif not st.session_state.prd_text:
            st.caption("⚠️ Add requirements first")

    with col2:
        if st.session_state.plan:
            st.success(f"✓ Plan generated ({len(st.session_state.plan)} chars)")
        else:
            st.info("No plan yet.")

    if st.session_state.plan:
        with st.expander("📄 View / edit test plan", expanded=False):
            edited = st.text_area(
                "Markdown", value=st.session_state.plan, height=400,
                label_visibility="collapsed", key="plan_edit",
            )
            c1, c2 = st.columns([1, 5])
            with c1:
                if st.button("💾 Save edits", use_container_width=True):
                    st.session_state.plan = edited
                    (get_workspace() / "test_plan.md").write_text(edited)
                    st.toast("Saved")
            with c2:
                st.download_button(
                    "⬇ Download test_plan.md",
                    data=edited, file_name="test_plan.md", mime="text/markdown",
                    use_container_width=True,
                )


# ══════════════════════════════════════════════════════════════════════════════
# Stage 2 — Test Cases + Exports
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
                    f"Stage 2 — {provider_choice} writing test cases...",
                    stage2_cases, llm, st.session_state.prd_text,
                    st.session_state.plan, get_workspace(),
                )
                if cases:
                    st.session_state.cases = cases
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
            st.success(f"✓ {len(st.session_state.cases)} cases generated")
        else:
            st.info("No cases yet.")

    if st.session_state.cases:
        cases = st.session_state.cases

        # Summary chips
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", len(cases))
        c2.metric("Automatable", sum(1 for c in cases if c.get("automatable", True)))
        c3.metric("UI", sum(1 for c in cases if c.get("target") == "ui"))
        c4.metric("API", sum(1 for c in cases if c.get("target") == "api"))

        # Filterable table
        df = pd.DataFrame([{
            "ID": c.get("id", ""),
            "REQ": c.get("requirement_id", ""),
            "Title": c.get("title", ""),
            "Type": c.get("type", ""),
            "Target": c.get("target", ""),
            "Priority": c.get("priority", ""),
            "Auto": "✓" if c.get("automatable", True) else "—",
        } for c in cases])

        with st.expander(f"📋 Table ({len(cases)} cases)", expanded=True):
            st.dataframe(df, use_container_width=True, hide_index=True, height=400)

        # Downloads — 6 formats
        st.markdown("##### 📦 Download")
        ws = get_workspace()
        d = st.columns(6)
        _dl_button(d[0], ws / "test_cases.csv",          "CSV",       "text/csv")
        _dl_button(d[1], ws / "test_cases.xlsx",         "Excel",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        _dl_button(d[2], ws / "test_cases.jira.csv",     "Jira",      "text/csv")
        _dl_button(d[3], ws / "test_cases.testrail.csv", "TestRail",  "text/csv")
        _dl_button(d[4], ws / "test_cases.html",         "HTML",      "text/html")
        _dl_button(d[5], ws / "test_cases.md",           "Markdown",  "text/markdown")


# ══════════════════════════════════════════════════════════════════════════════
# Stage 3 — Scope gate + automation
# ══════════════════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.subheader("④ Automation Scope")

    if not st.session_state.cases:
        st.info("Generate test cases first.")
    else:
        cases = st.session_state.cases
        automatable = [c for c in cases if c.get("automatable", True)]

        # Preset cards
        st.markdown("**Choose a preset:**")
        preset_cols = st.columns(len(PRESETS) + 1)
        preset_keys = list(PRESETS.keys()) + ["custom"]

        for col, key in zip(preset_cols, preset_keys):
            with col:
                is_active = st.session_state.scope_selection == key
                if key == "custom":
                    count_label = "—"
                    desc = "Pick filters below"
                else:
                    preset = {k: v for k, v in PRESETS[key].items() if k != "description"}
                    count_label = f"{len(apply_scope(cases, preset))} cases"
                    desc = PRESETS[key].get("description", "")

                btn_label = f"{'✓ ' if is_active else ''}{key.title()}\n\n{count_label}"
                if st.button(btn_label, key=f"preset_{key}", use_container_width=True,
                             type="primary" if is_active else "secondary"):
                    st.session_state.scope_selection = key
                    st.rerun()
                st.caption(desc)

        # Custom filters
        if st.session_state.scope_selection == "custom":
            st.markdown("**Custom filters:**")
            all_prios = sorted({c.get("priority", "?") for c in automatable})
            all_types = sorted({c.get("type", "?") for c in automatable})
            all_tgts = sorted({c.get("target", "?") for c in automatable})

            c1, c2, c3 = st.columns(3)
            with c1:
                st.session_state.custom_priorities = st.multiselect(
                    "Priorities", all_prios, default=all_prios)
            with c2:
                st.session_state.custom_types = st.multiselect(
                    "Types", all_types, default=all_types)
            with c3:
                st.session_state.custom_targets = st.multiselect(
                    "Targets", all_tgts, default=all_tgts)

            scope = {
                "priorities": st.session_state.custom_priorities,
                "types": st.session_state.custom_types,
                "targets": st.session_state.custom_targets,
            }
        else:
            scope = {k: v for k, v in PRESETS[st.session_state.scope_selection].items()
                     if k != "description"}

        selected = apply_scope(cases, scope)

        st.divider()
        c1, c2 = st.columns([3, 1])
        c1.info(f"**{len(selected)} cases** will be automated.")
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
# Stage 4 — Results & download
# ══════════════════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.subheader("⑤ Playwright Suite")

    if not st.session_state.stage3_done:
        st.info("Run Stage 3 to see generated files here.")
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

        # Preview any file
        ts_files = [f for f in generated if f.endswith((".ts", ".md", ".json"))]
        if ts_files:
            selected_file = st.selectbox("Preview file", ts_files)
            if selected_file:
                content = (ws / selected_file).read_text()
                ext = selected_file.split(".")[-1]
                lang = {"ts": "typescript", "md": "markdown", "json": "json"}.get(ext, "text")
                st.code(content, language=lang, line_numbers=True)

        # ZIP download
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in ws.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(ws))
        zip_buf.seek(0)

        st.download_button(
            "⬇ Download full project (.zip)",
            data=zip_buf.getvalue(),
            file_name="qa_agent_output.zip",
            mime="application/zip",
            use_container_width=True,
            type="primary",
        )
