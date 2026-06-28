import json
from pathlib import Path

import pytest

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sprint_issues.json").read_text()
)


def test_critical_no_assignee():
    from agents.priority_agent import run

    # ENG-3: Highest priority, no assignee → HIGH
    findings = run(FIXTURES)
    eng3 = next(
        (f for f in findings if f["key"] == "ENG-3" and "assignee" in f["reason"].lower()),
        None
    )
    assert eng3 is not None
    assert eng3["severity"] == "HIGH"


def test_critical_no_due_date():
    from agents.priority_agent import run

    # ENG-3: Highest priority, no due date → HIGH
    findings = run(FIXTURES)
    eng3_due = next(
        (f for f in findings if f["key"] == "ENG-3" and "due date" in f["reason"].lower()),
        None
    )
    assert eng3_due is not None
    assert eng3_due["severity"] == "HIGH"


def test_label_priority_mismatch():
    from agents.priority_agent import run

    # ENG-6: labels=["priority-high"], priority="Medium" → MEDIUM
    findings = run(FIXTURES)
    eng6 = next(
        (f for f in findings if f["key"] == "ENG-6" and "mismatch" in f["reason"].lower()),
        None
    )
    assert eng6 is not None
    assert eng6["severity"] == "MEDIUM"


def test_orphaned_escalation():
    from agents.priority_agent import run

    # ENG-8: labels=["escalated"], has_escalation_link=False → HIGH
    findings = run(FIXTURES)
    eng8 = next(
        (f for f in findings if f["key"] == "ENG-8" and "escalat" in f["reason"].lower()),
        None
    )
    assert eng8 is not None
    assert eng8["severity"] == "HIGH"


def test_no_false_positives_on_clean_issue():
    from agents.priority_agent import run

    # ENG-7: Medium priority, has assignee, no escalation label → no priority findings
    findings = run(FIXTURES)
    eng7 = [f for f in findings if f["key"] == "ENG-7"]
    assert len(eng7) == 0


def test_schema():
    from agents.priority_agent import run

    findings = run(FIXTURES)
    for f in findings:
        assert {"agent", "key", "severity", "reason", "url"} <= set(f.keys())
        assert f["agent"] == "priority"
