import json
from pathlib import Path

import pytest

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sprint_issues.json").read_text()
)


def test_missing_story_points():
    from agents.estimation_agent import run

    # ENG-4: story_points=None → HIGH
    findings = run(FIXTURES)
    eng4 = next((f for f in findings if f["key"] == "ENG-4"), None)
    assert eng4 is not None
    assert eng4["severity"] == "HIGH"
    assert eng4["agent"] == "estimation"


def test_zero_story_points():
    from agents.estimation_agent import run

    # ENG-5: story_points=0.0 → MEDIUM
    findings = run(FIXTURES)
    eng5 = next(
        (f for f in findings if f["key"] == "ENG-5" and "0" in f["reason"]),
        None
    )
    assert eng5 is not None
    assert eng5["severity"] == "MEDIUM"


def test_time_overrun():
    from agents.estimation_agent import run

    # ENG-1: estimate=14400s, logged=28800s → 200% overrun → MEDIUM
    findings = run(FIXTURES)
    eng1 = next(
        (f for f in findings if f["key"] == "ENG-1" and "overrun" in f["reason"].lower()),
        None
    )
    assert eng1 is not None
    assert eng1["severity"] == "MEDIUM"


def test_subtask_exceeds_parent():
    from agents.estimation_agent import run

    # ENG-1 (5pts) has subtasks ENG-11 (8pts) + ENG-12 (5pts) = 13pts > 5pts → MEDIUM
    findings = run(FIXTURES)
    eng1_subtask = next(
        (f for f in findings if f["key"] == "ENG-1" and "subtask" in f["reason"].lower()),
        None
    )
    assert eng1_subtask is not None
    assert eng1_subtask["severity"] == "MEDIUM"


def test_clean_estimation():
    from agents.estimation_agent import run

    # ENG-6: has points, no overrun, no subtasks
    findings = run(FIXTURES)
    eng6 = [f for f in findings if f["key"] == "ENG-6"]
    assert len(eng6) == 0


def test_returns_correct_schema():
    from agents.estimation_agent import run

    findings = run(FIXTURES)
    for f in findings:
        assert {"agent", "key", "severity", "reason", "url"} <= set(f.keys())
        assert f["agent"] == "estimation"
