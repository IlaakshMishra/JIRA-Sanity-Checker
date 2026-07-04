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


@patch("main.send_ppt_email")
@patch("main.build_ppt")
@patch("main.ppt_narrative")
@patch("main.sprint_summary_agent")
@patch("main.fetch_active_sprint_issues")
@patch("main.get_jira_client")
def test_run_ppt_dry_run_skips_email(
    mock_get_client, mock_fetch, mock_summary, mock_narrative,
    mock_build_ppt, mock_send_ppt,
):
    mock_fetch.return_value = [_issue("ENG-1", labels=[])]
    mock_summary.summarize.return_value = {"stats": "x"}
    mock_narrative.generate.return_value = {"highlights": []}
    mock_build_ppt.return_value = b"PPTXBYTES"

    result = main.run_ppt("ENG", "Sprint 42", dry_run=True)

    assert result == b"PPTXBYTES"
    mock_send_ppt.assert_not_called()


@patch("main.send_ppt_email")
@patch("main.build_ppt")
@patch("main.ppt_narrative")
@patch("main.sprint_summary_agent")
@patch("main.fetch_active_sprint_issues")
@patch("main.get_jira_client")
def test_run_ppt_sends_email_when_not_dry_run(
    mock_get_client, mock_fetch, mock_summary, mock_narrative,
    mock_build_ppt, mock_send_ppt,
):
    mock_fetch.return_value = [_issue("ENG-1", labels=[])]
    mock_summary.summarize.return_value = {"stats": "x"}
    mock_narrative.generate.return_value = {"highlights": []}
    mock_build_ppt.return_value = b"PPTXBYTES"

    main.run_ppt("ENG", "Sprint 42", dry_run=False)

    mock_send_ppt.assert_called_once_with(b"PPTXBYTES", "Sprint 42")


@patch("main.send_ppt_email")
@patch("main.build_ppt")
@patch("main.ppt_narrative")
@patch("main.sprint_summary_agent")
@patch("main.fetch_active_sprint_issues")
@patch("main.get_jira_client")
def test_run_ppt_respects_ignore_label(
    mock_get_client, mock_fetch, mock_summary, mock_narrative,
    mock_build_ppt, mock_send_ppt, monkeypatch,
):
    monkeypatch.setenv("JIRA_IGNORE_LABEL", "sanity-ignore")
    mock_fetch.return_value = [
        _issue("ENG-1", labels=[]),
        _issue("ENG-2", labels=["sanity-ignore"]),
    ]
    mock_summary.summarize.return_value = {"stats": "x"}
    mock_narrative.generate.return_value = {"highlights": []}
    mock_build_ppt.return_value = b"PPTXBYTES"

    main.run_ppt("ENG", "Sprint 42", dry_run=True)

    seen_keys = {i["key"] for i in mock_summary.summarize.call_args[0][0]}
    assert seen_keys == {"ENG-1"}
