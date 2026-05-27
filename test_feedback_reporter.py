"""Unit tests for feedback_reporter.py.

Mirrors the structure of MarineSABRES' test-feedback-reporter.R but
adapted to pytest + EconetPy's domain. No live HTTP calls — GitHub
paths are exercised via monkey-patching urllib.request.urlopen.

Run: pytest test_feedback_reporter.py -v
"""

from __future__ import annotations

import io
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from feedback_reporter import (
    LABEL_MAP,
    SubmissionResult,
    _build_issue_body,
    collect_system_context,
    create_github_issue,
    save_feedback_local,
    submit_feedback,
)


# ---------------------------------------------------------------------------
# collect_system_context
# ---------------------------------------------------------------------------

def test_collect_system_context_returns_all_expected_fields(tmp_path):
    version_file = tmp_path / "VERSION"
    version_file.write_text("1.2.3\n", encoding="utf-8")
    ctx = collect_system_context(
        current_tab="topology",
        browser_info="Mozilla/5.0 (Test)",
        user_level="beginner",
        language="en",
        species_count=5,
        edge_count=8,
        version_path=version_file,
    )
    expected = {
        "app_version",
        "user_level",
        "current_tab",
        "browser_info",
        "language",
        "species_count",
        "edge_count",
        "timestamp",
    }
    assert expected.issubset(ctx.keys())
    assert ctx["app_version"] == "1.2.3"
    assert ctx["current_tab"] == "topology"
    assert ctx["browser_info"] == "Mozilla/5.0 (Test)"
    assert ctx["user_level"] == "beginner"
    assert ctx["language"] == "en"
    assert ctx["species_count"] == 5
    assert ctx["edge_count"] == 8


def test_collect_system_context_timestamp_is_iso8601_utc(tmp_path):
    ctx = collect_system_context(version_path=tmp_path / "no-such-VERSION")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", ctx["timestamp"])


def test_collect_system_context_handles_missing_version_file(tmp_path):
    ctx = collect_system_context(version_path=tmp_path / "no-such-VERSION")
    assert ctx["app_version"] == "unknown"


def test_collect_system_context_defaults_to_unknown_when_inputs_empty(tmp_path):
    ctx = collect_system_context(
        current_tab="", browser_info="", version_path=tmp_path / "no-such-VERSION"
    )
    assert ctx["current_tab"] == "unknown"
    assert ctx["browser_info"] == "unknown"
    assert ctx["species_count"] == 0
    assert ctx["edge_count"] == 0


# ---------------------------------------------------------------------------
# save_feedback_local
# ---------------------------------------------------------------------------

def test_save_feedback_local_writes_valid_ndjson(tmp_path):
    log = tmp_path / "logs" / "feedback.ndjson"  # nested dir auto-created
    payload = {"title": "x", "description": "y", "n": 42}
    assert save_feedback_local(payload, path=log) is True
    raw = log.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    parsed = json.loads(raw)
    assert parsed["title"] == "x"
    assert parsed["n"] == 42


def test_save_feedback_local_appends_without_corrupting(tmp_path):
    log = tmp_path / "feedback.ndjson"
    save_feedback_local({"a": 1}, path=log)
    save_feedback_local({"a": 2}, path=log)
    save_feedback_local({"a": 3}, path=log)
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    assert [json.loads(line)["a"] for line in lines] == [1, 2, 3]


def test_save_feedback_local_returns_false_on_write_error(tmp_path, monkeypatch):
    log = tmp_path / "feedback.ndjson"

    def boom(*args, **kwargs):
        raise OSError("simulated disk full")

    monkeypatch.setattr(Path, "open", boom)
    assert save_feedback_local({"x": 1}, path=log) is False


# ---------------------------------------------------------------------------
# create_github_issue
# ---------------------------------------------------------------------------

def test_create_github_issue_returns_none_when_token_missing(monkeypatch):
    monkeypatch.delenv("ECONETPY_GITHUB_TOKEN", raising=False)
    assert create_github_issue("t", "b") is None


def test_create_github_issue_builds_correct_request(monkeypatch):
    """Verify the POST request is constructed with the right URL, headers,
    and JSON body. Mocks urlopen so no real HTTP happens."""
    monkeypatch.setenv("ECONETPY_GITHUB_TOKEN", "ghp_fake_token")
    monkeypatch.setenv("ECONETPY_GITHUB_OWNER", "testowner")
    monkeypatch.setenv("ECONETPY_GITHUB_REPO", "testrepo")

    captured: dict[str, Any] = {}

    class FakeResp:
        status = 201

        def read(self):
            return json.dumps(
                {"html_url": "https://github.com/o/r/issues/7", "number": 7}
            ).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = create_github_issue("the-title", "the-body", ["bug", "user-reported"])

    assert result == {"url": "https://github.com/o/r/issues/7", "number": 7}
    assert captured["url"] == "https://api.github.com/repos/testowner/testrepo/issues"
    assert captured["method"] == "POST"
    # Header keys come back title-cased.
    headers_lc = {k.lower(): v for k, v in captured["headers"].items()}
    assert headers_lc["authorization"] == "Bearer ghp_fake_token"
    assert headers_lc["accept"] == "application/vnd.github+json"
    assert captured["body"] == {
        "title": "the-title",
        "body": "the-body",
        "labels": ["bug", "user-reported"],
    }
    assert captured["timeout"] == 10.0  # default


def test_create_github_issue_returns_none_on_http_error(monkeypatch):
    monkeypatch.setenv("ECONETPY_GITHUB_TOKEN", "ghp_fake_token")

    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(
            req.full_url, 422, "Unprocessable", hdrs=None, fp=io.BytesIO(b"")
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert create_github_issue("t", "b") is None


def test_create_github_issue_returns_none_on_network_error(monkeypatch):
    monkeypatch.setenv("ECONETPY_GITHUB_TOKEN", "ghp_fake_token")

    def fake_urlopen(req, timeout):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert create_github_issue("t", "b") is None


# ---------------------------------------------------------------------------
# _build_issue_body
# ---------------------------------------------------------------------------

def test_build_issue_body_omits_steps_section_when_empty():
    body = _build_issue_body("desc here", "", {"k": "v"})
    assert "## Description" in body
    assert "desc here" in body
    assert "Steps to Reproduce" not in body
    assert "<details>" in body and "</details>" in body
    assert '"k": "v"' in body


def test_build_issue_body_includes_steps_section_when_provided():
    body = _build_issue_body("desc", "1. open\n2. click", {})
    assert "## Steps to Reproduce" in body
    assert "1. open" in body


# ---------------------------------------------------------------------------
# submit_feedback
# ---------------------------------------------------------------------------

def test_submit_feedback_validates_title_required(tmp_path):
    with pytest.raises(ValueError, match="title"):
        submit_feedback(
            title="  ", description="x", log_path=tmp_path / "f.ndjson"
        )


def test_submit_feedback_validates_description_required(tmp_path):
    with pytest.raises(ValueError, match="description"):
        submit_feedback(
            title="t", description="\n\t  ", log_path=tmp_path / "f.ndjson"
        )


def test_submit_feedback_local_only_when_token_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("ECONETPY_GITHUB_TOKEN", raising=False)
    log = tmp_path / "f.ndjson"
    result = submit_feedback(
        title="my title",
        description="my desc",
        type_="bug",
        steps="1. step",
        context={"app_version": "9.9.9"},
        log_path=log,
    )
    assert isinstance(result, SubmissionResult)
    assert result.local_success is True
    assert result.github_success is False
    assert result.github_url is None
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").strip().splitlines()]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["title"] == "my title"
    assert entry["type"] == "bug"
    assert entry["labels"] == ["bug", "user-reported"]
    assert entry["app_version"] == "9.9.9"


def test_submit_feedback_records_github_url_when_succeeds(tmp_path, monkeypatch):
    monkeypatch.setenv("ECONETPY_GITHUB_TOKEN", "ghp_fake")
    log = tmp_path / "f.ndjson"

    class FakeResp:
        status = 201

        def read(self):
            return json.dumps(
                {"html_url": "https://github.com/x/y/issues/42", "number": 42}
            ).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: FakeResp())
    result = submit_feedback(
        title="t", description="d", type_="suggestion", log_path=log
    )
    assert result.local_success is True
    assert result.github_success is True
    assert result.github_url == "https://github.com/x/y/issues/42"
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").strip().splitlines()]
    # Two entries: original (no URL) + correction (with URL). NDJSON-append pattern.
    assert len(entries) == 2
    assert entries[0]["github_url"] is None
    assert entries[1]["github_url"] == "https://github.com/x/y/issues/42"


def test_submit_feedback_label_mapping_falls_back_for_unknown_type(tmp_path, monkeypatch):
    monkeypatch.delenv("ECONETPY_GITHUB_TOKEN", raising=False)
    log = tmp_path / "f.ndjson"
    result = submit_feedback(
        title="t", description="d", type_="totally-made-up", log_path=log
    )
    assert result.local_success is True
    entry = json.loads(log.read_text(encoding="utf-8").strip().splitlines()[0])
    assert entry["labels"] == LABEL_MAP["general"]
