"""Tests for the direct Jira push (integrations/jira_push.py).

All HTTP goes through monkeypatched requests.get/post/put fakes — nothing
touches the network. Covers the upsert decision (existing label → PUT,
missing → POST), the specwright-<TC-ID> label, external_ids recording,
the shared description builder, and the config/credential error paths.
"""

from __future__ import annotations

import json

import pytest

from exporters import build_jira_description
from integrations import jira_push
from integrations.jira_push import JiraPushError, push_cases


def _case(tc_id: str = "TC-001") -> dict:
    return {
        "id": tc_id,
        "requirement_id": "REQ-1",
        "title": f"case {tc_id}",
        "type": "functional",
        "target": "api",
        "priority": "P0",
        "preconditions": ["logged in"],
        "steps": [{"action": "do it", "data": "x=1"}],
        "expected": "works",
        "automatable": True,
    }


CFG = {"base_url": "https://jira.example.com", "project_key": "QA"}


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = json.dumps(self._payload)

    def json(self) -> dict:
        return self._payload


class FakeHttp:
    """Records every call; serves canned search results and create keys."""

    def __init__(self, existing: dict[str, str] | None = None):
        self.existing = existing or {}  # label -> issue key
        self.calls: list[tuple[str, str, dict]] = []
        self.created = 0

    def install(self, monkeypatch) -> None:
        monkeypatch.setattr(jira_push.requests, "get", self._get)
        monkeypatch.setattr(jira_push.requests, "post", self._post)
        monkeypatch.setattr(jira_push.requests, "put", self._put)

    def _get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        label = kwargs["params"]["jql"].split('"')[1]
        key = self.existing.get(label)
        return FakeResponse(200, {"issues": [{"key": key}] if key else []})

    def _post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        self.created += 1
        return FakeResponse(201, {"key": f"QA-{100 + self.created}"})

    def _put(self, url, **kwargs):
        self.calls.append(("put", url, kwargs))
        return FakeResponse(204, {})


@pytest.fixture(autouse=True)
def _env_creds(monkeypatch):
    monkeypatch.setenv("JIRA_EMAIL", "qa@example.com")
    monkeypatch.setenv("JIRA_TOKEN", "tok-123")


# ──────────────────────────────────────────────────────────────────────────────
# Upsert decision — existing label updates, missing label creates
# ──────────────────────────────────────────────────────────────────────────────

def test_missing_label_creates_issue_and_records_external_id(monkeypatch):
    http = FakeHttp()
    http.install(monkeypatch)
    case = _case()

    result = push_cases([case], CFG)

    assert (result["created"], result["updated"]) == (1, 0)
    assert case["external_ids"] == {"jira": "QA-101"}
    assert result["keys"] == {"TC-001": "QA-101"}
    methods = [m for m, _, _ in http.calls]
    assert methods == ["get", "post"]
    _, url, kwargs = http.calls[1]
    assert url == "https://jira.example.com/rest/api/2/issue"
    assert "specwright-TC-001" in kwargs["json"]["fields"]["labels"]


def test_existing_label_updates_issue_in_place(monkeypatch):
    http = FakeHttp(existing={"specwright-TC-001": "QA-7"})
    http.install(monkeypatch)
    case = _case()

    result = push_cases([case], CFG)

    assert (result["created"], result["updated"]) == (0, 1)
    assert case["external_ids"] == {"jira": "QA-7"}
    methods = [m for m, _, _ in http.calls]
    assert methods == ["get", "put"]
    _, url, kwargs = http.calls[1]
    assert url == "https://jira.example.com/rest/api/2/issue/QA-7"
    assert "specwright-TC-001" in kwargs["json"]["fields"]["labels"]


def test_mixed_batch_counts_creates_and_updates(monkeypatch):
    http = FakeHttp(existing={"specwright-TC-001": "QA-7"})
    http.install(monkeypatch)
    cases = [_case("TC-001"), _case("TC-002")]

    result = push_cases(cases, CFG)

    assert (result["created"], result["updated"]) == (1, 1)
    assert cases[0]["external_ids"]["jira"] == "QA-7"
    assert cases[1]["external_ids"]["jira"] == "QA-101"


def test_search_jql_targets_the_case_label(monkeypatch):
    http = FakeHttp()
    http.install(monkeypatch)
    push_cases([_case("TC-042")], CFG)

    _, url, kwargs = http.calls[0]
    assert url == "https://jira.example.com/rest/api/2/search"
    assert kwargs["params"]["jql"] == 'labels = "specwright-TC-042"'


def test_description_matches_the_csv_exporters_builder(monkeypatch):
    http = FakeHttp()
    http.install(monkeypatch)
    case = _case()
    push_cases([case], CFG)

    fields = http.calls[1][2]["json"]["fields"]
    assert fields["description"] == build_jira_description(case)
    assert fields["summary"] == "[TC-001] case TC-001"
    assert fields["project"] == {"key": "QA"}
    assert fields["issuetype"] == {"name": "Test"}
    assert fields["priority"] == {"name": "Highest"}


def test_issue_type_from_config_overrides_default(monkeypatch):
    http = FakeHttp()
    http.install(monkeypatch)
    push_cases([_case()], {**CFG, "issue_type": "Test Case"})

    fields = http.calls[1][2]["json"]["fields"]
    assert fields["issuetype"] == {"name": "Test Case"}


# ──────────────────────────────────────────────────────────────────────────────
# Error paths — incomplete config, missing credentials, HTTP failures
# ──────────────────────────────────────────────────────────────────────────────

def test_missing_base_url_or_project_key_raises():
    with pytest.raises(JiraPushError, match="base_url"):
        push_cases([_case()], {"project_key": "QA"})
    with pytest.raises(JiraPushError, match="project_key"):
        push_cases([_case()], {"base_url": "https://jira.example.com"})


def test_missing_credentials_raises(monkeypatch):
    monkeypatch.delenv("JIRA_EMAIL")
    monkeypatch.delenv("JIRA_TOKEN")
    with pytest.raises(JiraPushError, match="JIRA_EMAIL"):
        push_cases([_case()], CFG)


def test_config_credentials_beat_env(monkeypatch):
    monkeypatch.delenv("JIRA_EMAIL")
    monkeypatch.delenv("JIRA_TOKEN")
    http = FakeHttp()
    http.install(monkeypatch)

    push_cases([_case()], {**CFG, "email": "cfg@example.com",
                           "api_token": "cfg-tok"})

    assert http.calls[0][2]["auth"] == ("cfg@example.com", "cfg-tok")


def test_http_error_raises_with_status_and_body(monkeypatch):
    http = FakeHttp()
    http.install(monkeypatch)
    monkeypatch.setattr(
        jira_push.requests, "post",
        lambda url, **kw: FakeResponse(400, {"errors": {"labels": "nope"}}))

    with pytest.raises(JiraPushError, match="HTTP 400"):
        push_cases([_case()], CFG)
