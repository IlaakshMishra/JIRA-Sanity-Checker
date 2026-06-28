import json
from pathlib import Path

import pytest

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sprint_issues.json").read_text()
)


def test_stale_in_progress_detected():
    from agents.staleness_agent import run

    # ENG-1: In Progress, 6 days since update → HIGH
    findings = run(FIXTURES)
    keys = [f["key"] for f in findings]
    assert "ENG-1" in keys

    eng1 = next(f for f in findings if f["key"] == "ENG-1")
    assert eng1["severity"] == "HIGH"
    assert eng1["agent"] == "staleness"


def test_stale_in_review_detected():
    from agents.staleness_agent import run

    # ENG-7: In Review, 4 days → MEDIUM (>= 3 threshold, not > 5)
    findings = run(FIXTURES)
    eng7 = next((f for f in findings if f["key"] == "ENG-7"), None)
    assert eng7 is not None
    assert eng7["severity"] == "MEDIUM"


def test_unassigned_in_progress():
    from agents.staleness_agent import run

    # ENG-2: In Progress, no assignee → HIGH
    findings = run(FIXTURES)
    eng2_findings = [f for f in findings if f["key"] == "ENG-2"]
    assert any(f["severity"] == "HIGH" for f in eng2_findings)


def test_fresh_issue_not_flagged():
    from agents.staleness_agent import run

    # ENG-6: To Do (not In Progress/In Review) — should not be flagged by staleness
    findings = run(FIXTURES)
    eng6_staleness = [
        f for f in findings
        if f["key"] == "ENG-6" and f["agent"] == "staleness"
    ]
    # ENG-6 is To Do, not In Progress/In Review, no stale flag
    assert all(f["key"] != "ENG-6" for f in eng6_staleness)


def test_done_issue_not_flagged():
    from agents.staleness_agent import run

    # ENG-11: Done — never flagged
    findings = run(FIXTURES)
    assert all(f["key"] != "ENG-11" for f in findings)


def test_returns_list_of_dicts():
    from agents.staleness_agent import run

    findings = run(FIXTURES)
    assert isinstance(findings, list)
    for f in findings:
        assert {"agent", "key", "severity", "reason", "url"} <= set(f.keys())


def test_clean_sprint_returns_empty():
    from agents.staleness_agent import run

    clean = [
        {**i, "days_since_update": 0, "days_since_last_comment": 0,
         "status": "To Do", "assignee": "Someone"}
        for i in FIXTURES
    ]
    assert run(clean) == []
