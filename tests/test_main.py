from unittest.mock import patch

import main


def _issue(key, labels):
    return {
        "key": key,
        "labels": labels,
        "status": "In Progress",
        "priority": "High",
        "assignee": "Someone",
        "story_points": 3,
        "days_since_update": 10,
        "days_since_last_comment": 10,
        "issuetype": "Story",
        "time_estimate": None,
        "time_logged": None,
        "blocker_count": 0,
        "is_blocked": False,
        "blocking_chain_keys": [],
        "has_escalation_link": False,
        "due_date": None,
        "parent_key": None,
        "subtask_keys": [],
        "comment_count": 0,
        "url": f"https://example.atlassian.net/browse/{key}",
    }


@patch("main.send_email_report")
@patch("main.compose", return_value="report")
@patch("main.commit_run", return_value=[])
@patch("main.blocker_agent")
@patch("main.priority_agent")
@patch("main.estimation_agent")
@patch("main.staleness_agent")
@patch("main.fetch_active_sprint_issues")
@patch("main.get_jira_client")
def test_ignore_label_excludes_issue_from_all_agents(
    mock_get_client,
    mock_fetch,
    mock_staleness,
    mock_estimation,
    mock_priority,
    mock_blocker,
    mock_commit_run,
    mock_compose,
    mock_send_email,
    monkeypatch,
):
    monkeypatch.setenv("JIRA_IGNORE_LABEL", "sanity-ignore")
    mock_fetch.return_value = [
        _issue("ENG-1", labels=[]),
        _issue("ENG-2", labels=["sanity-ignore"]),
    ]
    mock_staleness.run.return_value = []
    mock_estimation.run.return_value = []
    mock_priority.run.return_value = []
    mock_blocker.run.return_value = []

    main.run("ENG", "Sprint 42", dry_run=True)

    seen_keys = {i["key"] for i in mock_staleness.run.call_args[0][0]}
    assert seen_keys == {"ENG-1"}
    assert {i["key"] for i in mock_commit_run.call_args[0][0]} == {"ENG-1"}


@patch("main.send_email_report")
@patch("main.fetch_active_sprint_issues")
@patch("main.get_jira_client")
def test_agent_backend_agentcore_routes_through_agentcore_agents(
    mock_get_client, mock_fetch, mock_send_email, monkeypatch
):
    monkeypatch.setenv("AGENT_BACKEND", "agentcore")
    mock_fetch.return_value = [_issue("ENG-1", labels=[])]

    with patch("agentcore_agents.staleness_run", return_value=[]) as mock_staleness, \
         patch("agentcore_agents.estimation_run", return_value=[]), \
         patch("agentcore_agents.priority_run", return_value=[]), \
         patch("agentcore_agents.blocker_run", return_value=[]), \
         patch(
             "agentcore_agents.commit_run",
             return_value=[{"agent": "commit", "key": "ENG-1", "severity": "LOW", "reason": "x", "url": "u"}],
         ), \
         patch("agentcore_agents.report_composer_compose", return_value="agentcore report") as mock_compose:
        result = main.run("ENG", "Sprint 42", dry_run=True)

    assert result == [{"agent": "commit", "key": "ENG-1", "severity": "LOW", "reason": "x", "url": "u"}]
    mock_staleness.assert_called_once()
    mock_compose.assert_called_once_with(result, "Sprint 42")
