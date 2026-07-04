import json
from pathlib import Path

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sprint_issues.json").read_text()
)


def test_summarize_totals_and_points():
    from agents.sprint_summary_agent import summarize

    stats = summarize(FIXTURES)

    assert stats["total_issues"] == 12
    assert stats["committed_points"] == 53.0
    assert stats["completed_points"] == 8.0


def test_summarize_status_counts():
    from agents.sprint_summary_agent import summarize

    stats = summarize(FIXTURES)

    assert stats["status_counts"] == {
        "In Progress": 6,
        "To Do": 4,
        "In Review": 1,
        "Done": 1,
    }


def test_summarize_carryover_excludes_done_only():
    from agents.sprint_summary_agent import summarize

    stats = summarize(FIXTURES)

    assert "ENG-11" not in stats["carryover_keys"]
    assert len(stats["carryover_keys"]) == 11
    assert "ENG-1" in stats["carryover_keys"]


def test_summarize_blocked_issues():
    from agents.sprint_summary_agent import summarize

    stats = summarize(FIXTURES)

    blocked_keys = {b["key"] for b in stats["blocked_issues"]}
    assert blocked_keys == {"ENG-5", "ENG-9"}
    eng5 = next(b for b in stats["blocked_issues"] if b["key"] == "ENG-5")
    assert eng5["blocker_count"] == 1


def test_summarize_by_assignee():
    from agents.sprint_summary_agent import summarize

    stats = summarize(FIXTURES)

    assert stats["by_assignee"]["Alice Smith"] == {"total": 4, "done": 1}
    assert stats["by_assignee"]["Unassigned"] == {"total": 4, "done": 0}
