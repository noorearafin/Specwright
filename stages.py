"""The three pipeline stages. Stage 3 is now deterministic (no tool-use loop)
so it works with any LLM."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import defaultdict
from pathlib import Path

from prompts import (
    PLANNER_SYSTEM, ESTIMATOR_SYSTEM, CASE_WRITER_SYSTEM,
    POM_SYSTEM, UI_SPEC_SYSTEM, API_SPEC_SYSTEM, REPAIR_SYSTEM,
)
from schema import validate_cases
from verify import verify_project

# Rough budget per test case in tokens (JSON object with steps).
# Used to decide chunking: if total_cases × this > provider max, split per-REQ.
TOKENS_PER_CASE = 500

# A failed per-requirement chunk gets this many extra attempts before we
# record the failure in generation_report.json and move on.
CHUNK_RETRIES = 2
CHUNK_BACKOFF_SECONDS = 2


# ──────────────────────────────────────────────────────────────────────────────
# Stage 1 — Test Plan
# ──────────────────────────────────────────────────────────────────────────────
def stage1_plan(llm, requirements: str, out_dir: Path) -> str:
    print("▶ Stage 1: Writing test plan...")
    plan = llm.complete(
        system=PLANNER_SYSTEM,
        user=f"<requirements>\n{requirements}\n</requirements>\n\nWrite the test plan.",
        max_tokens=8000,
    )
    (out_dir / "test_plan.md").write_text(plan)
    print(f"  ✓ test_plan.md written ({len(plan)} chars)\n")
    return plan


# ──────────────────────────────────────────────────────────────────────────────
# Stage 2 — Test Cases (two-pass: estimate → generate, chunked if needed)
# ──────────────────────────────────────────────────────────────────────────────
def stage2_cases(llm, requirements: str, plan: str, out_dir: Path) -> list[dict]:
    print("▶ Stage 2: Writing test cases...")

    # Pass 1 — Estimator: LLM decides how many cases per requirement
    print("  • Pass 1/2: Estimating coverage...")
    estimate = llm.complete_json(
        system=ESTIMATOR_SYSTEM,
        user=(
            f"<requirements>\n{requirements}\n</requirements>\n\n"
            f"<test_plan>\n{plan}\n</test_plan>\n\n"
            "Return your coverage plan."
        ),
        max_tokens=2000,
    )
    per_req = estimate.get("cases_per_requirement", {})
    if not per_req:
        raise ValueError(f"Estimator returned no per-requirement counts: {estimate}")

    total = sum(per_req.values())
    print(f"  ✓ LLM plans {total} cases across {len(per_req)} requirements: "
          f"{dict(per_req)}")
    if estimate.get("reasoning"):
        print(f"  • Reasoning: {estimate['reasoning'][:200]}")

    # Pass 2 — Decide: single call or chunked?
    budget = total * TOKENS_PER_CASE
    cap = llm.max_output_tokens
    all_cases: list[dict] = []
    errors: dict[str, str] = {}  # req_id → error message for the report

    if budget <= cap:
        print(f"  • Pass 2/2: Generating all {total} cases in one call "
              f"(budget {budget} ≤ provider cap {cap})...")
        batch = llm.complete_json(
            system=CASE_WRITER_SYSTEM,
            user=_case_user_message(requirements, plan, per_req),
            max_tokens=cap,
        )
        all_cases = _normalize_cases(batch)
    else:
        print(f"  • Pass 2/2: Chunking per-requirement "
              f"(total budget {budget} > provider cap {cap})...")
        for i, (req_id, count) in enumerate(per_req.items(), 1):
            print(f"    [{i}/{len(per_req)}] Generating {count} cases for {req_id}...")
            chunk, err = _generate_req_chunk(llm, requirements, plan, req_id, count, cap)
            if err is None:
                all_cases.extend(chunk)
                print(f"       ✓ got {len(chunk)} cases")
            else:
                errors[req_id] = str(err)
                print(f"       ⚠ {req_id} failed after retries: {err} — continuing")

            # Pause between calls (sequential-safe for free tiers)
            if i < len(per_req):
                time.sleep(1)

    # Enforce the case schema (fill defaults, coerce near-misses, drop junk)
    all_cases = validate_cases(all_cases)

    # Renumber TC-IDs globally so they're unique regardless of chunking
    for idx, case in enumerate(all_cases, 1):
        case["id"] = f"TC-{idx:03d}"

    (out_dir / "test_cases.json").write_text(json.dumps(all_cases, indent=2))

    # Coverage integrity report: Pass-1 estimate vs what Pass 2 produced,
    # so callers can spot requirements that silently got zero cases.
    report = _build_generation_report(per_req, all_cases, errors)
    (out_dir / "generation_report.json").write_text(json.dumps(report, indent=2))
    shortfall = [r for r, e in report.items() if e["generated"] == 0]
    if shortfall:
        print(f"  ⚠ Zero cases generated for: {', '.join(shortfall)} "
              f"(see generation_report.json)")

    by_target = defaultdict(int)
    for c in all_cases:
        by_target[c.get("target", "?")] += 1
    print(f"  ✓ {len(all_cases)} cases written. By target: {dict(by_target)}\n")
    return all_cases


def _case_user_message(requirements: str, plan: str, per_req: dict,
                       single_req: str | None = None) -> str:
    """Build the user prompt for the case-writer pass."""
    if single_req:
        target_line = (
            f"Generate EXACTLY {per_req[single_req]} test cases for "
            f"requirement `{single_req}` only. Ignore other requirements."
        )
    else:
        breakdown = ", ".join(f"{k}={v}" for k, v in per_req.items())
        total = sum(per_req.values())
        target_line = (
            f"Generate EXACTLY {total} test cases total, distributed as: {breakdown}."
        )

    return (
        f"<requirements>\n{requirements}\n</requirements>\n\n"
        f"<test_plan>\n{plan}\n</test_plan>\n\n"
        f"{target_line}\n\n"
        "Return a JSON array only. No prose, no markdown fences."
    )


def _normalize_cases(batch, start_id: int = 1) -> list[dict]:
    """Accept either a bare list or an object wrapping one. Normalize to a list."""
    if isinstance(batch, dict):
        # Some models wrap: {"test_cases": [...]} or {"cases": [...]}
        for key in ("test_cases", "cases", "items", "data"):
            if key in batch and isinstance(batch[key], list):
                batch = batch[key]
                break
        else:
            raise ValueError(f"Expected list of cases, got object: {list(batch.keys())}")
    if not isinstance(batch, list):
        raise ValueError(f"Expected list of cases, got {type(batch).__name__}")
    return batch


def _generate_req_chunk(llm, requirements: str, plan: str, req_id: str,
                        count: int, cap: int) -> tuple[list[dict], Exception | None]:
    """Generate the cases for one requirement, retrying failed calls.

    Returns ``(cases, error)`` — ``error`` is None on success, the last
    exception when all attempts failed (then ``cases`` is empty)."""
    req_budget = count * TOKENS_PER_CASE + 500  # padding for JSON overhead
    chunk_max = min(req_budget, cap)
    last_err: Exception | None = None
    for attempt in range(1 + CHUNK_RETRIES):
        try:
            batch = llm.complete_json(
                system=CASE_WRITER_SYSTEM,
                user=_case_user_message(
                    requirements, plan, {req_id: count}, single_req=req_id,
                ),
                max_tokens=chunk_max,
            )
            return _normalize_cases(batch), None
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < CHUNK_RETRIES:
                wait = CHUNK_BACKOFF_SECONDS * (attempt + 1)
                print(f"       ⚠ {req_id} attempt {attempt + 1} failed: {e} "
                      f"— retrying in {wait}s")
                time.sleep(wait)
    return [], last_err


def _build_generation_report(per_req: dict, cases: list[dict],
                             errors: dict[str, str]) -> dict:
    """Per-requirement {estimated, generated, error} comparing the Pass-1
    estimate against the cases that actually came back."""
    generated = defaultdict(int)
    for c in cases:
        generated[c.get("requirement_id")] += 1
    return {
        req_id: {
            "estimated": count,
            "generated": generated.get(req_id, 0),
            "error": errors.get(req_id),
        }
        for req_id, count in per_req.items()
    }


def stage2_regenerate(llm, requirements: str, plan: str, per_req: dict,
                      out_dir: Path) -> dict[str, list[dict]]:
    """Re-run Pass 2 for a subset of requirements (one chunked call each).

    Used to backfill requirements that got zero cases in stage2_cases.
    Returns ``{req_id: cases}`` (cases validated, TC-IDs NOT renumbered —
    the caller merges and renumbers) and refreshes the matching entries in
    generation_report.json."""
    cap = llm.max_output_tokens
    results: dict[str, list[dict]] = {}
    errors: dict[str, str] = {}
    for i, (req_id, count) in enumerate(per_req.items(), 1):
        print(f"  • Regenerating {count} cases for {req_id}...")
        chunk, err = _generate_req_chunk(llm, requirements, plan, req_id, count, cap)
        results[req_id] = validate_cases(chunk)
        if err is not None:
            errors[req_id] = str(err)
            print(f"    ⚠ {req_id} failed again: {err}")
        else:
            print(f"    ✓ got {len(results[req_id])} cases")
        if i < len(per_req):
            time.sleep(1)

    report_path = out_dir / "generation_report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    report.update(_build_generation_report(
        per_req, [c for chunk in results.values() for c in chunk], errors))
    report_path.write_text(json.dumps(report, indent=2))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# Stage 3 — Automation (deterministic orchestration + LLM code gen per file)
# ──────────────────────────────────────────────────────────────────────────────
def stage3_automate(llm, cases: list[dict], project_root: Path,
                    all_cases: list[dict] | None = None,
                    check: bool = True, regen: str = "changed") -> list[str]:
    print("▶ Stage 3: Generating Playwright tests...")

    # 1. Project detection + scaffold (pure Python, no LLM)
    is_new = not (project_root / "playwright.config.ts").exists()
    if is_new:
        print("  • New project — scaffolding Playwright config...")
        _scaffold(project_root)

    # 2. Split by target
    ui_cases = [c for c in cases if c.get("target") == "ui"]
    api_cases = [c for c in cases if c.get("target") == "api"]
    print(f"  • UI cases: {len(ui_cases)}, API cases: {len(api_cases)}")

    # Regeneration manifest: per generated file, the hash of the content we
    # wrote and of the cases that produced it. Lets re-runs tell apart
    # "cases changed" (regenerate) from "hand-edited" (don't clobber).
    manifest = _load_manifest(project_root)
    files_written: list[str] = []
    conflicts: list[tuple[str, str]] = []  # (original rel path, .new rel path)

    # 3. For UI: figure out page objects, generate each
    if ui_cases:
        pages = _group_pages(ui_cases)  # {"LoginPage": [cases...], ...}
        print(f"  • Page objects needed: {list(pages.keys())}")

        for page_name, page_cases in pages.items():
            _generate_file(
                llm, project_root, f"tests/pages/{page_name}.ts",
                POM_SYSTEM, _pom_user(page_name, page_cases), 4000,
                page_cases, manifest, regen, files_written, conflicts,
            )

        # 4. UI spec files grouped by requirement. Each spec may only import
        # the POMs _group_pages actually produced (including inferred names),
        # so pass those real class names instead of re-deriving from c['page'].
        by_req = _group_by(ui_cases, "requirement_id")
        for req_id, group in by_req.items():
            pom_names = sorted({_page_name(c) for c in group})
            _generate_file(
                llm, project_root, f"tests/specs/{_slug(req_id)}.spec.ts",
                UI_SPEC_SYSTEM, _ui_spec_user(req_id, group, pom_names), 6000,
                group, manifest, regen, files_written, conflicts,
            )

    # 5. API spec files grouped by requirement
    if api_cases:
        by_req = _group_by(api_cases, "requirement_id")
        for req_id, group in by_req.items():
            _generate_file(
                llm, project_root, f"tests/api/{_slug(req_id)}.spec.ts",
                API_SPEC_SYSTEM, _api_spec_user(req_id, group), 6000,
                group, manifest, regen, files_written, conflicts,
            )

    _save_manifest(project_root, manifest)

    # 6. Verify gate (optional) — compile what was written, give each broken
    # file ONE LLM repair pass, re-verify, and persist the outcome for the
    # CLI/UI to read. Return type stays list[str] for existing callers.
    verify = None
    needs_manual: list[str] = []
    if check:
        print("  • Verifying project (npm install / tsc / playwright --list)...")
        verify = verify_project(project_root)
        if verify["status"] == "failed" and verify["errors"]:
            print(f"    ⚠ {len(verify['errors'])} file(s) failed to compile "
                  f"— attempting one repair round...")
            pom_files = sorted(f for f in files_written
                               if f.startswith("tests/pages/"))
            verify = _repair_round(llm, project_root, verify, pom_files)
        needs_manual = sorted(verify.get("errors", {}))
        (project_root / "verify_report.json").write_text(
            json.dumps(verify, indent=2))
        print(f"    {'✓' if verify['status'] == 'passed' else '⚠'} "
              f"Verification {verify['status']}")

    # 7. Report — compute skipped from the FULL case set when the caller
    # provides it, since `cases` is usually pre-filtered to automatable ones
    # by the scope gate (which would make the skipped list always empty).
    pool = all_cases if all_cases is not None else cases
    selected_ids = {c.get("id") for c in cases}
    skipped = [c for c in pool
               if not c.get("automatable", True) and c.get("id") not in selected_ids]
    _write_report(project_root, cases, files_written, skipped,
                  verify=verify, needs_manual=needs_manual,
                  conflicts=conflicts)
    print(f"\n  ✓ {len(files_written)} files written. See AUTOMATION_REPORT.md")
    return files_written


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _page_name(case: dict) -> str:
    """POM class name for a UI case: its `page` field, or a name inferred
    from requirement_id. Single source of truth so POM generation and spec
    imports always agree."""
    return case.get("page") or f"Req{case.get('requirement_id', 'Unknown').replace('REQ-', '')}Page"


def _group_pages(ui_cases: list[dict]) -> dict[str, list[dict]]:
    """Group UI cases by their `page` field. Infer from requirement_id if missing."""
    out: dict[str, list[dict]] = defaultdict(list)
    for c in ui_cases:
        out[_page_name(c)].append(c)
    return dict(out)


def _group_by(cases: list[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for c in cases:
        out[c.get(key, "UNGROUPED")].append(c)
    return dict(out)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ──────────────────────────────────────────────────────────────────────────────
# Regeneration manifest — .specwright/manifest.json maps each generated file
# to {file_sha256, cases_sha256} so re-runs can tell "cases changed" apart
# from "someone hand-edited this file".
# ──────────────────────────────────────────────────────────────────────────────
MANIFEST_PATH = ".specwright/manifest.json"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cases_hash(cases: list[dict]) -> str:
    """Stable hash of the cases that produce one generated file."""
    return _sha256(json.dumps(cases, sort_keys=True))


def _load_manifest(project_root: Path) -> dict:
    """Read the manifest; {} when missing or unreadable (pre-manifest project)."""
    path = project_root / MANIFEST_PATH
    if not path.exists():
        return {}
    try:
        manifest = json.loads(path.read_text())
        return manifest if isinstance(manifest, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_manifest(project_root: Path, manifest: dict) -> None:
    path = project_root / MANIFEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True))


def _conflict_path(path: Path) -> Path:
    """`req-1.spec.ts` → `req-1.spec.new.ts` — the fresh version written
    beside a hand-edited file so the edit is never clobbered."""
    return path.with_name(f"{path.stem}.new{path.suffix}")


def _decide_regen(path: Path, cases_hash: str, entry: dict | None,
                  regen: str = "changed") -> str:
    """Per-file regeneration decision. Returns one of:

    - "write"    — (re)generate the file in place
    - "skip"     — leave it alone, no LLM call
    - "conflict" — cases changed but the file was hand-edited since we wrote
                   it: generate beside it as <name>.new.<ext>

    ``entry`` is the manifest record for this file (or None). Rules:
    missing file → write; regen="all" → write (explicit overwrite); no
    manifest entry → skip (the old skip-if-exists behavior for files we
    never wrote); producing cases unchanged → skip; cases changed and the
    file still matches what we wrote → write; cases changed but the file
    hash differs (hand-edited) → conflict."""
    if not path.exists():
        return "write"
    if regen == "all":
        return "write"
    if entry is None:
        return "skip"
    if cases_hash == entry.get("cases_sha256"):
        return "skip"
    if _sha256(path.read_text()) == entry.get("file_sha256"):
        return "write"
    return "conflict"


def _generate_file(llm, project_root: Path, rel_path: str, system: str,
                   user: str, max_tokens: int, cases: list[dict],
                   manifest: dict, regen: str, files_written: list[str],
                   conflicts: list[tuple[str, str]]) -> None:
    """Decide whether ``rel_path`` needs (re)generation; if so, call the LLM
    and write it (in place, or as <name>.new.<ext> on a hand-edit conflict).
    Updates ``manifest``, ``files_written`` and ``conflicts`` in place."""
    path = project_root / rel_path
    cases_hash = _cases_hash(cases)
    decision = _decide_regen(path, cases_hash, manifest.get(rel_path), regen)

    if decision == "skip":
        reason = ("cases unchanged" if rel_path in manifest
                  else "exists, not generated by us")
        print(f"    ↳ skip ({reason}): {rel_path}")
        return

    code = llm.complete(system=system, user=user, max_tokens=max_tokens)

    target = path if decision == "write" else _conflict_path(path)
    target_rel = str(target.relative_to(project_root))
    target.parent.mkdir(parents=True, exist_ok=True)
    content = _clean_code(code)
    target.write_text(content)
    manifest[target_rel] = {
        "file_sha256": _sha256(content),
        "cases_sha256": cases_hash,
    }
    files_written.append(target_rel)
    if decision == "conflict":
        conflicts.append((rel_path, target_rel))
        print(f"    ⚠ conflict (hand-edited): {rel_path} — wrote {target_rel}")
    else:
        print(f"    ✓ {target_rel}")


def _clean_code(code: str) -> str:
    """Strip accidental markdown fences and surrounding prose from LLM output."""
    lines = code.strip().split("\n")

    # Opening fence (```typescript, ```ts or bare ```) — drop it plus any
    # prose above it, but stop looking once real code has started.
    for i, line in enumerate(lines):
        if re.match(r"^\s*import\b", line):
            break
        if re.match(r"^```\w*\s*$", line.strip()):
            lines = lines[i + 1:]
            break

    # Closing fence — drop it plus any trailing prose below it.
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() == "```":
            lines = lines[:i]
            break

    code = "\n".join(lines).strip()

    # Prose before the first import (some models preface the code anyway).
    if not code.startswith(("import", "//", "/*")):
        first_import = re.search(r"^import\b", code, re.MULTILINE)
        if first_import:
            code = code[first_import.start():].strip()
    return code + "\n"


def _pom_user(page_name: str, cases: list[dict]) -> str:
    return (
        f"Create a Page Object class named `{page_name}` for these cases.\n"
        f"Extract all the UI interactions you can infer.\n\n"
        f"Cases:\n{json.dumps(cases, indent=2)}"
    )


def _ui_spec_user(req_id: str, cases: list[dict], pom_names: list[str]) -> str:
    imports = "\n".join(
        f"import {{ {name} }} from '../pages/{name}';" for name in pom_names)
    return (
        f"Write a spec file for {req_id}.\n"
        f"These page objects exist (class name = file name). Import ONLY them, "
        f"exactly like this:\n{imports}\n"
        f"Generate one test() per case. Use TC-ID in the title.\n\n"
        f"Cases:\n{json.dumps(cases, indent=2)}"
    )


def _api_spec_user(req_id: str, cases: list[dict]) -> str:
    return (
        f"Write an API spec file for {req_id} using Playwright's request fixture.\n"
        f"Generate one test() per case. Use TC-ID in the title.\n\n"
        f"Cases:\n{json.dumps(cases, indent=2)}"
    )


def _repair_round(llm, project_root: Path, verify: dict,
                  pom_files: list[str]) -> dict:
    """ONE LLM repair call per broken file, then one re-verify.

    Returns the re-verify result; files still broken stay in its
    ``errors`` dict and end up under "Needs manual fix" in the report."""
    for rel_path, messages in verify["errors"].items():
        path = project_root / rel_path
        # Only rewrite real .ts files inside the project — tsc paths are
        # relative to project_root, but don't trust them blindly.
        if (not rel_path.endswith(".ts") or not path.is_file()
                or project_root.resolve() not in path.resolve().parents):
            continue
        print(f"    • Repairing {rel_path} ({len(messages)} error(s))...")
        fixed = llm.complete(
            system=REPAIR_SYSTEM,
            user=_repair_user(rel_path, path.read_text(), messages, pom_files),
            max_tokens=8000,
        )
        path.write_text(_clean_code(fixed))
    return verify_project(project_root)


def _repair_user(rel_path: str, content: str, messages: list[str],
                 pom_files: list[str]) -> str:
    pom_list = "\n".join(f"- {f}" for f in pom_files) or "(none)"
    return (
        f"File `{rel_path}` fails to compile.\n\n"
        f"Compiler errors:\n{chr(10).join(messages)}\n\n"
        f"Page-object files that exist on disk:\n{pom_list}\n\n"
        f"Current content:\n{content}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Scaffold for new projects
# ──────────────────────────────────────────────────────────────────────────────
def _scaffold(root: Path) -> None:
    (root / "tests" / "pages").mkdir(parents=True, exist_ok=True)
    (root / "tests" / "specs").mkdir(parents=True, exist_ok=True)
    (root / "tests" / "api").mkdir(parents=True, exist_ok=True)
    (root / "tests" / "fixtures").mkdir(parents=True, exist_ok=True)

    pkg = root / "package.json"
    if not pkg.exists():
        pkg.write_text(json.dumps({
            "name": root.name, "version": "0.0.1", "private": True,
            "scripts": {
                "test": "playwright test",
                "test:ui": "playwright test tests/specs",
                "test:api": "playwright test tests/api",
            },
            "devDependencies": {
                "@playwright/test": "^1.50.0",
                "@types/node": "^20.0.0",
                "typescript": "^5.0.0",
                "dotenv": "^16.0.0",
                # UI_SPEC_SYSTEM tells the LLM to use this for a11y tests
                "@axe-core/playwright": "^4.10.0",
            },
        }, indent=2))

    ts = root / "tsconfig.json"
    if not ts.exists():
        ts.write_text(json.dumps({
            "compilerOptions": {
                "target": "ES2022", "module": "commonjs", "strict": True,
                "esModuleInterop": True, "skipLibCheck": True,
            },
            "include": ["tests/**/*.ts"],
        }, indent=2))

    cfg = root / "playwright.config.ts"
    if not cfg.exists():
        cfg.write_text("""import { defineConfig, devices } from '@playwright/test';
import 'dotenv/config';

// Browser projects reuse the session saved by tests/fixtures/auth.setup.ts,
// so specs start logged in instead of repeating the login flow per test.
const AUTH_FILE = 'playwright/.auth/user.json';

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: [['html'], ['list']],
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'setup', testMatch: /.*\\.setup\\.ts/ },
    { name: 'chromium', use: { ...devices['Desktop Chrome'], storageState: AUTH_FILE },
      dependencies: ['setup'] },
    { name: 'firefox',  use: { ...devices['Desktop Firefox'], storageState: AUTH_FILE },
      dependencies: ['setup'] },
    { name: 'webkit',   use: { ...devices['Desktop Safari'], storageState: AUTH_FILE },
      dependencies: ['setup'] },
    { name: 'api', testDir: './tests/api',
      use: { baseURL: process.env.API_URL || process.env.BASE_URL } },
  ],
});
""")

    # Auth fixtures: log in ONCE in a setup project, persist the session as
    # storageState, and hand specs a pre-authenticated `test` to import.
    setup_ts = root / "tests" / "fixtures" / "auth.setup.ts"
    if not setup_ts.exists():
        setup_ts.write_text("""import { test as setup } from '@playwright/test';

const AUTH_FILE = 'playwright/.auth/user.json';

// Runs once before the browser projects (see playwright.config.ts).
// Adjust the locators to match the application's real login form.
setup('authenticate', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel(/email|username/i).fill(process.env.TEST_USER || '');
  await page.getByLabel(/password/i).fill(process.env.TEST_PASS || '');
  await page.getByRole('button', { name: /log in|sign in/i }).click();
  await page.waitForURL((url) => !url.pathname.includes('login'));
  await page.context().storageState({ path: AUTH_FILE });
});
""")

    fixture_ts = root / "tests" / "fixtures" / "test.ts"
    if not fixture_ts.exists():
        fixture_ts.write_text("""import path from 'path';
import { test as base } from '@playwright/test';

// `test` wired to the session saved by auth.setup.ts. Specs import it from
// here instead of '@playwright/test' and start already logged in — except
// login/auth specs, which must exercise the real flow.
export const test = base.extend({
  storageState: async ({}, use) => {
    await use(path.resolve(__dirname, '../../playwright/.auth/user.json'));
  },
});

export { expect } from '@playwright/test';
""")

    gi = root / ".gitignore"
    if not gi.exists():
        gi.write_text(
            "node_modules/\n"
            "playwright/.auth/\n"
            "test-results/\n"
        )

    env = root / ".env.example"
    if not env.exists():
        env.write_text(
            "BASE_URL=http://localhost:3000\n"
            "API_URL=http://localhost:3000/api\n"
            "TEST_USER=test@example.com\n"
            "TEST_PASS=changeme\n"
        )


def _write_report(root: Path, cases: list[dict], files: list[str],
                  skipped: list[dict] | None = None,
                  verify: dict | None = None,
                  needs_manual: list[str] | None = None,
                  conflicts: list[tuple[str, str]] | None = None) -> None:
    if skipped is None:
        skipped = [c for c in cases if not c.get("automatable", True)]

    # Hand-edit conflicts: cases changed but the on-disk file no longer
    # matches what we wrote, so the fresh version landed beside it.
    conflicts_md = ""
    if conflicts:
        rows = "\n".join(f"- `{orig}` → `{new}`" for orig, new in conflicts)
        conflicts_md = (
            f"\n## Conflicts ({len(conflicts)})\n"
            f"These files were hand-edited after generation, but their test "
            f"cases changed since. The regenerated version was written beside "
            f"each — merge manually, then delete the `.new` file:\n{rows}\n")

    # Optional verification sections (only when the verify gate ran)
    verify_md = ""
    if verify is not None:
        steps = "\n".join(
            f"- {'✓' if s['ok'] else '✗'} `{s['name']}` — {s['detail']}"
            for s in verify["steps"])
        verify_md = (f"\n## Verification: {verify['status']}\n{steps}\n")
        if needs_manual:
            details = "\n".join(
                f"- `{f}`\n" + "\n".join(f"  - {m}" for m in verify["errors"].get(f, []))
                for f in needs_manual)
            verify_md += (f"\n## Needs manual fix ({len(needs_manual)})\n"
                          f"These files still fail to compile after one "
                          f"automatic repair round:\n{details}\n")

    report = f"""# Automation Report

Generated {len(files)} files from {len(cases)} total test cases.

## Files Written ({len(files)})
{chr(10).join(f'- `{f}`' for f in files) or '_None_'}

## Skipped (non-automatable, {len(skipped)})
{chr(10).join(f'- **{c["id"]}** — {c["title"]}' for c in skipped) or '_None_'}
{conflicts_md}{verify_md}
## Next Steps
```bash
npm install
npx playwright install
cp .env.example .env
npm test
```
"""
    (root / "AUTOMATION_REPORT.md").write_text(report)