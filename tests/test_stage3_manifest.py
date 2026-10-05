"""Tests for the Stage-3 regeneration manifest (stages.py).

Everything runs offline: _decide_regen is pure hashing against tmp_path
files and manifest entries — no LLM, no subprocess.
"""

from __future__ import annotations

from pathlib import Path

from stages import (_cases_hash, _conflict_path, _decide_regen,
                    _load_manifest, _save_manifest, _sha256)

CASES = [{"id": "TC-001", "title": "Login works", "requirement_id": "REQ-1"}]
CASES_V2 = [{"id": "TC-001", "title": "Login works twice", "requirement_id": "REQ-1"}]
CODE = "import { test } from '../fixtures/test';\n"


def _entry(content: str, cases: list[dict]) -> dict:
    """Manifest record as stage 3 writes it for a generated file."""
    return {"file_sha256": _sha256(content), "cases_sha256": _cases_hash(cases)}


# ──────────────────────────────────────────────────────────────────────────────
# _decide_regen — one test per branch of the decision table
# ──────────────────────────────────────────────────────────────────────────────

def test_missing_file_is_written(tmp_path: Path):
    path = tmp_path / "req-1.spec.ts"
    assert _decide_regen(path, _cases_hash(CASES), None) == "write"


def test_regen_all_overwrites_even_hand_edits(tmp_path: Path):
    path = tmp_path / "req-1.spec.ts"
    path.write_text("// hand-edited\n" + CODE)
    entry = _entry(CODE, CASES)
    assert _decide_regen(path, _cases_hash(CASES_V2), entry, regen="all") == "write"


def test_untracked_existing_file_is_skipped(tmp_path: Path):
    # Pre-manifest project (or hand-created file): old skip-if-exists behavior
    path = tmp_path / "req-1.spec.ts"
    path.write_text(CODE)
    assert _decide_regen(path, _cases_hash(CASES), None) == "skip"


def test_unchanged_cases_are_skipped(tmp_path: Path):
    path = tmp_path / "req-1.spec.ts"
    path.write_text(CODE)
    assert _decide_regen(path, _cases_hash(CASES), _entry(CODE, CASES)) == "skip"


def test_unchanged_cases_skip_even_if_file_hand_edited(tmp_path: Path):
    path = tmp_path / "req-1.spec.ts"
    path.write_text("// hand-edited\n" + CODE)
    assert _decide_regen(path, _cases_hash(CASES), _entry(CODE, CASES)) == "skip"


def test_changed_cases_pristine_file_regenerates_in_place(tmp_path: Path):
    path = tmp_path / "req-1.spec.ts"
    path.write_text(CODE)
    assert _decide_regen(path, _cases_hash(CASES_V2), _entry(CODE, CASES)) == "write"


def test_changed_cases_hand_edited_file_conflicts(tmp_path: Path):
    path = tmp_path / "req-1.spec.ts"
    path.write_text("// hand-edited\n" + CODE)
    assert _decide_regen(path, _cases_hash(CASES_V2), _entry(CODE, CASES)) == "conflict"


# ──────────────────────────────────────────────────────────────────────────────
# Supporting pieces — hashing, conflict naming, manifest I/O
# ──────────────────────────────────────────────────────────────────────────────

def test_cases_hash_ignores_key_order():
    reordered = [{"requirement_id": "REQ-1", "title": "Login works", "id": "TC-001"}]
    assert _cases_hash(CASES) == _cases_hash(reordered)


def test_cases_hash_changes_with_content():
    assert _cases_hash(CASES) != _cases_hash(CASES_V2)


def test_conflict_path_keeps_spec_suffix():
    assert _conflict_path(Path("tests/specs/req-1.spec.ts")).name == "req-1.spec.new.ts"
    assert _conflict_path(Path("tests/pages/LoginPage.ts")).name == "LoginPage.new.ts"


def test_manifest_roundtrip(tmp_path: Path):
    manifest = {"tests/specs/req-1.spec.ts": _entry(CODE, CASES)}
    _save_manifest(tmp_path, manifest)
    assert (tmp_path / ".specwright" / "manifest.json").exists()
    assert _load_manifest(tmp_path) == manifest


def test_manifest_missing_or_corrupt_reads_as_empty(tmp_path: Path):
    assert _load_manifest(tmp_path) == {}
    (tmp_path / ".specwright").mkdir()
    (tmp_path / ".specwright" / "manifest.json").write_text("not json{")
    assert _load_manifest(tmp_path) == {}
