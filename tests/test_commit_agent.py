import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sprint_issues.json").read_text()
)


def _mock_github_prs(prs: list[dict]):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = prs
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def test_skips_when_no_github_token(monkeypatch):
    from agents.commit_agent import run

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    findings = run(FIXTURES)
    assert findings == []


def test_closed_ticket_no_pr():
    from agents.commit_agent import run

    import os
    with patch.dict(os.environ, {"GITHUB_TOKEN": "tok", "GITHUB_REPO": "org/repo"}):
        with patch("agents.commit_agent._fetch_prs") as mock_prs, \
             patch("agents.commit_agent._fetch_branches") as mock_branches:
            mock_prs.return_value = []
            mock_branches.return_value = []

            # ENG-11 is Done but no matching PR
            findings = run(FIXTURES)
            done_flags = [f for f in findings if f["key"] == "ENG-11"]
            assert any("no pr" in f["reason"].lower() or "no commit" in f["reason"].lower()
                       for f in done_flags)


def test_merged_pr_open_ticket():
    from agents.commit_agent import run

    import os
    with patch.dict(os.environ, {"GITHUB_TOKEN": "tok", "GITHUB_REPO": "org/repo"}):
        with patch("agents.commit_agent._fetch_prs") as mock_prs, \
             patch("agents.commit_agent._fetch_branches") as mock_branches:
            mock_prs.return_value = [
                {
                    "title": "Fix ENG-1 login timeout",
                    "body": "Closes ENG-1",
                    "state": "closed",
                    "merged_at": "2026-06-27T10:00:00Z",
                    "head": {"ref": "fix/ENG-1-login-timeout"},
                }
            ]
            mock_branches.return_value = []

            # ENG-1 is "In Progress" but PR is merged → HIGH
            findings = run(FIXTURES)
            eng1 = next(
                (f for f in findings if f["key"] == "ENG-1" and "merged" in f["reason"].lower()),
                None
            )
            assert eng1 is not None
            assert eng1["severity"] == "HIGH"


def test_schema():
    from agents.commit_agent import run

    import os
    with patch.dict(os.environ, {"GITHUB_TOKEN": "tok", "GITHUB_REPO": "org/repo"}):
        with patch("agents.commit_agent._fetch_prs") as mock_prs, \
             patch("agents.commit_agent._fetch_branches") as mock_branches:
            mock_prs.return_value = []
            mock_branches.return_value = []
            findings = run(FIXTURES)
            for f in findings:
                assert {"agent", "key", "severity", "reason", "url"} <= set(f.keys())
                assert f["agent"] == "commit"
