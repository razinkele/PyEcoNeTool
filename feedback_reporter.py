"""User Feedback Collection and Reporting for EconetPy.

Ported from MarineSABRES SESToolbox's `functions/feedback_reporter.R`
(2026-03-24 spec). Functional equivalents in Python with stdlib only —
no third-party HTTP dep.

Public API:
    collect_system_context()  - snapshot of session/project state
    save_feedback_local()     - append one NDJSON line to the feedback log
    create_github_issue()     - POST a new issue to GitHub (requires token)
    submit_feedback()         - orchestrate local save + optional GitHub post
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger("econetpy.feedback")

# Project root: this module sits in the project root, so __file__'s parent is it.
PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_LOG_PATH = PROJECT_ROOT / "data" / "user_feedback_log.ndjson"
DEFAULT_VERSION_PATH = PROJECT_ROOT / "VERSION"

LABEL_MAP: dict[str, list[str]] = {
    "bug": ["bug", "user-reported"],
    "suggestion": ["enhancement", "user-reported"],
    "general": ["feedback", "user-reported"],
}


@dataclass(frozen=True)
class SubmissionResult:
    """Outcome of submit_feedback() — three flags + optional issue URL."""

    local_success: bool
    github_success: bool
    github_url: Optional[str]


def collect_system_context(
    *,
    current_tab: str = "unknown",
    browser_info: str = "unknown",
    user_level: str = "unknown",
    language: str = "en",
    species_count: int = 0,
    edge_count: int = 0,
    version_path: Path = DEFAULT_VERSION_PATH,
) -> dict[str, Any]:
    """Snapshot of app/session/project state at modal-open time.

    Args mirror the R version but adapted to EconetPy's domain:
    species_count / edge_count replace the ISA element_count /
    connection_count from Marine-SABRES.
    """
    try:
        lines = Path(version_path).read_text(encoding="utf-8").splitlines()
        app_version = lines[0].strip() if lines else "unknown"
    except (OSError, IndexError) as exc:
        logger.warning("collect_system_context app_version: %s", exc)
        app_version = "unknown"

    return {
        "app_version": app_version,
        "user_level": user_level,
        "current_tab": current_tab or "unknown",
        "browser_info": browser_info or "unknown",
        "language": language,
        "species_count": int(species_count),
        "edge_count": int(edge_count),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def save_feedback_local(
    payload: dict[str, Any],
    path: Path = DEFAULT_LOG_PATH,
) -> bool:
    """Append `payload` as one NDJSON line to `path`. Returns True on success."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, default=str) + "\n")
        return True
    except OSError as exc:
        logger.error("save_feedback_local failed: %s", exc)
        return False


def create_github_issue(
    title: str,
    body: str,
    labels: Iterable[str] = (),
    *,
    timeout: float = 10.0,
) -> Optional[dict[str, Any]]:
    """POST a new issue to GitHub via the REST API.

    Reads `ECONETPY_GITHUB_TOKEN` from the environment. Returns None if the
    token is absent or on any HTTP / network error.

    On success returns ``{"url": html_url, "number": issue_number}``.
    """
    token = os.environ.get("ECONETPY_GITHUB_TOKEN", "")
    if not token:
        logger.info("create_github_issue: ECONETPY_GITHUB_TOKEN not set")
        return None

    repo_owner = os.environ.get("ECONETPY_GITHUB_OWNER", "razinkele")
    repo_name = os.environ.get("ECONETPY_GITHUB_REPO", "PyEcoNeTool")
    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues"

    payload = json.dumps(
        {"title": title, "body": body, "labels": list(labels)}
    ).encode("utf-8")
    req = urllib.request.Request(
        url=api_url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "econetpy-feedback/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status in (200, 201):
                parsed = json.loads(resp.read().decode("utf-8"))
                return {
                    "url": parsed.get("html_url", "unknown"),
                    "number": parsed.get("number"),
                }
            logger.error("create_github_issue: HTTP %s", resp.status)
            return None
    except urllib.error.HTTPError as exc:
        logger.error("create_github_issue HTTP %s: %s", exc.code, exc.reason)
        return None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.error("create_github_issue network: %s", exc)
        return None
    except (ValueError, KeyError) as exc:
        logger.error("create_github_issue parse: %s", exc)
        return None


def _build_issue_body(description: str, steps: str, context: dict[str, Any]) -> str:
    """Markdown body for the GitHub issue: description, steps (if any),
    collapsible JSON of context."""
    parts = [f"## Description\n\n{description}"]
    if steps.strip():
        parts.append(f"\n\n## Steps to Reproduce\n\n{steps}")
    context_json = json.dumps(context, indent=2, default=str)
    parts.append(
        "\n\n<details>\n<summary>System Context</summary>\n\n"
        f"```json\n{context_json}\n```\n\n</details>"
    )
    return "".join(parts)


def submit_feedback(
    *,
    title: str,
    description: str,
    type_: str = "general",
    steps: str = "",
    context: Optional[dict[str, Any]] = None,
    log_path: Path = DEFAULT_LOG_PATH,
) -> SubmissionResult:
    """Orchestrate local save + optional GitHub Issue creation.

    Validation errors (empty title/description) raise ValueError —
    the caller is responsible for user-facing message.
    """
    if not title.strip():
        raise ValueError("title is required")
    if not description.strip():
        raise ValueError("description is required")

    ctx = context or {}
    labels = LABEL_MAP.get(type_, LABEL_MAP["general"])
    issue_body = _build_issue_body(description, steps, ctx)

    local_payload: dict[str, Any] = {
        "title": title,
        "description": description,
        "type": type_,
        "steps": steps,
        "labels": labels,
        "github_url": None,
        **ctx,
    }
    local_ok = save_feedback_local(local_payload, path=log_path)

    gh = create_github_issue(title, issue_body, labels)
    github_ok = gh is not None
    github_url = gh["url"] if github_ok else None

    # If GitHub succeeded, append a corrected entry with the URL. The original
    # entry remains (acceptable for NDJSON; matches the R behaviour).
    if github_ok and local_ok:
        save_feedback_local({**local_payload, "github_url": github_url}, path=log_path)

    return SubmissionResult(
        local_success=local_ok,
        github_success=github_ok,
        github_url=github_url,
    )
