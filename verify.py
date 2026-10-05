"""Post-generation verify gate. Compiles the generated Playwright project
(npm install → tsc --noEmit → playwright test --list) so broken TypeScript
never ships silently. Pure subprocess orchestration — no LLM calls here."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

# npm install can legitimately take minutes on a cold cache.
INSTALL_TIMEOUT_SECONDS = 600
STEP_TIMEOUT_SECONDS = 180

# Matches both tsc output styles:
#   classic:  tests/specs/req-1.spec.ts(3,10): error TS2307: Cannot find module...
#   pretty:   tests/specs/req-1.spec.ts:3:10 - error TS2307: Cannot find module...
_TSC_ERROR = re.compile(
    r"^(?P<file>[^\s(][^(:\n]*\.tsx?)"      # file path (no spaces/parens/colons)
    r"[(:](?P<line>\d+)[,:](?P<col>\d+)\)?"  # (line,col) or :line:col
    r"\s*[-:]\s*"
    r"(?P<msg>error TS\d+:.*)$"
)


def verify_project(project_root: Path) -> dict:
    """Compile-check the project in ``project_root``.

    Returns ``{"status": "passed"|"failed"|"skipped", "steps": [...],
    "errors": {file: [messages]}}``. Each step is
    ``{"name", "ok", "detail"}``. Never raises: a missing or broken
    toolchain yields status "skipped" with the reason in its step."""
    project_root = Path(project_root)
    result: dict = {"status": "passed", "steps": [], "errors": {}}

    npm = shutil.which("npm")
    npx = shutil.which("npx")
    if not npm or not npx:
        result["status"] = "skipped"
        result["steps"].append({
            "name": "toolchain", "ok": False,
            "detail": "npm/npx not found on PATH — verification skipped",
        })
        return result

    # 1. npm install (skipped when node_modules is already there)
    if (project_root / "node_modules").exists():
        result["steps"].append({"name": "npm install", "ok": True,
                                "detail": "node_modules present — skipped"})
    else:
        ok, out = _run([npm, "install", "--no-audit", "--no-fund"],
                       project_root, INSTALL_TIMEOUT_SECONDS)
        result["steps"].append({"name": "npm install", "ok": ok,
                                "detail": _tail(out)})
        if not ok:
            # Without dependencies tsc would drown in false TS2307 errors,
            # so this is "couldn't verify", not "code is broken".
            result["status"] = "skipped"
            return result

    # 2. tsc --noEmit — the actual compile gate
    ok, out = _run([npx, "tsc", "--noEmit"], project_root, STEP_TIMEOUT_SECONDS)
    result["steps"].append({"name": "tsc --noEmit", "ok": ok,
                            "detail": "clean" if ok else _tail(out)})
    if not ok:
        result["status"] = "failed"
        result["errors"] = parse_tsc_output(out)

    # 3. playwright test --list — catches config/collection problems tsc misses
    ok, out = _run([npx, "playwright", "test", "--list"],
                   project_root, STEP_TIMEOUT_SECONDS)
    result["steps"].append({"name": "playwright test --list", "ok": ok,
                            "detail": "clean" if ok else _tail(out)})
    if not ok:
        result["status"] = "failed"

    return result


def parse_tsc_output(output: str) -> dict[str, list[str]]:
    """Group tsc error lines by file: ``{relative/path.ts: [messages]}``.

    Handles both the classic ``file(line,col): error TS...`` and the pretty
    ``file:line:col - error TS...`` formats; non-error lines are ignored."""
    errors: dict[str, list[str]] = {}
    for line in output.splitlines():
        m = _TSC_ERROR.match(line.strip())
        if m:
            errors.setdefault(m.group("file"), []).append(
                f"({m.group('line')},{m.group('col')}): {m.group('msg').strip()}")
    return errors


def _run(cmd: list[str], cwd: Path, timeout: int) -> tuple[bool, str]:
    """Run a command, never raise. Returns (succeeded, combined output)."""
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
        return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def _tail(output: str, limit: int = 2000) -> str:
    """Keep step details readable in the JSON report."""
    output = output.strip()
    return output if len(output) <= limit else "…" + output[-limit:]
