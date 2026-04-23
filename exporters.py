"""Exporters for test cases. Six formats, all write to the project root.

- CSV        → test_cases.csv          (flat, universal)
- Excel      → test_cases.xlsx         (formatted, with summary sheet)
- Jira CSV   → test_cases.jira.csv     (Jira + Xray importable)
- TestRail   → test_cases.testrail.csv (TestRail CSV importer)
- HTML       → test_cases.html         (self-contained, styled)
- Markdown   → test_cases.md           (summary table + per-case detail)
"""

from __future__ import annotations

import csv
import html
from collections import Counter
from pathlib import Path


def run_exports(cases: list[dict], out_dir: Path, formats: list[str]) -> None:
    handlers = {
        "csv": export_csv,
        "excel": export_excel,
        "jira": export_jira,
        "testrail": export_testrail,
        "html": export_html,
        "markdown": export_markdown,
    }
    print("▶ Exporting test cases...")
    for fmt in formats:
        fn = handlers.get(fmt)
        if not fn:
            print(f"  ⚠ unknown format: {fmt}")
            continue
        path = fn(cases, out_dir)
        print(f"  ✓ {fmt:<10} → {path.name}")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _fmt_steps(steps: list[dict]) -> str:
    """Format steps as '1. Action (data: X)\\n2. ...'"""
    out = []
    for i, s in enumerate(steps, 1):
        line = f"{i}. {s.get('action', '')}"
        if s.get("data"):
            line += f" [data: {s['data']}]"
        out.append(line)
    return "\n".join(out)


def _fmt_preconditions(pcs: list[str]) -> str:
    return "\n".join(f"- {p}" for p in pcs) if pcs else ""


def _priority_to_jira(p: str) -> str:
    return {"P0": "Highest", "P1": "High", "P2": "Medium"}.get(p, "Medium")


# ──────────────────────────────────────────────────────────────────────────────
# 1. Plain CSV
# ──────────────────────────────────────────────────────────────────────────────
def export_csv(cases: list[dict], out_dir: Path) -> Path:
    path = out_dir / "test_cases.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "ID", "Requirement", "Title", "Type", "Target", "Priority", "Page",
            "Preconditions", "Steps", "Expected", "Automatable",
        ])
        for c in cases:
            w.writerow([
                c.get("id", ""), c.get("requirement_id", ""), c.get("title", ""),
                c.get("type", ""), c.get("target", ""), c.get("priority", ""),
                c.get("page", ""),
                _fmt_preconditions(c.get("preconditions", [])),
                _fmt_steps(c.get("steps", [])),
                c.get("expected", ""),
                "Yes" if c.get("automatable", True) else "No",
            ])
    return path


# ──────────────────────────────────────────────────────────────────────────────
# 2. Excel (.xlsx) — cases sheet + summary sheet
# ──────────────────────────────────────────────────────────────────────────────
def export_excel(cases: list[dict], out_dir: Path) -> Path:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise SystemExit("Excel export needs openpyxl: pip install openpyxl")

    path = out_dir / "test_cases.xlsx"
    wb = Workbook()

    # Sheet 1: Cases
    ws = wb.active
    ws.title = "Test Cases"
    headers = ["ID", "Requirement", "Title", "Type", "Target", "Priority", "Page",
               "Preconditions", "Steps", "Expected", "Automatable"]
    ws.append(headers)

    header_fill = PatternFill(start_color="2C3E50", end_color="2C3E50", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center")

    priority_colors = {"P0": "E74C3C", "P1": "F39C12", "P2": "95A5A6"}

    for c in cases:
        ws.append([
            c.get("id", ""), c.get("requirement_id", ""), c.get("title", ""),
            c.get("type", ""), c.get("target", ""), c.get("priority", ""),
            c.get("page", ""),
            _fmt_preconditions(c.get("preconditions", [])),
            _fmt_steps(c.get("steps", [])),
            c.get("expected", ""),
            "Yes" if c.get("automatable", True) else "No",
        ])
        # Color priority cell
        prio = c.get("priority", "")
        if prio in priority_colors:
            cell = ws.cell(row=ws.max_row, column=6)
            cell.fill = PatternFill(start_color=priority_colors[prio],
                                     end_color=priority_colors[prio], fill_type="solid")
            cell.font = Font(color="FFFFFF", bold=True)
            cell.alignment = Alignment(horizontal="center")

    # Column widths
    widths = [10, 12, 45, 14, 10, 10, 18, 30, 50, 40, 12]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # Wrap multi-line cells
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    ws.freeze_panes = "A2"

    # Sheet 2: Summary
    ws2 = wb.create_sheet("Summary")
    ws2.append(["Metric", "Count"])
    for cell in ws2[1]:
        cell.fill = header_fill
        cell.font = header_font

    ws2.append(["Total cases", len(cases)])
    ws2.append(["Automatable", sum(1 for c in cases if c.get("automatable", True))])
    ws2.append([])
    ws2.append(["By Priority", ""])
    for p, n in Counter(c.get("priority", "?") for c in cases).most_common():
        ws2.append([f"  {p}", n])
    ws2.append([])
    ws2.append(["By Type", ""])
    for t, n in Counter(c.get("type", "?") for c in cases).most_common():
        ws2.append([f"  {t}", n])
    ws2.append([])
    ws2.append(["By Target", ""])
    for tg, n in Counter(c.get("target", "?") for c in cases).most_common():
        ws2.append([f"  {tg}", n])

    ws2.column_dimensions["A"].width = 24
    ws2.column_dimensions["B"].width = 12

    wb.save(path)
    return path


# ──────────────────────────────────────────────────────────────────────────────
# 3. Jira CSV (Xray-compatible Test issue format)
# ──────────────────────────────────────────────────────────────────────────────
def export_jira(cases: list[dict], out_dir: Path) -> Path:
    path = out_dir / "test_cases.jira.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "Issue Type", "Summary", "Priority", "Description", "Labels",
            "Test Type", "Manual Test Steps",
        ])
        for c in cases:
            desc = _build_jira_description(c)
            labels = " ".join(filter(None, [
                c.get("type", ""),
                c.get("target", ""),
                c.get("priority", ""),
                c.get("requirement_id", ""),
            ]))
            steps_combined = _fmt_steps(c.get("steps", [])) + f"\n\nExpected: {c.get('expected', '')}"
            w.writerow([
                "Test",
                f"[{c.get('id', '')}] {c.get('title', '')}",
                _priority_to_jira(c.get("priority", "P2")),
                desc,
                labels,
                "Manual" if not c.get("automatable", True) else "Automated",
                steps_combined,
            ])
    return path


def _build_jira_description(c: dict) -> str:
    lines = [
        f"*Requirement:* {c.get('requirement_id', 'n/a')}",
        f"*Type:* {c.get('type', 'n/a')}  |  *Target:* {c.get('target', 'n/a')}",
        "",
    ]
    pcs = c.get("preconditions") or []
    if pcs:
        lines.append("*Preconditions:*")
        lines += [f"* {p}" for p in pcs]
        lines.append("")
    lines.append("*Steps:*")
    for i, s in enumerate(c.get("steps", []), 1):
        line = f"# {s.get('action', '')}"
        if s.get("data"):
            line += f" (data: {s['data']})"
        lines.append(line)
    lines.append("")
    lines.append(f"*Expected:* {c.get('expected', '')}")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# 4. TestRail CSV (standard TestRail importer columns)
# ──────────────────────────────────────────────────────────────────────────────
def export_testrail(cases: list[dict], out_dir: Path) -> Path:
    path = out_dir / "test_cases.testrail.csv"
    tr_priority = {"P0": "Critical", "P1": "High", "P2": "Medium"}
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "Section", "Title", "Template", "Type", "Priority",
            "Preconditions", "Steps", "Expected Result", "References",
        ])
        for c in cases:
            w.writerow([
                c.get("requirement_id", "General"),
                c.get("title", ""),
                "Test Case (Text)",
                c.get("type", "Functional").title(),
                tr_priority.get(c.get("priority", "P2"), "Medium"),
                _fmt_preconditions(c.get("preconditions", [])),
                _fmt_steps(c.get("steps", [])),
                c.get("expected", ""),
                f"{c.get('requirement_id', '')} / {c.get('id', '')}",
            ])
    return path


# ──────────────────────────────────────────────────────────────────────────────
# 5. HTML report (self-contained, human-readable)
# ──────────────────────────────────────────────────────────────────────────────
def export_html(cases: list[dict], out_dir: Path) -> Path:
    path = out_dir / "test_cases.html"
    by_prio = Counter(c.get("priority", "?") for c in cases)
    by_type = Counter(c.get("type", "?") for c in cases)
    by_target = Counter(c.get("target", "?") for c in cases)

    rows = []
    for c in cases:
        prio = c.get("priority", "P2")
        prio_class = {"P0": "p0", "P1": "p1", "P2": "p2"}.get(prio, "")
        target_class = f"t-{c.get('target', 'x')}"
        steps_html = "".join(
            f"<li>{html.escape(s.get('action', ''))}"
            + (f" <code>{html.escape(str(s['data']))}</code>" if s.get("data") else "")
            + "</li>"
            for s in c.get("steps", [])
        )
        pcs = c.get("preconditions") or []
        pcs_html = "".join(f"<li>{html.escape(p)}</li>" for p in pcs)

        rows.append(f"""
        <details class="case">
          <summary>
            <span class="id">{html.escape(c.get('id', ''))}</span>
            <span class="badge {prio_class}">{html.escape(prio)}</span>
            <span class="badge {target_class}">{html.escape(c.get('target', ''))}</span>
            <span class="badge t-{html.escape(c.get('type', ''))}">{html.escape(c.get('type', ''))}</span>
            <span class="title">{html.escape(c.get('title', ''))}</span>
            <span class="req">{html.escape(c.get('requirement_id', ''))}</span>
          </summary>
          <div class="body">
            {f'<h4>Preconditions</h4><ul>{pcs_html}</ul>' if pcs_html else ''}
            <h4>Steps</h4>
            <ol>{steps_html}</ol>
            <h4>Expected</h4>
            <p>{html.escape(c.get('expected', ''))}</p>
          </div>
        </details>""")

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Test Cases ({len(cases)})</title>
<style>
  :root {{ --fg:#1a1a1a; --muted:#666; --bg:#fafafa; --card:#fff; --border:#e0e0e0; }}
  body {{ font-family: -apple-system, 'Segoe UI', system-ui, sans-serif;
          margin:0; padding:2rem; background:var(--bg); color:var(--fg); }}
  h1 {{ margin:0 0 1rem; }}
  .stats {{ display:flex; gap:2rem; flex-wrap:wrap; background:var(--card);
            padding:1rem 1.5rem; border-radius:8px; border:1px solid var(--border); margin-bottom:1.5rem; }}
  .stat-block strong {{ display:block; color:var(--muted); font-size:.8rem; text-transform:uppercase; }}
  .stat-block span {{ margin-right:.75rem; }}
  .case {{ background:var(--card); border:1px solid var(--border); border-radius:6px;
           margin-bottom:.5rem; padding:.5rem .75rem; }}
  .case summary {{ cursor:pointer; display:flex; align-items:center; gap:.5rem; flex-wrap:wrap; }}
  .case summary .id {{ font-family: monospace; font-weight:bold; min-width:70px; }}
  .case summary .title {{ flex:1; min-width:200px; }}
  .case summary .req {{ color:var(--muted); font-size:.85rem; }}
  .badge {{ display:inline-block; padding:.15rem .5rem; border-radius:3px; font-size:.75rem;
            font-weight:600; text-transform:uppercase; letter-spacing:.5px; }}
  .badge.p0 {{ background:#E74C3C; color:#fff; }}
  .badge.p1 {{ background:#F39C12; color:#fff; }}
  .badge.p2 {{ background:#95A5A6; color:#fff; }}
  .badge.t-ui {{ background:#3498DB; color:#fff; }}
  .badge.t-api {{ background:#9B59B6; color:#fff; }}
  .badge.t-manual {{ background:#7F8C8D; color:#fff; }}
  .badge[class*="t-security"] {{ background:#C0392B; color:#fff; }}
  .badge[class*="t-accessibility"] {{ background:#16A085; color:#fff; }}
  .body {{ padding:.5rem 1rem; border-top:1px solid var(--border); margin-top:.5rem; }}
  .body h4 {{ margin:.5rem 0 .25rem; color:var(--muted); font-size:.85rem; text-transform:uppercase; }}
  code {{ background:#f0f0f0; padding:1px 5px; border-radius:3px; font-size:.85em; }}
</style></head><body>
<h1>Test Cases <span style="color:var(--muted); font-weight:normal;">({len(cases)})</span></h1>
<div class="stats">
  <div class="stat-block"><strong>Priority</strong>{"".join(f'<span><b>{p}</b>: {n}</span>' for p, n in by_prio.most_common())}</div>
  <div class="stat-block"><strong>Type</strong>{"".join(f'<span><b>{t}</b>: {n}</span>' for t, n in by_type.most_common())}</div>
  <div class="stat-block"><strong>Target</strong>{"".join(f'<span><b>{t}</b>: {n}</span>' for t, n in by_target.most_common())}</div>
</div>
{"".join(rows)}
</body></html>"""
    path.write_text(page, encoding="utf-8")
    return path


# ──────────────────────────────────────────────────────────────────────────────
# 6. Markdown — summary table + full detail
# ──────────────────────────────────────────────────────────────────────────────
def export_markdown(cases: list[dict], out_dir: Path) -> Path:
    path = out_dir / "test_cases.md"
    lines = [f"# Test Cases ({len(cases)})\n"]

    # Summary stats
    lines.append("## Summary\n")
    lines.append(f"- **Priority:** " + ", ".join(
        f"{p}: {n}" for p, n in Counter(c.get('priority', '?') for c in cases).most_common()))
    lines.append(f"- **Type:** " + ", ".join(
        f"{t}: {n}" for t, n in Counter(c.get('type', '?') for c in cases).most_common()))
    lines.append(f"- **Target:** " + ", ".join(
        f"{t}: {n}" for t, n in Counter(c.get('target', '?') for c in cases).most_common()))
    lines.append("")

    # Overview table
    lines.append("## Overview\n")
    lines.append("| ID | REQ | Title | Type | Target | Priority | Auto |")
    lines.append("|----|-----|-------|------|--------|----------|------|")
    for c in cases:
        title = c.get("title", "").replace("|", "\\|")
        lines.append(
            f"| {c.get('id', '')} | {c.get('requirement_id', '')} | {title} | "
            f"{c.get('type', '')} | {c.get('target', '')} | {c.get('priority', '')} | "
            f"{'✓' if c.get('automatable', True) else '—'} |"
        )
    lines.append("")

    # Full detail
    lines.append("## Details\n")
    for c in cases:
        lines.append(f"### {c.get('id', '')}: {c.get('title', '')}\n")
        lines.append(f"**Requirement:** {c.get('requirement_id', '')}  ")
        lines.append(f"**Type:** {c.get('type', '')}  |  "
                     f"**Target:** {c.get('target', '')}  |  "
                     f"**Priority:** {c.get('priority', '')}")
        pcs = c.get("preconditions") or []
        if pcs:
            lines.append("\n**Preconditions:**")
            lines += [f"- {p}" for p in pcs]
        lines.append("\n**Steps:**")
        for i, s in enumerate(c.get("steps", []), 1):
            extra = f" _(data: `{s['data']}`)_" if s.get("data") else ""
            lines.append(f"{i}. {s.get('action', '')}{extra}")
        lines.append(f"\n**Expected:** {c.get('expected', '')}\n")
        lines.append("---\n")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
