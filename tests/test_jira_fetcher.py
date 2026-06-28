import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest


FIXTURES_PATH = Path(__file__).parent / "fixtures" / "sprint_issues.json"


def load_fixture() -> list[dict]:
    return json.loads(FIXTURES_PATH.read_text())


def test_fixture_loads():
    issues = load_fixture()
    assert len(issues) == 12


def test_fixture_schema():
    required_keys = {
        "key", "summary", "status", "priority", "assignee",
        "story_points", "days_since_update", "days_since_last_comment",
        "labels", "issuetype", "time_estimate", "time_logged",
        "blocker_count", "is_blocked", "blocking_chain_keys",
        "has_escalation_link", "due_date", "parent_key",
        "subtask_keys", "comment_count", "url",
    }
    for issue in load_fixture():
        missing = required_keys - set(issue.keys())
        assert not missing, f"{issue['key']} missing keys: {missing}"


def test_normalize_stale_issue():
    from jira_fetcher import _normalize

    mock_issue = _make_mock_issue(
        key="TEST-1",
        status="In Progress",
        updated_days_ago=6,
        comment_total=1,
        last_comment_days_ago=6,
    )
    result = _normalize(mock_issue)

    assert result["key"] == "TEST-1"
    assert result["status"] == "In Progress"
    assert result["days_since_update"] >= 6
    assert result["is_blocked"] is False
    assert result["blocker_count"] == 0
    assert isinstance(result["labels"], list)
    assert isinstance(result["subtask_keys"], list)


def test_normalize_blocked_issue():
    from jira_fetcher import _normalize

    mock_issue = _make_mock_issue(
        key="TEST-2",
        status="In Progress",
        updated_days_ago=1,
        comment_total=0,
        last_comment_days_ago=999,
        blocker_keys=["TEST-99"],
    )
    result = _normalize(mock_issue)

    assert result["is_blocked"] is True
    assert "TEST-99" in result["blocking_chain_keys"]
    assert result["blocker_count"] == 1


def test_normalize_subtask():
    from jira_fetcher import _normalize

    mock_issue = _make_mock_issue(
        key="TEST-3",
        status="In Progress",
        updated_days_ago=0,
        comment_total=0,
        last_comment_days_ago=999,
        parent_key="TEST-1",
    )
    result = _normalize(mock_issue)
    assert result["parent_key"] == "TEST-1"


def test_normalize_no_comments():
    from jira_fetcher import _normalize

    mock_issue = _make_mock_issue(
        key="TEST-4",
        status="To Do",
        updated_days_ago=2,
        comment_total=0,
        last_comment_days_ago=999,
    )
    result = _normalize(mock_issue)
    assert result["days_since_last_comment"] == 999


def _make_mock_issue(
    key="TEST-1",
    status="In Progress",
    updated_days_ago=0,
    comment_total=0,
    last_comment_days_ago=999,
    blocker_keys=None,
    parent_key=None,
    subtask_keys=None,
):
    from datetime import datetime, timezone, timedelta

    issue = MagicMock()
    issue.key = key
    issue.fields.summary = f"Summary for {key}"
    issue.fields.status.name = status
    issue.fields.priority.name = "Medium"
    issue.fields.assignee = None
    issue.fields.customfield_10016 = 5.0  # story points

    now = datetime.now(timezone.utc)
    updated = now - timedelta(days=updated_days_ago)
    issue.fields.updated = updated.isoformat().replace("+00:00", "Z")

    issue.fields.labels = []
    issue.fields.issuetype.name = "Story"
    issue.fields.timeoriginalestimate = 3600
    issue.fields.timespent = 0
    issue.fields.duedate = None

    issue.fields.comment.total = comment_total
    if comment_total > 0:
        last_comment_dt = now - timedelta(days=last_comment_days_ago)
        comment = MagicMock()
        comment.created = last_comment_dt.isoformat().replace("+00:00", "Z")
        issue.fields.comment.comments = [comment]
    else:
        issue.fields.comment.comments = []

    # blockers
    issue.fields.issuelinks = []
    if blocker_keys:
        for bk in blocker_keys:
            link = MagicMock()
            link.type.name = "Blocks"
            link.inwardIssue = MagicMock()
            link.inwardIssue.key = bk
            issue.fields.issuelinks.append(link)

    # parent
    if parent_key:
        issue.fields.parent = MagicMock()
        issue.fields.parent.key = parent_key
    else:
        issue.fields.parent = None

    # subtasks
    issue.fields.subtasks = []
    if subtask_keys:
        for sk in subtask_keys:
            st = MagicMock()
            st.key = sk
            issue.fields.subtasks.append(st)

    os.environ.setdefault("JIRA_URL", "https://test.atlassian.net")
    return issue


def test_fetch_active_sprint_issues_paginates():
    from unittest.mock import patch, call
    from jira_fetcher import fetch_active_sprint_issues

    import os
    os.environ.setdefault("JIRA_URL", "https://test.atlassian.net")

    page1 = [_make_mock_issue(f"TEST-{i}", "To Do", 0, 0, 999) for i in range(50)]
    page2 = [_make_mock_issue(f"TEST-{i}", "To Do", 0, 0, 999) for i in range(50, 60)]

    mock_jira = MagicMock()
    mock_jira.search_issues.side_effect = [page1, page2]

    issues = fetch_active_sprint_issues(mock_jira, "ENG")

    assert len(issues) == 60
    assert mock_jira.search_issues.call_count == 2
    first_call = mock_jira.search_issues.call_args_list[0]
    assert first_call.kwargs.get("startAt", first_call.args[1] if len(first_call.args) > 1 else 0) == 0
    second_call = mock_jira.search_issues.call_args_list[1]
    assert second_call.kwargs.get("startAt", 0) == 50 or second_call.kwargs.get("maxResults") == 50


def test_fetch_active_sprint_issues_retry_on_error():
    from unittest.mock import patch
    from jira_fetcher import fetch_active_sprint_issues
    import os

    os.environ.setdefault("JIRA_URL", "https://test.atlassian.net")

    page = [_make_mock_issue("TEST-1", "To Do", 0, 0, 999)]
    mock_jira = MagicMock()
    mock_jira.search_issues.side_effect = [Exception("rate limit"), page]

    with patch("jira_fetcher.time.sleep"):
        issues = fetch_active_sprint_issues(mock_jira, "ENG")

    assert len(issues) == 1


def test_get_jira_client_uses_env_vars(monkeypatch):
    from unittest.mock import patch as mpatch
    from jira_fetcher import get_jira_client

    monkeypatch.setenv("JIRA_URL", "https://myco.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "user@myco.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "mytoken")

    with mpatch("jira_fetcher.JIRA") as mock_jira_cls:
        mock_jira_cls.return_value = MagicMock()
        client = get_jira_client()
        mock_jira_cls.assert_called_once_with(
            server="https://myco.atlassian.net",
            basic_auth=("user@myco.com", "mytoken"),
        )
