"""Direct Jira push with upsert semantics.

One Jira issue per test case, keyed by a ``specwright-<tc-id>`` label:
a push searches for that label first and updates the match, creating the
issue only when none exists — so re-pushing never duplicates. Uses the
REST v2 API (plain-text descriptions) with email + API-token basic auth.

Config (the ``jira`` block in config.yaml, ${ENV_VAR} values resolved by
config.load_config):
    base_url     https://yourteam.atlassian.net          (required)
    project_key  e.g. QA                                 (required)
    issue_type   issue type name, default "Test"
    email        falls back to the JIRA_EMAIL env var
    api_token    falls back to the JIRA_TOKEN env var
"""

from __future__ import annotations

import os

import requests

from exporters import _priority_to_jira, build_jira_description

# Issues are matched on this label, which makes the push idempotent
LABEL_PREFIX = "specwright-"

_TIMEOUT = 30  # seconds per HTTP request


class JiraPushError(RuntimeError):
    """Config incomplete, credentials missing, or Jira rejected a request."""


def push_cases(cases: list[dict], jira_cfg: dict) -> dict:
    """Upsert every case into Jira. Returns ``{"created": n, "updated": n,
    "keys": {tc_id: issue_key}}`` and stamps each pushed case with
    ``case["external_ids"] = {"jira": "KEY-123"}`` — the caller persists
    the cases. Raises JiraPushError on the first failure."""
    base_url = (jira_cfg.get("base_url") or "").rstrip("/")
    project_key = jira_cfg.get("project_key") or ""
    if not base_url or not project_key:
        raise JiraPushError(
            "Jira config incomplete — set 'base_url' and 'project_key' "
            "in the config's jira block (or the app sidebar).")
    issue_type = jira_cfg.get("issue_type") or "Test"
    auth = _resolve_credentials(jira_cfg)

    created = updated = 0
    keys: dict[str, str] = {}
    for c in cases:
        label = f"{LABEL_PREFIX}{c.get('id', '')}"
        fields = _issue_fields(c, project_key, issue_type, label)
        key = _find_existing(base_url, auth, label)
        if key:
            resp = _request("put", f"{base_url}/rest/api/2/issue/{key}",
                            auth, json={"fields": fields})
            _check(resp, f"Updating {key} for {c.get('id', '?')}")
            updated += 1
        else:
            resp = _request("post", f"{base_url}/rest/api/2/issue",
                            auth, json={"fields": fields})
            _check(resp, f"Creating issue for {c.get('id', '?')}")
            key = resp.json().get("key", "")
            created += 1
        c.setdefault("external_ids", {})["jira"] = key
        keys[c.get("id", "")] = key
    return {"created": created, "updated": updated, "keys": keys}


def _resolve_credentials(jira_cfg: dict) -> tuple[str, str]:
    """(email, api_token) from the config block, env vars as fallback."""
    email = jira_cfg.get("email") or os.environ.get("JIRA_EMAIL", "")
    token = jira_cfg.get("api_token") or os.environ.get("JIRA_TOKEN", "")
    if not email or not token:
        raise JiraPushError(
            "Jira credentials missing — set the JIRA_EMAIL and JIRA_TOKEN "
            "env vars (or 'email'/'api_token' in the config's jira block).")
    return email, token


def _issue_fields(c: dict, project_key: str, issue_type: str,
                  label: str) -> dict:
    """Issue fields for one case — summary/description/labels mirror the
    Jira CSV export so both routes land identical content."""
    labels = [label] + [v for v in (
        c.get("type", ""),
        c.get("target", ""),
        c.get("priority", ""),
        c.get("requirement_id", ""),
    ) if v]
    return {
        "project": {"key": project_key},
        "issuetype": {"name": issue_type},
        "summary": f"[{c.get('id', '')}] {c.get('title', '')}",
        "description": build_jira_description(c),
        "priority": {"name": _priority_to_jira(c.get("priority", "P2"))},
        "labels": labels,
    }


def _find_existing(base_url: str, auth: tuple[str, str],
                   label: str) -> str | None:
    """Issue key carrying the case's specwright label, or None."""
    resp = _request("get", f"{base_url}/rest/api/2/search", auth,
                    params={"jql": f'labels = "{label}"',
                            "maxResults": 1, "fields": "key"})
    _check(resp, f"Searching for label {label}")
    issues = resp.json().get("issues") or []
    return issues[0].get("key") if issues else None


def _request(method: str, url: str, auth: tuple[str, str], **kwargs):
    """One HTTP call with auth + timeout; network errors → JiraPushError."""
    try:
        return getattr(requests, method)(url, auth=auth, timeout=_TIMEOUT,
                                         **kwargs)
    except requests.RequestException as e:
        raise JiraPushError(f"Jira request failed ({method.upper()} {url}): {e}")


def _check(resp, what: str) -> None:
    if resp.status_code >= 400:
        raise JiraPushError(f"{what} failed (HTTP {resp.status_code}): "
                            f"{resp.text[:300]}")
