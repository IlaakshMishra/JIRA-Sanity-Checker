# Jira Sanity Checker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-agent sprint hygiene system that fetches Jira issues nightly, runs 5 specialized rule-based checks, composes an LLM-written PM report via AWS Bedrock, and posts it to Teams/Slack after human approval.

**Architecture:** Orchestrator (`main.py`) fetches the active sprint via Jira API, fans out to 5 pure-Python check agents (Staleness, Estimation, Priority, Commit, Blocker), collects structured `Finding` dicts, then calls a Bedrock-backed Report Composer (Agent 6) that writes Markdown prose around those facts. All writes to Jira are gated behind explicit human CLI confirmation.

**Tech Stack:** Python 3.12, `jira==3.8.0`, `boto3==1.35.0`, AWS Bedrock (claude-sonnet-4-5), `requests==2.32.0`, `python-dotenv==1.0.1`, `pytest==8.3.0`, AWS EventBridge + Lambda (deploy), Terraform (IaC), Docker Compose (local dev)

## Global Constraints

- Python 3.12 minimum
- `jira==3.8.0`, `boto3==1.35.0`, `requests==2.32.0`, `python-dotenv==1.0.1`, `pytest==8.3.0` — pin exact versions
- Bedrock model ID: `us.anthropic.claude-sonnet-4-5`
- All Jira writes gated behind `input()` confirmation — system is read-only by default
- story_points field configurable via `JIRA_STORY_POINTS_FIELD` env var, default `customfield_10016`
- Agents return `list[dict]` with keys: `agent`, `key`, `severity` (HIGH/MEDIUM/LOW), `reason`, `url`
- Run from project root: `PYTHONPATH=src python src/main.py`
- Tests run from project root: `pytest tests/`
- No external dependencies beyond `requirements.txt` — no LangChain, no frameworks

---

## File Map

| File | Responsibility |
|------|----------------|
| `src/jira_fetcher.py` | Jira API client, `fetch_active_sprint_issues()`, `_normalize()` |
| `src/agents/__init__.py` | Empty package marker |
| `src/agents/staleness_agent.py` | Agent 1: stale/unassigned-in-progress checks |
| `src/agents/estimation_agent.py` | Agent 2: missing/zero points, time overrun, subtask > parent |
| `src/agents/priority_agent.py` | Agent 3: unassigned P1, no due date on critical, label mismatch |
| `src/agents/commit_agent.py` | Agent 4: GitHub PR/branch correlation (optional, skips if no token) |
| `src/agents/blocker_agent.py` | Agent 5: long-blocked, deep chain, no escalation link |
| `src/agents/report_composer.py` | Agent 6: Bedrock call → Markdown report string |
| `src/notifier.py` | Teams/Slack webhook POST |
| `src/main.py` | Orchestrator: fetch → agents → compose → human gate → notify |
| `src/lambda_handler.py` | AWS Lambda entry point wrapping `main.run()` |
| `tests/fixtures/sprint_issues.json` | 12-issue mock fixture covering all agent edge cases |
| `tests/test_jira_fetcher.py` | Unit tests for `_normalize()`, fixture loading |
| `tests/test_staleness_agent.py` | Unit tests Agent 1 |
| `tests/test_estimation_agent.py` | Unit tests Agent 2 |
| `tests/test_priority_agent.py` | Unit tests Agent 3 |
| `tests/test_commit_agent.py` | Unit tests Agent 4 |
| `tests/test_blocker_agent.py` | Unit tests Agent 5 |
| `tests/test_report_composer.py` | Unit tests Agent 6 (mocked Bedrock) |
| `tests/test_notifier.py` | Unit tests notifier (mocked requests) |
| `tests/test_integration.py` | End-to-end with fixture data, no live APIs |
| `infra/main.tf` | EventBridge cron rule + Lambda function |
| `infra/variables.tf` | Terraform input variables |
| `infra/outputs.tf` | Terraform outputs (Lambda ARN, EventBridge rule) |
| `docker-compose.yml` | Local dev: runs `python src/main.py` with env loaded |
| `.env.example` | Template for required env vars |
| `requirements.txt` | Pinned dependencies |
| `README.md` | Quick-start, architecture diagram, env var reference |
| `LICENSE` | MIT |

---

### Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `src/__init__.py`
- Create: `src/agents/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/fixtures/` (directory)
- Create: `pytest.ini`

**Interfaces:**
- Produces: runnable Python env, `pytest` discovers `tests/`

- [ ] **Step 1: Create directory tree**

```bash
mkdir -p src/agents tests/fixtures infra
```

- [ ] **Step 2: Write `requirements.txt`**

```
jira==3.8.0
boto3==1.35.0
python-dotenv==1.0.1
requests==2.32.0
pytest==8.3.0
```

- [ ] **Step 3: Write `.env.example`**

```
JIRA_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=<from Atlassian API Tokens page>
JIRA_PROJECT_KEY=ENG
JIRA_STORY_POINTS_FIELD=customfield_10016
JIRA_STALENESS_THRESHOLD_DAYS=3
TEAMS_WEBHOOK_URL=<from Teams incoming webhook connector>
SLACK_WEBHOOK_URL=
GITHUB_TOKEN=
GITHUB_REPO=owner/repo
AWS_REGION=us-east-1
```

- [ ] **Step 4: Write `pytest.ini`**

```ini
[pytest]
testpaths = tests
pythonpath = src
```

- [ ] **Step 5: Create package markers**

Create empty files: `src/__init__.py`, `src/agents/__init__.py`, `tests/__init__.py`

- [ ] **Step 6: Create venv and install**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Expected: no errors, `pip show jira` shows `Version: 3.8.0`

- [ ] **Step 7: Verify pytest discovers tests**

```bash
pytest --collect-only
```

Expected: `no tests ran` (empty tests dir), no import errors

- [ ] **Step 8: Commit**

```bash
git init
git add requirements.txt .env.example pytest.ini src/__init__.py src/agents/__init__.py tests/__init__.py
git commit -m "chore: project scaffolding — deps, pytest, package structure"
```

---

### Task 2: Test Fixtures + Jira Fetcher

**Files:**
- Create: `tests/fixtures/sprint_issues.json`
- Create: `src/jira_fetcher.py`
- Create: `tests/test_jira_fetcher.py`

**Interfaces:**
- Produces:
  - `get_jira_client() -> JIRA`
  - `fetch_active_sprint_issues(jira: JIRA, project_key: str) -> list[dict]`
  - Normalized issue dict schema (all agents consume this)

**Normalized issue dict schema** (consumed by every downstream agent):
```python
{
    "key": str,                    # "ENG-123"
    "summary": str,
    "status": str,                 # "To Do" | "In Progress" | "In Review" | "Done"
    "priority": str | None,        # "Highest" | "High" | "Medium" | "Low" | "Lowest"
    "assignee": str | None,        # display name or None
    "story_points": float | None,  # None = unset
    "days_since_update": int,
    "days_since_last_comment": int,  # 999 if no comments
    "labels": list[str],
    "issuetype": str,              # "Story" | "Bug" | "Task" | "Sub-task"
    "time_estimate": int | None,   # seconds
    "time_logged": int | None,     # seconds
    "blocker_count": int,
    "is_blocked": bool,
    "blocking_chain_keys": list[str],  # keys of issues this one is blocked by
    "has_escalation_link": bool,
    "due_date": str | None,        # "2026-07-01" ISO format
    "parent_key": str | None,      # set for Sub-tasks
    "subtask_keys": list[str],     # keys of child sub-tasks
    "comment_count": int,
    "url": str,
}
```

- [ ] **Step 1: Write fixture file `tests/fixtures/sprint_issues.json`**

This JSON is the canonical test data. Every agent test imports this file.

```json
[
  {
    "key": "ENG-1",
    "summary": "Fix login timeout bug",
    "status": "In Progress",
    "priority": "High",
    "assignee": "Alice Smith",
    "story_points": 5.0,
    "days_since_update": 6,
    "days_since_last_comment": 6,
    "labels": [],
    "issuetype": "Bug",
    "time_estimate": 14400,
    "time_logged": 28800,
    "blocker_count": 0,
    "is_blocked": false,
    "blocking_chain_keys": [],
    "has_escalation_link": false,
    "due_date": "2026-07-10",
    "parent_key": null,
    "subtask_keys": ["ENG-11", "ENG-12"],
    "comment_count": 1,
    "url": "https://company.atlassian.net/browse/ENG-1"
  },
  {
    "key": "ENG-2",
    "summary": "Add SSO integration",
    "status": "In Progress",
    "priority": "Medium",
    "assignee": null,
    "story_points": 8.0,
    "days_since_update": 1,
    "days_since_last_comment": 1,
    "labels": [],
    "issuetype": "Story",
    "time_estimate": 28800,
    "time_logged": 3600,
    "blocker_count": 0,
    "is_blocked": false,
    "blocking_chain_keys": [],
    "has_escalation_link": false,
    "due_date": null,
    "parent_key": null,
    "subtask_keys": [],
    "comment_count": 2,
    "url": "https://company.atlassian.net/browse/ENG-2"
  },
  {
    "key": "ENG-3",
    "summary": "Deploy to prod",
    "status": "To Do",
    "priority": "Highest",
    "assignee": null,
    "story_points": 3.0,
    "days_since_update": 0,
    "days_since_last_comment": 999,
    "labels": ["critical"],
    "issuetype": "Task",
    "time_estimate": null,
    "time_logged": null,
    "blocker_count": 0,
    "is_blocked": false,
    "blocking_chain_keys": [],
    "has_escalation_link": false,
    "due_date": null,
    "parent_key": null,
    "subtask_keys": [],
    "comment_count": 0,
    "url": "https://company.atlassian.net/browse/ENG-3"
  },
  {
    "key": "ENG-4",
    "summary": "Write API docs",
    "status": "In Progress",
    "priority": "Low",
    "assignee": "Bob Jones",
    "story_points": null,
    "days_since_update": 2,
    "days_since_last_comment": 2,
    "labels": [],
    "issuetype": "Task",
    "time_estimate": 7200,
    "time_logged": 7200,
    "blocker_count": 0,
    "is_blocked": false,
    "blocking_chain_keys": [],
    "has_escalation_link": false,
    "due_date": null,
    "parent_key": null,
    "subtask_keys": [],
    "comment_count": 3,
    "url": "https://company.atlassian.net/browse/ENG-4"
  },
  {
    "key": "ENG-5",
    "summary": "Database migration for v2",
    "status": "In Progress",
    "priority": "High",
    "assignee": "Carol White",
    "story_points": 0.0,
    "days_since_update": 1,
    "days_since_last_comment": 1,
    "labels": [],
    "issuetype": "Story",
    "time_estimate": 0,
    "time_logged": 3600,
    "blocker_count": 1,
    "is_blocked": true,
    "blocking_chain_keys": ["ENG-9"],
    "has_escalation_link": false,
    "due_date": "2026-07-05",
    "parent_key": null,
    "subtask_keys": [],
    "comment_count": 1,
    "url": "https://company.atlassian.net/browse/ENG-5"
  },
  {
    "key": "ENG-6",
    "summary": "Performance testing",
    "status": "To Do",
    "priority": "Medium",
    "assignee": "Dave Brown",
    "story_points": 5.0,
    "days_since_update": 0,
    "days_since_last_comment": 999,
    "labels": ["priority-high"],
    "issuetype": "Task",
    "time_estimate": 14400,
    "time_logged": null,
    "blocker_count": 0,
    "is_blocked": false,
    "blocking_chain_keys": [],
    "has_escalation_link": false,
    "due_date": "2026-07-15",
    "parent_key": null,
    "subtask_keys": [],
    "comment_count": 0,
    "url": "https://company.atlassian.net/browse/ENG-6"
  },
  {
    "key": "ENG-7",
    "summary": "Setup CI pipeline",
    "status": "In Review",
    "priority": "Medium",
    "assignee": "Alice Smith",
    "story_points": 3.0,
    "days_since_update": 4,
    "days_since_last_comment": 4,
    "labels": [],
    "issuetype": "Task",
    "time_estimate": 7200,
    "time_logged": 7200,
    "blocker_count": 0,
    "is_blocked": false,
    "blocking_chain_keys": [],
    "has_escalation_link": false,
    "due_date": null,
    "parent_key": null,
    "subtask_keys": [],
    "comment_count": 5,
    "url": "https://company.atlassian.net/browse/ENG-7"
  },
  {
    "key": "ENG-8",
    "summary": "Security audit findings",
    "status": "To Do",
    "priority": "Highest",
    "assignee": null,
    "story_points": 13.0,
    "days_since_update": 0,
    "days_since_last_comment": 999,
    "labels": ["escalated"],
    "issuetype": "Bug",
    "time_estimate": null,
    "time_logged": null,
    "blocker_count": 0,
    "is_blocked": false,
    "blocking_chain_keys": [],
    "has_escalation_link": false,
    "due_date": null,
    "parent_key": null,
    "subtask_keys": [],
    "comment_count": 0,
    "url": "https://company.atlassian.net/browse/ENG-8"
  },
  {
    "key": "ENG-9",
    "summary": "Unblock DB migration — waiting on DBA",
    "status": "In Progress",
    "priority": "High",
    "assignee": "Eve Davis",
    "story_points": 2.0,
    "days_since_update": 4,
    "days_since_last_comment": 4,
    "labels": [],
    "issuetype": "Task",
    "time_estimate": 3600,
    "time_logged": 0,
    "blocker_count": 1,
    "is_blocked": true,
    "blocking_chain_keys": ["ENG-10"],
    "has_escalation_link": false,
    "due_date": null,
    "parent_key": null,
    "subtask_keys": [],
    "comment_count": 1,
    "url": "https://company.atlassian.net/browse/ENG-9"
  },
  {
    "key": "ENG-10",
    "summary": "DBA approval for schema change",
    "status": "To Do",
    "priority": "Low",
    "assignee": null,
    "story_points": 1.0,
    "days_since_update": 5,
    "days_since_last_comment": 5,
    "labels": [],
    "issuetype": "Task",
    "time_estimate": null,
    "time_logged": null,
    "blocker_count": 0,
    "is_blocked": false,
    "blocking_chain_keys": [],
    "has_escalation_link": false,
    "due_date": null,
    "parent_key": null,
    "subtask_keys": [],
    "comment_count": 0,
    "url": "https://company.atlassian.net/browse/ENG-10"
  },
  {
    "key": "ENG-11",
    "summary": "Fix login timeout — frontend",
    "status": "Done",
    "priority": "High",
    "assignee": "Alice Smith",
    "story_points": 8.0,
    "days_since_update": 0,
    "days_since_last_comment": 0,
    "labels": [],
    "issuetype": "Sub-task",
    "time_estimate": 3600,
    "time_logged": 3600,
    "blocker_count": 0,
    "is_blocked": false,
    "blocking_chain_keys": [],
    "has_escalation_link": false,
    "due_date": null,
    "parent_key": "ENG-1",
    "subtask_keys": [],
    "comment_count": 2,
    "url": "https://company.atlassian.net/browse/ENG-11"
  },
  {
    "key": "ENG-12",
    "summary": "Fix login timeout — backend",
    "status": "In Progress",
    "priority": "High",
    "assignee": "Alice Smith",
    "story_points": 5.0,
    "days_since_update": 1,
    "days_since_last_comment": 1,
    "labels": [],
    "issuetype": "Sub-task",
    "time_estimate": 3600,
    "time_logged": 3600,
    "blocker_count": 0,
    "is_blocked": false,
    "blocking_chain_keys": [],
    "has_escalation_link": false,
    "due_date": null,
    "parent_key": "ENG-1",
    "subtask_keys": [],
    "comment_count": 1,
    "url": "https://company.atlassian.net/browse/ENG-12"
  }
]
```

- [ ] **Step 2: Write failing tests `tests/test_jira_fetcher.py`**

```python
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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
```

- [ ] **Step 3: Run tests — expect failures**

```bash
pytest tests/test_jira_fetcher.py -v
```

Expected: `ImportError: No module named 'jira_fetcher'` (file not created yet)

- [ ] **Step 4: Write `src/jira_fetcher.py`**

```python
import os
from datetime import datetime, timezone
from jira import JIRA


def get_jira_client() -> JIRA:
    return JIRA(
        server=os.environ["JIRA_URL"],
        basic_auth=(os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"]),
    )


def fetch_active_sprint_issues(jira: JIRA, project_key: str) -> list[dict]:
    field = os.environ.get("JIRA_STORY_POINTS_FIELD", "customfield_10016")
    jql = (
        f"project = {project_key} "
        "AND sprint in openSprints() "
        "ORDER BY updated ASC"
    )
    issues = jira.search_issues(
        jql,
        maxResults=200,
        expand="changelog",
        fields=f"summary,status,priority,assignee,{field},labels,"
               "issuetype,timeoriginalestimate,timespent,issuelinks,"
               "comment,duedate,parent,subtasks",
    )
    return [_normalize(issue) for issue in issues]


def _normalize(issue) -> dict:
    now = datetime.now(timezone.utc)
    field = os.environ.get("JIRA_STORY_POINTS_FIELD", "customfield_10016")

    updated = datetime.fromisoformat(
        issue.fields.updated.replace("Z", "+00:00")
    )
    days_since_update = (now - updated).days

    comments = getattr(issue.fields.comment, "comments", [])
    if comments:
        last = datetime.fromisoformat(
            comments[-1].created.replace("Z", "+00:00")
        )
        days_since_last_comment = (now - last).days
    else:
        days_since_last_comment = 999

    blocker_links = [
        link for link in issue.fields.issuelinks
        if getattr(link, "type", None)
        and link.type.name.lower() == "blocks"
        and hasattr(link, "inwardIssue")
    ]
    blocking_chain_keys = [link.inwardIssue.key for link in blocker_links]

    escalation_links = [
        link for link in issue.fields.issuelinks
        if getattr(link, "type", None)
        and "escalat" in link.type.name.lower()
    ]

    parent_key = None
    if getattr(issue.fields, "parent", None):
        parent_key = issue.fields.parent.key

    subtask_keys = [
        st.key for st in getattr(issue.fields, "subtasks", [])
    ]

    return {
        "key": issue.key,
        "summary": issue.fields.summary,
        "status": issue.fields.status.name,
        "priority": getattr(issue.fields.priority, "name", None),
        "assignee": getattr(issue.fields.assignee, "displayName", None),
        "story_points": getattr(issue.fields, field, None),
        "days_since_update": days_since_update,
        "days_since_last_comment": days_since_last_comment,
        "labels": list(issue.fields.labels),
        "issuetype": issue.fields.issuetype.name,
        "time_estimate": issue.fields.timeoriginalestimate,
        "time_logged": issue.fields.timespent,
        "blocker_count": len(blocker_links),
        "is_blocked": len(blocker_links) > 0,
        "blocking_chain_keys": blocking_chain_keys,
        "has_escalation_link": len(escalation_links) > 0,
        "due_date": getattr(issue.fields, "duedate", None),
        "parent_key": parent_key,
        "subtask_keys": subtask_keys,
        "comment_count": issue.fields.comment.total,
        "url": f"{os.environ['JIRA_URL']}/browse/{issue.key}",
    }
```

- [ ] **Step 5: Run tests — expect pass**

```bash
pytest tests/test_jira_fetcher.py -v
```

Expected: `6 passed`

- [ ] **Step 6: Commit**

```bash
git add src/jira_fetcher.py tests/test_jira_fetcher.py tests/fixtures/sprint_issues.json pytest.ini requirements.txt .env.example src/__init__.py src/agents/__init__.py tests/__init__.py
git commit -m "feat: Jira fetcher with normalize + fixture data"
```

---

### Task 3: Staleness Agent (Agent 1)

**Files:**
- Create: `src/agents/staleness_agent.py`
- Create: `tests/test_staleness_agent.py`

**Interfaces:**
- Consumes: `list[dict]` normalized issues (schema from Task 2)
- Produces: `run(issues: list[dict]) -> list[dict]` — findings with `agent="staleness"`

Checks:
1. `status in ("In Progress", "In Review") AND days_since_update >= THRESHOLD` → severity HIGH if > 5 days, else MEDIUM
2. `status == "In Progress" AND assignee is None` → HIGH
3. `days_since_last_comment >= 5 AND status in ("In Progress", "In Review")` → MEDIUM

Threshold configurable via `JIRA_STALENESS_THRESHOLD_DAYS` env var, default 3.

- [ ] **Step 1: Write failing test `tests/test_staleness_agent.py`**

```python
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
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/test_staleness_agent.py -v
```

Expected: `ImportError: cannot import name 'run' from 'agents.staleness_agent'`

- [ ] **Step 3: Write `src/agents/staleness_agent.py`**

```python
import os

STALENESS_THRESHOLD = int(os.environ.get("JIRA_STALENESS_THRESHOLD_DAYS", "3"))
ACTIVE_STATUSES = ("In Progress", "In Review")


def run(issues: list[dict]) -> list[dict]:
    findings = []
    for issue in issues:
        if issue["status"] not in ACTIVE_STATUSES:
            continue

        if issue["days_since_update"] >= STALENESS_THRESHOLD:
            severity = "HIGH" if issue["days_since_update"] > 5 else "MEDIUM"
            findings.append({
                "agent": "staleness",
                "key": issue["key"],
                "severity": severity,
                "reason": f"No update in {issue['days_since_update']}d (threshold: {STALENESS_THRESHOLD}d)",
                "url": issue["url"],
            })

        if issue["status"] == "In Progress" and not issue["assignee"]:
            findings.append({
                "agent": "staleness",
                "key": issue["key"],
                "severity": "HIGH",
                "reason": "In Progress with no assignee",
                "url": issue["url"],
            })

        if issue["days_since_last_comment"] >= 5:
            findings.append({
                "agent": "staleness",
                "key": issue["key"],
                "severity": "MEDIUM",
                "reason": f"No comment in {issue['days_since_last_comment']}d",
                "url": issue["url"],
            })

    return findings
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_staleness_agent.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/agents/staleness_agent.py tests/test_staleness_agent.py
git commit -m "feat: staleness agent — stale/unassigned/no-comment checks"
```

---

### Task 4: Estimation Auditor (Agent 2)

**Files:**
- Create: `src/agents/estimation_agent.py`
- Create: `tests/test_estimation_agent.py`

**Interfaces:**
- Consumes: `list[dict]` normalized issues
- Produces: `run(issues: list[dict]) -> list[dict]` — findings with `agent="estimation"`

Checks:
1. `story_points is None` → HIGH (missing estimate)
2. `story_points == 0` → MEDIUM (0-point in sprint)
3. `time_logged > time_estimate * 1.5` (both non-None, non-zero) → MEDIUM (overrun > 50%)
4. Sum of subtask story_points > parent story_points → MEDIUM

For check 4: build an `issue_map` keyed by `key`, then for each issue with `subtask_keys`, sum subtask points from `issue_map`.

- [ ] **Step 1: Write failing test `tests/test_estimation_agent.py`**

```python
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
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/test_estimation_agent.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Write `src/agents/estimation_agent.py`**

```python
def run(issues: list[dict]) -> list[dict]:
    issue_map = {i["key"]: i for i in issues}
    findings = []

    for issue in issues:
        pts = issue["story_points"]

        if pts is None:
            findings.append({
                "agent": "estimation",
                "key": issue["key"],
                "severity": "HIGH",
                "reason": "Missing story points estimate",
                "url": issue["url"],
            })
            continue

        if pts == 0:
            findings.append({
                "agent": "estimation",
                "key": issue["key"],
                "severity": "MEDIUM",
                "reason": "0-point issue in sprint",
                "url": issue["url"],
            })

        est = issue["time_estimate"]
        logged = issue["time_logged"]
        if est and est > 0 and logged and logged > est * 1.5:
            pct = int((logged / est) * 100)
            findings.append({
                "agent": "estimation",
                "key": issue["key"],
                "severity": "MEDIUM",
                "reason": f"Time overrun: logged {pct}% of estimate",
                "url": issue["url"],
            })

        if issue["subtask_keys"] and pts is not None:
            subtask_total = sum(
                issue_map[sk]["story_points"] or 0
                for sk in issue["subtask_keys"]
                if sk in issue_map
            )
            if subtask_total > pts:
                findings.append({
                    "agent": "estimation",
                    "key": issue["key"],
                    "severity": "MEDIUM",
                    "reason": (
                        f"Subtask total ({subtask_total}pts) exceeds "
                        f"parent ({pts}pts)"
                    ),
                    "url": issue["url"],
                })

    return findings
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_estimation_agent.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/agents/estimation_agent.py tests/test_estimation_agent.py
git commit -m "feat: estimation agent — missing points, overrun, subtask checks"
```

---

### Task 5: Priority Drift Checker (Agent 3)

**Files:**
- Create: `src/agents/priority_agent.py`
- Create: `tests/test_priority_agent.py`

**Interfaces:**
- Consumes: `list[dict]` normalized issues
- Produces: `run(issues: list[dict]) -> list[dict]` — findings with `agent="priority"`

Checks:
1. `priority in ("Highest", "High") AND assignee is None` → HIGH
2. `priority == "Highest" AND due_date is None` → HIGH
3. Label says "critical" or "priority-high" but `priority in ("Low", "Lowest", "Medium")` → MEDIUM (label/priority mismatch)
4. `labels contains "escalated" AND has_escalation_link is False` → HIGH (orphaned escalation)

- [ ] **Step 1: Write failing test `tests/test_priority_agent.py`**

```python
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
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/test_priority_agent.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Write `src/agents/priority_agent.py`**

```python
HIGH_PRIORITIES = ("Highest", "High")
URGENT_PRIORITIES = ("Highest",)
CRITICAL_LABELS = {"critical", "priority-high", "priority-critical"}
LOW_PRIORITIES = ("Low", "Lowest", "Medium")


def run(issues: list[dict]) -> list[dict]:
    findings = []

    for issue in issues:
        priority = issue.get("priority") or ""
        labels = {label.lower() for label in issue.get("labels", [])}

        if priority in HIGH_PRIORITIES and not issue["assignee"]:
            findings.append({
                "agent": "priority",
                "key": issue["key"],
                "severity": "HIGH",
                "reason": f"{priority} priority with no assignee",
                "url": issue["url"],
            })

        if priority in URGENT_PRIORITIES and not issue["due_date"]:
            findings.append({
                "agent": "priority",
                "key": issue["key"],
                "severity": "HIGH",
                "reason": f"{priority} priority with no due date",
                "url": issue["url"],
            })

        label_says_critical = bool(labels & CRITICAL_LABELS)
        if label_says_critical and priority in LOW_PRIORITIES:
            matched = labels & CRITICAL_LABELS
            findings.append({
                "agent": "priority",
                "key": issue["key"],
                "severity": "MEDIUM",
                "reason": (
                    f"Label mismatch: label '{next(iter(matched))}' "
                    f"but priority is '{priority}'"
                ),
                "url": issue["url"],
            })

        if "escalated" in labels and not issue["has_escalation_link"]:
            findings.append({
                "agent": "priority",
                "key": issue["key"],
                "severity": "HIGH",
                "reason": "Orphaned escalation: 'escalated' label but no escalation ticket linked",
                "url": issue["url"],
            })

    return findings
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_priority_agent.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/agents/priority_agent.py tests/test_priority_agent.py
git commit -m "feat: priority agent — unassigned P1, no due date, label mismatch, orphaned escalation"
```

---

### Task 6: Commit Correlator (Agent 4)

**Files:**
- Create: `src/agents/commit_agent.py`
- Create: `tests/test_commit_agent.py`

**Interfaces:**
- Consumes: `list[dict]` normalized issues, GitHub REST API
- Produces: `run(issues: list[dict]) -> list[dict]` — findings with `agent="commit"`
- Skips silently if `GITHUB_TOKEN` env var not set

Checks (via GitHub API):
1. Issue `status == "Done"` but no PR/branch referencing `issue["key"]` → MEDIUM
2. PR merged (state=closed, merged=true) but issue still `status not in ("Done", "Closed")` → HIGH
3. Open issue with recent commits on a branch named after it → LOW (informational, suggest close)

GitHub API: `GET /repos/{owner}/{repo}/pulls?state=all&per_page=100` + `GET /repos/{owner}/{repo}/git/refs/heads`

- [ ] **Step 1: Write failing test `tests/test_commit_agent.py`**

```python
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
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/test_commit_agent.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Write `src/agents/commit_agent.py`**

```python
import os
import requests


def run(issues: list[dict]) -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO")
    if not token or not repo:
        return []

    prs = _fetch_prs(token, repo)
    branches = _fetch_branches(token, repo)
    return _correlate(issues, prs, branches)


def _fetch_prs(token: str, repo: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    resp = requests.get(
        f"https://api.github.com/repos/{repo}/pulls",
        params={"state": "all", "per_page": 100},
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_branches(token: str, repo: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    resp = requests.get(
        f"https://api.github.com/repos/{repo}/git/refs/heads",
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _pr_mentions(pr: dict, issue_key: str) -> bool:
    key_lower = issue_key.lower()
    return (
        key_lower in (pr.get("title") or "").lower()
        or key_lower in (pr.get("body") or "").lower()
        or key_lower in (pr.get("head", {}).get("ref") or "").lower()
    )


def _branch_mentions(branch: dict, issue_key: str) -> bool:
    ref = branch.get("ref", "")
    return issue_key.lower() in ref.lower()


def _correlate(issues: list[dict], prs: list[dict], branches: list[dict]) -> list[dict]:
    findings = []
    done_statuses = {"Done", "Closed", "Resolved"}

    for issue in issues:
        key = issue["key"]
        matching_prs = [pr for pr in prs if _pr_mentions(pr, key)]
        matching_branches = [b for b in branches if _branch_mentions(b, key)]

        if issue["status"] in done_statuses and not matching_prs and not matching_branches:
            findings.append({
                "agent": "commit",
                "key": key,
                "severity": "MEDIUM",
                "reason": "Ticket closed but no PR or branch found referencing it",
                "url": issue["url"],
            })

        for pr in matching_prs:
            if pr.get("merged_at") and issue["status"] not in done_statuses:
                findings.append({
                    "agent": "commit",
                    "key": key,
                    "severity": "HIGH",
                    "reason": f"PR merged ({pr['head']['ref']}) but ticket still '{issue['status']}'",
                    "url": issue["url"],
                })
                break

    return findings
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_commit_agent.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/agents/commit_agent.py tests/test_commit_agent.py
git commit -m "feat: commit correlator agent — PR/branch vs ticket status checks"
```

---

### Task 7: Blocker Analyst (Agent 5)

**Files:**
- Create: `src/agents/blocker_agent.py`
- Create: `tests/test_blocker_agent.py`

**Interfaces:**
- Consumes: `list[dict]` normalized issues
- Produces: `run(issues: list[dict]) -> list[dict]` — findings with `agent="blocker"`

Checks:
1. `is_blocked AND days_since_last_comment >= 3` → HIGH
2. Blocking chain depth > 2: `issue A blocks issue B, B is blocked by C` — walk `blocking_chain_keys` transitively to measure chain depth → HIGH
3. `is_blocked AND NOT has_escalation_link` → MEDIUM (blocked with no escalation)
4. (OOO check skipped — no HR integration available)

For chain depth: build adjacency map `{key: blocking_chain_keys}`, then BFS from each blocked issue to find max depth.

- [ ] **Step 1: Write failing test `tests/test_blocker_agent.py`**

```python
import json
from pathlib import Path

import pytest

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sprint_issues.json").read_text()
)


def test_blocked_no_comment():
    from agents.blocker_agent import run

    # ENG-9: is_blocked=True, days_since_last_comment=4 → HIGH
    findings = run(FIXTURES)
    eng9 = next(
        (f for f in findings if f["key"] == "ENG-9" and "comment" in f["reason"].lower()),
        None
    )
    assert eng9 is not None
    assert eng9["severity"] == "HIGH"


def test_blocking_chain_depth():
    from agents.blocker_agent import run

    # ENG-5 blocked by ENG-9, ENG-9 blocked by ENG-10 → chain depth = 3 → HIGH
    findings = run(FIXTURES)
    chain_flags = [f for f in findings if "chain" in f["reason"].lower() or "depth" in f["reason"].lower()]
    assert len(chain_flags) > 0
    assert any(f["severity"] == "HIGH" for f in chain_flags)


def test_blocked_no_escalation():
    from agents.blocker_agent import run

    # ENG-5: is_blocked=True, has_escalation_link=False → MEDIUM
    findings = run(FIXTURES)
    eng5 = next(
        (f for f in findings if f["key"] == "ENG-5" and "escalat" in f["reason"].lower()),
        None
    )
    assert eng5 is not None
    assert eng5["severity"] == "MEDIUM"


def test_not_blocked_not_flagged():
    from agents.blocker_agent import run

    # ENG-1: is_blocked=False → no blocker findings
    findings = run(FIXTURES)
    eng1_blocker = [
        f for f in findings if f["key"] == "ENG-1" and f["agent"] == "blocker"
    ]
    assert len(eng1_blocker) == 0


def test_schema():
    from agents.blocker_agent import run

    findings = run(FIXTURES)
    for f in findings:
        assert {"agent", "key", "severity", "reason", "url"} <= set(f.keys())
        assert f["agent"] == "blocker"
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/test_blocker_agent.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Write `src/agents/blocker_agent.py`**

```python
COMMENT_STALE_DAYS = 3
MAX_CHAIN_DEPTH = 2


def run(issues: list[dict]) -> list[dict]:
    issue_map = {i["key"]: i for i in issues}
    findings = []

    for issue in issues:
        if not issue["is_blocked"]:
            continue

        if issue["days_since_last_comment"] >= COMMENT_STALE_DAYS:
            findings.append({
                "agent": "blocker",
                "key": issue["key"],
                "severity": "HIGH",
                "reason": (
                    f"Blocked for {issue['days_since_last_comment']}d "
                    f"with no comment update"
                ),
                "url": issue["url"],
            })

        if not issue["has_escalation_link"]:
            findings.append({
                "agent": "blocker",
                "key": issue["key"],
                "severity": "MEDIUM",
                "reason": "Blocked with no escalation ticket linked",
                "url": issue["url"],
            })

    chain_violations = _find_deep_chains(issues, issue_map)
    findings.extend(chain_violations)

    return findings


def _chain_depth(start_key: str, issue_map: dict, visited: set | None = None) -> int:
    if visited is None:
        visited = set()
    if start_key in visited or start_key not in issue_map:
        return 0
    visited.add(start_key)
    issue = issue_map[start_key]
    if not issue["blocking_chain_keys"]:
        return 1
    return 1 + max(
        _chain_depth(k, issue_map, visited)
        for k in issue["blocking_chain_keys"]
    )


def _find_deep_chains(issues: list[dict], issue_map: dict) -> list[dict]:
    reported = set()
    findings = []
    for issue in issues:
        if not issue["is_blocked"]:
            continue
        depth = _chain_depth(issue["key"], issue_map)
        if depth > MAX_CHAIN_DEPTH and issue["key"] not in reported:
            reported.add(issue["key"])
            findings.append({
                "agent": "blocker",
                "key": issue["key"],
                "severity": "HIGH",
                "reason": f"Blocking chain depth {depth} (max: {MAX_CHAIN_DEPTH})",
                "url": issue["url"],
            })
    return findings
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_blocker_agent.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/agents/blocker_agent.py tests/test_blocker_agent.py
git commit -m "feat: blocker agent — stale blockers, deep chains, no escalation"
```

---

### Task 8: Report Composer + Notifier

**Files:**
- Create: `src/agents/report_composer.py`
- Create: `src/notifier.py`
- Create: `tests/test_report_composer.py`
- Create: `tests/test_notifier.py`

**Interfaces:**
- Consumes: `all_findings: list[dict]`, `sprint_name: str`
- Produces: `compose(all_findings, sprint_name) -> str` — Markdown string
- Produces: `post_to_teams(report: str) -> None` — posts to Teams webhook
- Produces: `post_to_slack(report: str) -> None` — posts to Slack webhook (if URL set)

Bedrock model: `us.anthropic.claude-sonnet-4-5`  
Bedrock region: `AWS_REGION` env var, default `us-east-1`

- [ ] **Step 1: Write failing tests `tests/test_report_composer.py`**

```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

SAMPLE_FINDINGS = [
    {"agent": "staleness", "key": "ENG-1", "severity": "HIGH",
     "reason": "No update in 6d", "url": "https://co.atlassian.net/browse/ENG-1"},
    {"agent": "estimation", "key": "ENG-4", "severity": "HIGH",
     "reason": "Missing story points", "url": "https://co.atlassian.net/browse/ENG-4"},
    {"agent": "blocker", "key": "ENG-5", "severity": "MEDIUM",
     "reason": "Blocked with no escalation ticket linked",
     "url": "https://co.atlassian.net/browse/ENG-5"},
]


def _mock_bedrock_response(text: str):
    mock_client = MagicMock()
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps({
        "content": [{"text": text}]
    }).encode()
    mock_client.invoke_model.return_value = {"body": mock_body}
    return mock_client


def test_compose_returns_string():
    from agents.report_composer import compose

    with patch("agents.report_composer.boto3") as mock_boto3:
        mock_boto3.client.return_value = _mock_bedrock_response(
            "# Sprint Health\n\n**ENG-1**: Stale ticket, update required."
        )
        result = compose(SAMPLE_FINDINGS, "Sprint 42")
        assert isinstance(result, str)
        assert len(result) > 0


def test_compose_calls_bedrock_once():
    from agents.report_composer import compose

    with patch("agents.report_composer.boto3") as mock_boto3:
        mock_client = _mock_bedrock_response("Report text")
        mock_boto3.client.return_value = mock_client
        compose(SAMPLE_FINDINGS, "Sprint 42")
        assert mock_client.invoke_model.call_count == 1


def test_compose_passes_findings_in_prompt():
    from agents.report_composer import compose

    with patch("agents.report_composer.boto3") as mock_boto3:
        mock_client = _mock_bedrock_response("Report")
        mock_boto3.client.return_value = mock_client
        compose(SAMPLE_FINDINGS, "Sprint 99")

        call_args = mock_client.invoke_model.call_args
        body = json.loads(call_args.kwargs.get("body") or call_args.args[0] if call_args.args else call_args.kwargs["body"])
        user_content = body["messages"][0]["content"]
        assert "Sprint 99" in user_content
        assert "ENG-1" in user_content


def test_compose_empty_findings_returns_clean_message():
    from agents.report_composer import compose

    with patch("agents.report_composer.boto3") as mock_boto3:
        mock_boto3.client.return_value = _mock_bedrock_response("Sprint looks clean.")
        result = compose([], "Sprint 42")
        assert isinstance(result, str)
```

- [ ] **Step 2: Write failing tests `tests/test_notifier.py`**

```python
import os
from unittest.mock import patch, MagicMock

import pytest


def test_post_to_teams_sends_request(monkeypatch):
    from notifier import post_to_teams

    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://teams.example.com/webhook")
    with patch("notifier.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()
        post_to_teams("# Sprint Health Report")
        assert mock_post.called
        call_json = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert "Sprint Health Report" in str(call_json)


def test_post_to_teams_skips_when_no_url(monkeypatch):
    from notifier import post_to_teams

    monkeypatch.delenv("TEAMS_WEBHOOK_URL", raising=False)
    with patch("notifier.requests.post") as mock_post:
        post_to_teams("# Report")
        assert not mock_post.called


def test_post_to_slack_sends_request(monkeypatch):
    from notifier import post_to_slack

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/xxx")
    with patch("notifier.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()
        post_to_slack("# Report")
        assert mock_post.called


def test_post_to_slack_skips_when_no_url(monkeypatch):
    from notifier import post_to_slack

    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    with patch("notifier.requests.post") as mock_post:
        post_to_slack("# Report")
        assert not mock_post.called
```

- [ ] **Step 3: Run tests — expect failures**

```bash
pytest tests/test_report_composer.py tests/test_notifier.py -v
```

Expected: `ImportError`

- [ ] **Step 4: Write `src/agents/report_composer.py`**

```python
import json
import os
import boto3

MODEL_ID = "us.anthropic.claude-sonnet-4-5"

SYSTEM = """You are a senior engineering project manager.
You receive structured findings from sprint health agents.
Write a concise, actionable sprint health report in Markdown.
Group findings by severity (HIGH → MEDIUM → LOW).
For each issue, write one bullet with: ticket key, reason, and
a specific suggested action. Max 400 words. No fluff."""


def compose(all_findings: list[dict], sprint_name: str) -> str:
    region = os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("bedrock-runtime", region_name=region)

    payload = {
        "model": MODEL_ID,
        "max_tokens": 1000,
        "system": SYSTEM,
        "messages": [{
            "role": "user",
            "content": (
                f"Sprint: {sprint_name}\n\n"
                f"Findings JSON:\n{json.dumps(all_findings, indent=2)}"
            ),
        }],
    }
    resp = client.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps(payload),
        contentType="application/json",
        accept="application/json",
    )
    body = json.loads(resp["body"].read())
    return body["content"][0]["text"]
```

- [ ] **Step 5: Write `src/notifier.py`**

```python
import os
import requests


def post_to_teams(report: str) -> None:
    url = os.environ.get("TEAMS_WEBHOOK_URL")
    if not url:
        return
    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": "Sprint Health Report",
        "text": report,
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()


def post_to_slack(report: str) -> None:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return
    resp = requests.post(url, json={"text": report}, timeout=15)
    resp.raise_for_status()
```

- [ ] **Step 6: Run tests — expect pass**

```bash
pytest tests/test_report_composer.py tests/test_notifier.py -v
```

Expected: `8 passed`

- [ ] **Step 7: Commit**

```bash
git add src/agents/report_composer.py src/notifier.py tests/test_report_composer.py tests/test_notifier.py
git commit -m "feat: report composer (Bedrock) + Teams/Slack notifier"
```

---

### Task 9: Main Orchestrator + Integration Test

**Files:**
- Create: `src/main.py`
- Create: `tests/test_integration.py`

**Interfaces:**
- Consumes: all agents, `jira_fetcher`, `notifier`, `report_composer`
- Produces: `run(project_key: str, sprint_name: str, dry_run: bool = False) -> list[dict]` — returns all findings; also `lambda_run(project_key, sprint_name)` for Lambda

`main.run()` flow:
1. `fetch_active_sprint_issues()` → issues
2. Fan out to all agents, collect findings
3. If no findings → print clean message, return `[]`
4. `compose()` → report string
5. Print report
6. If not `dry_run`: prompt `"Post this report? [y/N]: "` → if `y`, notify
7. Return all findings

- [ ] **Step 1: Write failing integration test `tests/test_integration.py`**

```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sprint_issues.json").read_text()
)


def _mock_bedrock(text="Sprint health report text"):
    mock_client = MagicMock()
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps(
        {"content": [{"text": text}]}
    ).encode()
    mock_client.invoke_model.return_value = {"body": mock_body}
    return mock_client


def test_run_dry_run_returns_findings():
    from main import run

    with patch("main.get_jira_client"), \
         patch("main.fetch_active_sprint_issues", return_value=FIXTURES), \
         patch("main.boto3") as mock_boto3, \
         patch("main.post_to_teams"), \
         patch("main.post_to_slack"):
        mock_boto3.client.return_value = _mock_bedrock()
        findings = run("ENG", "Sprint 42", dry_run=True)

    assert isinstance(findings, list)
    assert len(findings) > 0
    agents_seen = {f["agent"] for f in findings}
    assert "staleness" in agents_seen
    assert "estimation" in agents_seen
    assert "priority" in agents_seen
    assert "blocker" in agents_seen


def test_run_clean_sprint_returns_empty(capsys):
    from main import run

    clean_issues = [
        {**i,
         "days_since_update": 0,
         "days_since_last_comment": 0,
         "status": "Done",
         "assignee": "Alice",
         "story_points": 5.0,
         "is_blocked": False,
         "labels": [],
         "priority": "Medium",
         "due_date": "2026-07-01",
         "has_escalation_link": False,
         "time_estimate": 3600,
         "time_logged": 3600,
         "subtask_keys": [],
         }
        for i in FIXTURES
    ]
    with patch("main.get_jira_client"), \
         patch("main.fetch_active_sprint_issues", return_value=clean_issues):
        findings = run("ENG", "Sprint 42", dry_run=True)

    assert findings == []
    captured = capsys.readouterr()
    assert "clean" in captured.out.lower()


def test_run_all_findings_have_required_keys():
    from main import run

    with patch("main.get_jira_client"), \
         patch("main.fetch_active_sprint_issues", return_value=FIXTURES), \
         patch("main.boto3") as mock_boto3, \
         patch("main.post_to_teams"), \
         patch("main.post_to_slack"):
        mock_boto3.client.return_value = _mock_bedrock()
        findings = run("ENG", "Sprint 42", dry_run=True)

    for f in findings:
        assert {"agent", "key", "severity", "reason", "url"} <= set(f.keys())
        assert f["severity"] in ("HIGH", "MEDIUM", "LOW")
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/test_integration.py -v
```

Expected: `ImportError: No module named 'main'`

- [ ] **Step 3: Write `src/main.py`**

```python
import os
import sys
import boto3

from jira_fetcher import get_jira_client, fetch_active_sprint_issues
from agents import staleness_agent, estimation_agent, priority_agent, blocker_agent
from agents.commit_agent import run as commit_run
from agents.report_composer import compose
from notifier import post_to_teams, post_to_slack

PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "ENG")


def run(project_key: str, sprint_name: str, dry_run: bool = False) -> list[dict]:
    jira = get_jira_client()
    issues = fetch_active_sprint_issues(jira, project_key)

    all_findings = (
        staleness_agent.run(issues)
        + estimation_agent.run(issues)
        + priority_agent.run(issues)
        + blocker_agent.run(issues)
        + commit_run(issues)
    )

    if not all_findings:
        print("✅ Sprint looks clean. Nothing to flag.")
        return []

    report = compose(all_findings, sprint_name=sprint_name)
    print(report)

    if not dry_run:
        answer = input("\nPost this report to Teams/Slack? [y/N]: ")
        if answer.strip().lower() == "y":
            post_to_teams(report)
            post_to_slack(report)
            print("📬 Posted.")

    return all_findings


if __name__ == "__main__":
    sprint_name = sys.argv[1] if len(sys.argv) > 1 else "Current Sprint"
    dry_run = "--dry-run" in sys.argv
    run(PROJECT_KEY, sprint_name, dry_run=dry_run)
```

- [ ] **Step 4: Run integration tests — expect pass**

```bash
pytest tests/test_integration.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add src/main.py tests/test_integration.py
git commit -m "feat: orchestrator main.py + integration tests — all agents wired"
```

---

### Task 10: Lambda Handler

**Files:**
- Create: `src/lambda_handler.py`

**Interfaces:**
- Produces: `handler(event, context) -> dict` — AWS Lambda entry point
- `event` may contain `project_key` and `sprint_name` keys (injected by EventBridge)

- [ ] **Step 1: Write `src/lambda_handler.py`**

```python
import json
import os
import traceback

from main import run

PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "ENG")


def handler(event: dict, context) -> dict:
    project_key = event.get("project_key", PROJECT_KEY)
    sprint_name = event.get("sprint_name", "Current Sprint")

    try:
        findings = run(project_key, sprint_name, dry_run=False)
        return {
            "statusCode": 200,
            "body": json.dumps({
                "findings_count": len(findings),
                "findings": findings,
            }),
        }
    except Exception as exc:
        traceback.print_exc()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(exc)}),
        }
```

- [ ] **Step 2: Verify imports resolve**

```bash
PYTHONPATH=src python -c "from lambda_handler import handler; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/lambda_handler.py
git commit -m "feat: Lambda handler wrapper for EventBridge cron invocation"
```

---

### Task 11: Docker Compose Local Dev

**Files:**
- Create: `docker-compose.yml`
- Create: `Dockerfile`

**Interfaces:**
- `docker compose run app` → runs `python src/main.py --dry-run`
- Loads env from `.env` file

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV PYTHONPATH=/app/src

CMD ["python", "src/main.py"]
```

- [ ] **Step 2: Write `docker-compose.yml`**

```yaml
version: "3.9"

services:
  app:
    build: .
    env_file: .env
    environment:
      - PYTHONPATH=/app/src
    command: python src/main.py --dry-run
    volumes:
      - ./src:/app/src
```

- [ ] **Step 3: Build image**

```bash
docker compose build
```

Expected: `Successfully built` with no errors

- [ ] **Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "chore: Docker local dev setup"
```

---

### Task 12: Terraform IaC

**Files:**
- Create: `infra/variables.tf`
- Create: `infra/main.tf`
- Create: `infra/outputs.tf`

**Interfaces:**
- Inputs: `aws_region`, `lambda_zip_path`, `jira_url`, `jira_email`, `jira_api_token_secret_arn`, `teams_webhook_secret_arn`, `project_key`, `schedule_expression`
- Produces: EventBridge cron rule that invokes Lambda nightly at 2 AM UTC

- [ ] **Step 1: Write `infra/variables.tf`**

```hcl
variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "lambda_zip_path" {
  type        = string
  description = "Path to the zipped Lambda deployment package"
}

variable "jira_url" {
  type = string
}

variable "jira_email" {
  type = string
}

variable "jira_api_token_secret_arn" {
  type        = string
  description = "ARN of the AWS Secrets Manager secret containing the Jira API token"
}

variable "teams_webhook_secret_arn" {
  type        = string
  description = "ARN of the AWS Secrets Manager secret containing the Teams webhook URL"
}

variable "project_key" {
  type    = string
  default = "ENG"
}

variable "schedule_expression" {
  type    = string
  default = "cron(0 2 * * ? *)"
}
```

- [ ] **Step 2: Write `infra/main.tf`**

```hcl
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

resource "aws_iam_role" "lambda_role" {
  name = "jira-sanity-checker-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "jira-sanity-checker-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [var.jira_api_token_secret_arn, var.teams_webhook_secret_arn]
      },
      {
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_lambda_function" "jira_sanity_checker" {
  filename         = var.lambda_zip_path
  function_name    = "jira-sanity-checker"
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda_handler.handler"
  runtime          = "python3.12"
  timeout          = 300
  source_code_hash = filebase64sha256(var.lambda_zip_path)

  environment {
    variables = {
      JIRA_URL         = var.jira_url
      JIRA_EMAIL       = var.jira_email
      JIRA_PROJECT_KEY = var.project_key
      AWS_REGION       = var.aws_region
    }
  }
}

resource "aws_cloudwatch_event_rule" "nightly" {
  name                = "jira-sanity-checker-nightly"
  description         = "Trigger Jira Sanity Checker at 2 AM UTC"
  schedule_expression = var.schedule_expression
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.nightly.name
  target_id = "JiraSanityCheckerLambda"
  arn       = aws_lambda_function.jira_sanity_checker.arn

  input = jsonencode({
    project_key  = var.project_key
    sprint_name  = "Current Sprint"
  })
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.jira_sanity_checker.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.nightly.arn
}
```

- [ ] **Step 3: Write `infra/outputs.tf`**

```hcl
output "lambda_function_arn" {
  value = aws_lambda_function.jira_sanity_checker.arn
}

output "lambda_function_name" {
  value = aws_lambda_function.jira_sanity_checker.function_name
}

output "eventbridge_rule_arn" {
  value = aws_cloudwatch_event_rule.nightly.arn
}
```

- [ ] **Step 4: Validate Terraform syntax**

```bash
cd infra && terraform init -backend=false && terraform validate
```

Expected: `Success! The configuration is valid.`

- [ ] **Step 5: Commit**

```bash
git add infra/
git commit -m "feat: Terraform — EventBridge cron + Lambda IAM + permissions"
```

---

### Task 13: OSS Packaging (README + LICENSE + CI)

**Files:**
- Create: `README.md`
- Create: `LICENSE`
- Create: `.github/workflows/ci.yml`
- Create: `CONTRIBUTING.md`

- [ ] **Step 1: Write `LICENSE`**

```
MIT License

Copyright (c) 2026 Lease-Ease

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 2: Write `README.md`**

```markdown
# Jira Sanity Checker

Multi-agent sprint hygiene system. Runs 5 rule-based checks against your active Jira sprint, composes a PM-ready report via AWS Bedrock, and posts it to Teams/Slack after human approval.

## Quick Start

```bash
git clone https://github.com/YOUR_ORG/jira-sanity-checker
cd jira-sanity-checker
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your values
PYTHONPATH=src python src/main.py "Sprint 42"
```

## Agents

| Agent | Checks |
|-------|--------|
| Staleness Detector | No update in N days, unassigned In Progress, no comment in 5d |
| Estimation Auditor | Missing points, 0-point issues, time overrun, subtask > parent |
| Priority Drift | Unassigned P1, no due date on critical, label/priority mismatch, orphaned escalation |
| Commit Correlator | Closed ticket without PR, merged PR with open ticket (requires `GITHUB_TOKEN`) |
| Blocker Analyst | Blocked >3d no comment, blocking chain depth >2, blocked without escalation |

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `JIRA_URL` | Yes | — | `https://yourcompany.atlassian.net` |
| `JIRA_EMAIL` | Yes | — | Your Atlassian email |
| `JIRA_API_TOKEN` | Yes | — | Atlassian API token |
| `JIRA_PROJECT_KEY` | Yes | `ENG` | Your Jira project key |
| `JIRA_STORY_POINTS_FIELD` | No | `customfield_10016` | Story points custom field ID |
| `JIRA_STALENESS_THRESHOLD_DAYS` | No | `3` | Days before a ticket is flagged as stale |
| `TEAMS_WEBHOOK_URL` | No | — | Teams incoming webhook URL |
| `SLACK_WEBHOOK_URL` | No | — | Slack incoming webhook URL |
| `GITHUB_TOKEN` | No | — | GitHub PAT (enables commit correlation) |
| `GITHUB_REPO` | No | — | `owner/repo` for GitHub API |
| `AWS_REGION` | No | `us-east-1` | AWS region for Bedrock |

## Finding the Story Points Custom Field

Story points live in a custom field that varies by Jira instance. To find yours:

```bash
curl -u you@company.com:YOUR_API_TOKEN \
  "https://yourcompany.atlassian.net/rest/api/3/field" | \
  python3 -c "import sys,json; [print(f['id'], f['name']) for f in json.load(sys.stdin) if 'point' in f['name'].lower()]"
```

Set `JIRA_STORY_POINTS_FIELD=customfield_XXXXX` in your `.env`.

## Running Tests

```bash
pytest tests/ -v
```

## Local Dev with Docker

```bash
docker compose run app
```

## Deploy to AWS (Lambda + EventBridge)

```bash
# Package Lambda
pip install -r requirements.txt -t lambda_package/
cp -r src/* lambda_package/
cd lambda_package && zip -r ../lambda.zip . && cd ..

# Deploy
cd infra
terraform init
terraform apply \
  -var="lambda_zip_path=../lambda.zip" \
  -var="jira_url=https://yourcompany.atlassian.net" \
  -var="jira_email=you@company.com" \
  -var="jira_api_token_secret_arn=arn:aws:..." \
  -var="teams_webhook_secret_arn=arn:aws:..."
```

## Architecture

```
Trigger (nightly 2AM / CLI / webhook)
         ↓
Sprint Intelligence Agent (main.py)
         ↓
┌─────────────────────────────────────┐
│ Staleness  │ Estimation │ Priority  │
│ Detector   │ Auditor    │ Drift     │
├─────────────────────────────────────┤
│ Commit     │ Blocker    │           │
│ Correlator │ Analyst    │           │
└─────────────────────────────────────┘
         ↓
Report Composer (Bedrock claude-sonnet-4-5)
         ↓
Human approval gate (CLI)
         ↓
Teams / Slack webhook
```

## License

MIT
```

- [ ] **Step 3: Write `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main, "feat/**"]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run tests
        run: pytest tests/ -v
        env:
          JIRA_URL: https://test.atlassian.net
          JIRA_EMAIL: test@test.com
          JIRA_API_TOKEN: dummy
          JIRA_PROJECT_KEY: TEST
          AWS_REGION: us-east-1
```

- [ ] **Step 4: Write `CONTRIBUTING.md`**

```markdown
# Contributing

1. Fork the repo and create a feature branch: `git checkout -b feat/my-change`
2. Write tests first (`pytest tests/ -v` must pass before opening a PR)
3. Follow the normalized issue dict schema in `src/jira_fetcher.py` — all agents consume it
4. Add new agents in `src/agents/` and wire them into `src/main.py`
5. Open a PR against `main`

## Adding a New Agent

1. Create `src/agents/my_agent.py` with a `run(issues: list[dict]) -> list[dict]` function
2. Return findings with keys: `agent`, `key`, `severity` (HIGH/MEDIUM/LOW), `reason`, `url`
3. Write `tests/test_my_agent.py` covering happy path and edge cases
4. Wire into `src/main.py`: add to the `all_findings` list
```

- [ ] **Step 5: Run full test suite one last time**

```bash
pytest tests/ -v --tb=short
```

Expected: all tests pass, no warnings

- [ ] **Step 6: Final commit**

```bash
git add README.md LICENSE CONTRIBUTING.md .github/
git commit -m "chore: OSS packaging — README, LICENSE, GitHub Actions CI"
```

---

## Self-Review

### Spec Coverage Check

| Spec Requirement | Task |
|-----------------|------|
| Nightly cron trigger | Task 12 (EventBridge) |
| Manual CLI invoke | Task 9 (`python src/main.py`) |
| Sprint start webhook | Task 10 (Lambda handler accepts event payload) |
| Sprint Intelligence Agent orchestrator | Task 9 |
| Agent 1: Staleness Detector | Task 3 |
| Agent 2: Estimation Auditor | Task 4 |
| Agent 3: Priority Drift Checker | Task 5 |
| Agent 4: Commit Correlator | Task 6 |
| Agent 5: Blocker Analyst | Task 7 |
| Agent 6: Report Composer | Task 8 |
| Jira REST API v3 (read) | Task 2 |
| Jira Agile API (sprints via JQL openSprints()) | Task 2 |
| GitHub/GitLab API | Task 6 |
| AWS Bedrock Claude | Task 8 |
| AWS EventBridge cron | Task 12 |
| Teams/Slack webhook | Task 8 |
| Jira write API (gated) | Task 9 (gated via `input()`) |
| Sprint Health Report output | Task 8 + Task 9 |
| Draft ticket comments (queued for approval) | Report Composer prompt |
| Action queue (top 10) | Report Composer prompt |
| Python 3.12 | Task 1 |
| jira==3.8.0 + boto3 + requests + dotenv + pytest | Task 1 |
| AWS Secrets Manager | Task 12 (IAM policy) |
| Terraform IaC | Task 12 |
| Docker Compose local dev | Task 11 |
| GitHub repo + README | Task 13 |
| MIT license | Task 13 |
| story_points field configurable | Task 2 (env var) |
| Jira rate limit: paginate maxResults=50, retry | **GAP — see below** |
| Ignore label support | **GAP — see below** |

### Gaps Found and Fixed

**Gap 1: Jira rate limit / retry backoff**

Add to `src/jira_fetcher.py` `fetch_active_sprint_issues()` — paginate with maxResults=50 and retry:

In Task 2, Step 4, replace the `jira.search_issues` call with:

```python
import time

def fetch_active_sprint_issues(jira: JIRA, project_key: str) -> list[dict]:
    field = os.environ.get("JIRA_STORY_POINTS_FIELD", "customfield_10016")
    jql = (
        f"project = {project_key} "
        "AND sprint in openSprints() "
        "ORDER BY updated ASC"
    )
    all_issues = []
    start = 0
    page_size = 50
    while True:
        for attempt in range(3):
            try:
                page = jira.search_issues(
                    jql, startAt=start, maxResults=page_size, expand="changelog",
                    fields=f"summary,status,priority,assignee,{field},labels,"
                           "issuetype,timeoriginalestimate,timespent,issuelinks,"
                           "comment,duedate,parent,subtasks",
                )
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
        all_issues.extend(page)
        if len(page) < page_size:
            break
        start += page_size
    return [_normalize(issue) for issue in all_issues]
```

**Gap 2: Ignore label support**

Spec says "Add ignore label" to suppress false positives. Add to `src/main.py`:

```python
IGNORE_LABEL = os.environ.get("JIRA_IGNORE_LABEL", "sanity-ignore")

def run(...):
    ...
    issues = [i for i in issues if IGNORE_LABEL not in i["labels"]]
    ...
```

Document `JIRA_IGNORE_LABEL` env var in README. Add to `.env.example`:
```
JIRA_IGNORE_LABEL=sanity-ignore
```

---

Plan complete and saved to `docs/superpowers/plans/2026-06-28-jira-sanity-checker.md`.
