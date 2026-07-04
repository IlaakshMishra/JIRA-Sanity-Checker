# Sprint Summary PPT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Weekly, Bedrock-narrated, python-pptx-rendered sprint summary deck, emailed via SES, on its own EventBridge cron — fully decoupled from the existing nightly sanity-check pipeline.

**Architecture:** `main.run_ppt()` fetches active-sprint issues (reusing `jira_fetcher`), computes stats with a pure-Python agent, gets a short Bedrock-written narrative (highlights/risks/next-steps as JSON), renders a 5-slide deck with `python-pptx`, and emails it as an attachment. `lambda_handler.py` dispatches between the existing sanity-check path and this new path on an event `mode` field. A second Terraform cron rule triggers the `mode=ppt` path weekly.

**Tech Stack:** Python 3.12, `python-pptx` (new dependency), `boto3` (Bedrock + SES, already a dependency), pytest + `unittest.mock`, Terraform (existing `infra/` module).

## Global Constraints

- Every agent module keeps the existing `run(issues) -> list[dict]` pattern where applicable, but `sprint_summary_agent.summarize()` and `ppt_narrative.generate()` are a different contract (stats dict / narrative dict) — do not force them into the 5-finding-agent shape (`agent`/`key`/`severity`/`reason`/`url`); this is a separate pipeline by design.
- No live API calls in tests — mock Jira via `unittest.mock.MagicMock`, mock Bedrock/SES via patching `boto3`, per existing test convention (see `tests/test_estimation_agent.py`, `tests/test_main.py`).
- `pytest.ini` sets `pythonpath = src` — imports in tests are unprefixed (`import main`, `from agents import sprint_summary_agent`), no `PYTHONPATH=src` needed at test time.
- Do not touch the existing sanity-check pipeline (`run()`, `staleness_agent`, `estimation_agent`, `priority_agent`, `blocker_agent`, `commit_agent`, `report_composer`, `pdf_generator`) — this feature is additive only.
- Env vars reused as-is: `EMAIL_FROM`, `EMAIL_RECIPIENTS`, `AWS_REGION`, `JIRA_IGNORE_LABEL`. No new env vars introduced.

---

### Task 1: Sprint Summary Agent

**Files:**
- Create: `src/agents/sprint_summary_agent.py`
- Test: `tests/test_sprint_summary_agent.py`

**Interfaces:**
- Consumes: `issues: list[dict]` — the 22-key normalized issue schema from `jira_fetcher._normalize` (see `tests/fixtures/sprint_issues.json` for shape).
- Produces: `summarize(issues: list[dict]) -> dict` with exactly these keys:
  ```python
  {
      "total_issues": int,
      "committed_points": float,
      "completed_points": float,
      "status_counts": {str: int},        # status name -> count
      "by_assignee": {str: {"total": int, "done": int}},  # None assignee -> "Unassigned"
      "carryover_keys": [str, ...],        # issue keys not in a done-like status
      "blocked_issues": [{"key": str, "summary": str, "blocker_count": int}, ...],
  }
  ```
  Done-like statuses (case-insensitive): `"done"`, `"closed"`, `"resolved"`. `story_points` of `None` counts as `0`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sprint_summary_agent.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sprint_summary_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agents.sprint_summary_agent'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/agents/sprint_summary_agent.py
DONE_STATUSES = {"done", "closed", "resolved"}


def summarize(issues: list[dict]) -> dict:
    status_counts: dict[str, int] = {}
    by_assignee: dict[str, dict[str, int]] = {}
    carryover_keys = []
    blocked_issues = []
    committed_points = 0.0
    completed_points = 0.0

    for issue in issues:
        status = issue["status"]
        is_done = status.lower() in DONE_STATUSES
        points = issue["story_points"] or 0

        status_counts[status] = status_counts.get(status, 0) + 1
        committed_points += points
        if is_done:
            completed_points += points
        else:
            carryover_keys.append(issue["key"])

        assignee = issue["assignee"] or "Unassigned"
        entry = by_assignee.setdefault(assignee, {"total": 0, "done": 0})
        entry["total"] += 1
        if is_done:
            entry["done"] += 1

        if issue["is_blocked"]:
            blocked_issues.append({
                "key": issue["key"],
                "summary": issue["summary"],
                "blocker_count": issue["blocker_count"],
            })

    return {
        "total_issues": len(issues),
        "committed_points": committed_points,
        "completed_points": completed_points,
        "status_counts": status_counts,
        "by_assignee": by_assignee,
        "carryover_keys": carryover_keys,
        "blocked_issues": blocked_issues,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_sprint_summary_agent.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/agents/sprint_summary_agent.py tests/test_sprint_summary_agent.py
git commit -m "feat: add sprint summary agent for PPT stats"
```

---

### Task 2: Bedrock Narrative Agent

**Files:**
- Create: `src/agents/ppt_narrative.py`
- Test: `tests/test_ppt_narrative.py`

**Interfaces:**
- Consumes: `stats: dict` (Task 1 shape), `issues: list[dict]` (raw normalized issues).
- Produces: `generate(stats: dict, issues: list[dict]) -> dict` returning exactly:
  ```python
  {"highlights": [str, ...], "risks": [str, ...], "next_steps": [str, ...]}
  ```
  Each list capped at 5 items. On any parse failure, returns all three lists empty — never raises.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ppt_narrative.py
import json
from unittest.mock import MagicMock, patch


def _bedrock_response(text: str):
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps({
        "content": [{"text": text}]
    }).encode()
    return {"body": mock_body}


@patch("agents.ppt_narrative.boto3")
def test_generate_parses_valid_json(mock_boto3):
    from agents.ppt_narrative import generate

    mock_client = MagicMock()
    mock_client.invoke_model.return_value = _bedrock_response(
        json.dumps({
            "highlights": ["Shipped SSO"],
            "risks": ["DB migration blocked"],
            "next_steps": ["Unblock ENG-9"],
        })
    )
    mock_boto3.client.return_value = mock_client

    result = generate({"total_issues": 1}, [])

    assert result == {
        "highlights": ["Shipped SSO"],
        "risks": ["DB migration blocked"],
        "next_steps": ["Unblock ENG-9"],
    }


@patch("agents.ppt_narrative.boto3")
def test_generate_falls_back_on_malformed_json(mock_boto3):
    from agents.ppt_narrative import generate

    mock_client = MagicMock()
    mock_client.invoke_model.return_value = _bedrock_response("not valid json")
    mock_boto3.client.return_value = mock_client

    result = generate({"total_issues": 1}, [])

    assert result == {"highlights": [], "risks": [], "next_steps": []}


@patch("agents.ppt_narrative.boto3")
def test_generate_caps_lists_at_five_items(mock_boto3):
    from agents.ppt_narrative import generate

    mock_client = MagicMock()
    mock_client.invoke_model.return_value = _bedrock_response(
        json.dumps({
            "highlights": [f"h{i}" for i in range(10)],
            "risks": [],
            "next_steps": [],
        })
    )
    mock_boto3.client.return_value = mock_client

    result = generate({"total_issues": 1}, [])

    assert len(result["highlights"]) == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ppt_narrative.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agents.ppt_narrative'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/agents/ppt_narrative.py
import json
import os

import boto3

MODEL_ID = "us.anthropic.claude-sonnet-4-5"

SYSTEM = """You are a senior engineering project manager.
You receive sprint statistics and raw ticket data.
Return STRICT JSON only, no prose, no markdown fences, matching exactly:
{"highlights": [string, ...], "risks": [string, ...], "next_steps": [string, ...]}
Each list has at most 5 items, one short sentence each."""

_EMPTY = {"highlights": [], "risks": [], "next_steps": []}


def generate(stats: dict, issues: list[dict]) -> dict:
    region = os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("bedrock-runtime", region_name=region)

    payload = {
        "model": MODEL_ID,
        "max_tokens": 800,
        "system": SYSTEM,
        "messages": [{
            "role": "user",
            "content": (
                f"Stats JSON:\n{json.dumps(stats, indent=2)}\n\n"
                f"Issues JSON:\n{json.dumps(issues, indent=2)}"
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
    text = body["content"][0]["text"]

    try:
        narrative = json.loads(text)
    except json.JSONDecodeError:
        return dict(_EMPTY)

    if not isinstance(narrative, dict):
        return dict(_EMPTY)

    return {
        "highlights": list(narrative.get("highlights") or [])[:5],
        "risks": list(narrative.get("risks") or [])[:5],
        "next_steps": list(narrative.get("next_steps") or [])[:5],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ppt_narrative.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/agents/ppt_narrative.py tests/test_ppt_narrative.py
git commit -m "feat: add Bedrock narrative agent for PPT highlights/risks/next-steps"
```

---

### Task 3: PPT Generator

**Files:**
- Create: `src/ppt_generator.py`
- Modify: `requirements.txt` (add `python-pptx==1.0.2`)
- Test: `tests/test_ppt_generator.py`

**Interfaces:**
- Consumes: `sprint_name: str`, `stats: dict` (Task 1 shape), `narrative: dict` (Task 2 shape).
- Produces: `build(sprint_name: str, stats: dict, narrative: dict) -> bytes` — raw `.pptx` file bytes, exactly 5 slides in this order: Title, Overview, Status Breakdown, Highlights & Risks, Next Steps.

- [ ] **Step 1: Add the dependency**

```
# requirements.txt — append
python-pptx==1.0.2
```

Run: `pip install python-pptx==1.0.2`

- [ ] **Step 2: Write the failing test**

```python
# tests/test_ppt_generator.py
import io

from pptx import Presentation

SAMPLE_STATS = {
    "total_issues": 12,
    "committed_points": 53.0,
    "completed_points": 8.0,
    "status_counts": {"In Progress": 6, "To Do": 4, "In Review": 1, "Done": 1},
    "by_assignee": {"Alice Smith": {"total": 4, "done": 1}},
    "carryover_keys": ["ENG-1", "ENG-2", "ENG-3"],
    "blocked_issues": [{"key": "ENG-5", "summary": "DB migration", "blocker_count": 1}],
}

SAMPLE_NARRATIVE = {
    "highlights": ["Shipped SSO integration"],
    "risks": ["DB migration blocked on DBA approval"],
    "next_steps": ["Unblock ENG-9 with DBA"],
}


def _all_text(slide) -> str:
    chunks = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            chunks.append(shape.text_frame.text)
    return "\n".join(chunks)


def test_build_produces_five_slides():
    from ppt_generator import build

    result = build("Sprint 42", SAMPLE_STATS, SAMPLE_NARRATIVE)
    prs = Presentation(io.BytesIO(result))

    assert len(prs.slides) == 5


def test_build_title_slide_has_sprint_name():
    from ppt_generator import build

    result = build("Sprint 42", SAMPLE_STATS, SAMPLE_NARRATIVE)
    prs = Presentation(io.BytesIO(result))

    assert "Sprint 42" in _all_text(prs.slides[0])


def test_build_highlights_slide_has_narrative_text():
    from ppt_generator import build

    result = build("Sprint 42", SAMPLE_STATS, SAMPLE_NARRATIVE)
    prs = Presentation(io.BytesIO(result))

    assert "Shipped SSO integration" in _all_text(prs.slides[3])
    assert "DB migration blocked on DBA approval" in _all_text(prs.slides[3])


def test_build_next_steps_slide_has_carryover_keys():
    from ppt_generator import build

    result = build("Sprint 42", SAMPLE_STATS, SAMPLE_NARRATIVE)
    prs = Presentation(io.BytesIO(result))

    text = _all_text(prs.slides[4])
    assert "Unblock ENG-9 with DBA" in text
    assert "ENG-1" in text
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_ppt_generator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ppt_generator'`

- [ ] **Step 4: Write minimal implementation**

```python
# src/ppt_generator.py
from datetime import datetime, timezone
from io import BytesIO

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches

_MAX_CARRYOVER_SHOWN = 15


def build(sprint_name: str, stats: dict, narrative: dict) -> bytes:
    prs = Presentation()

    _add_title_slide(prs, sprint_name)
    _add_overview_slide(prs, stats)
    _add_status_breakdown_slide(prs, stats)
    _add_highlights_risks_slide(prs, narrative)
    _add_next_steps_slide(prs, stats, narrative)

    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _add_title_slide(prs: Presentation, sprint_name: str) -> None:
    layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(layout)
    slide.shapes.title.text = sprint_name
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slide.placeholders[1].text = f"Sprint Summary — generated {date_str}"


def _set_bullets(text_frame, lines: list[str]) -> None:
    text_frame.text = lines[0]
    for line in lines[1:]:
        p = text_frame.add_paragraph()
        p.text = line


def _add_overview_slide(prs: Presentation, stats: dict) -> None:
    layout = prs.slide_layouts[1]
    slide = prs.slides.add_slide(layout)
    slide.shapes.title.text = "Overview"

    committed = stats["committed_points"]
    completed = stats["completed_points"]
    pct = (completed / committed * 100) if committed else 0.0

    lines = [
        f"Committed points: {committed:g}",
        f"Completed points: {completed:g}",
        f"% complete: {pct:.0f}%",
        f"Total issues: {stats['total_issues']}",
    ]
    for status, count in stats["status_counts"].items():
        lines.append(f"{status}: {count}")

    _set_bullets(slide.placeholders[1].text_frame, lines)


def _add_status_breakdown_slide(prs: Presentation, stats: dict) -> None:
    layout = prs.slide_layouts[5]
    slide = prs.slides.add_slide(layout)
    slide.shapes.title.text = "Status Breakdown"

    chart_data = CategoryChartData()
    chart_data.categories = list(stats["status_counts"].keys())
    chart_data.add_series("Issues", list(stats["status_counts"].values()))

    slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(1), Inches(1.5), Inches(8), Inches(5),
        chart_data,
    )


def _add_highlights_risks_slide(prs: Presentation, narrative: dict) -> None:
    layout = prs.slide_layouts[1]
    slide = prs.slides.add_slide(layout)
    slide.shapes.title.text = "Highlights & Risks"

    highlights = narrative.get("highlights") or ["None reported."]
    risks = narrative.get("risks") or ["None reported."]

    lines = ["Highlights:"]
    lines += [f"• {h}" for h in highlights]
    lines.append("Risks:")
    lines += [f"• {r}" for r in risks]

    _set_bullets(slide.placeholders[1].text_frame, lines)


def _add_next_steps_slide(prs: Presentation, stats: dict, narrative: dict) -> None:
    layout = prs.slide_layouts[1]
    slide = prs.slides.add_slide(layout)
    slide.shapes.title.text = "Next Steps"

    next_steps = narrative.get("next_steps") or ["None reported."]
    carryover = stats["carryover_keys"]
    shown = carryover[:_MAX_CARRYOVER_SHOWN]

    lines = list(next_steps)
    lines.append("Carryover:")
    lines += shown
    if len(carryover) > _MAX_CARRYOVER_SHOWN:
        lines.append(f"+{len(carryover) - _MAX_CARRYOVER_SHOWN} more")

    _set_bullets(slide.placeholders[1].text_frame, lines)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_ppt_generator.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add src/ppt_generator.py requirements.txt tests/test_ppt_generator.py
git commit -m "feat: add python-pptx sprint summary deck builder"
```

---

### Task 4: PPT Email Delivery

**Files:**
- Modify: `src/notifier.py`
- Test: `tests/test_notifier_ppt.py`

**Interfaces:**
- Consumes: `pptx_bytes: bytes`, `sprint_name: str`.
- Produces: `send_ppt_email(pptx_bytes: bytes, sprint_name: str) -> None`. Silently returns if `EMAIL_FROM` or `EMAIL_RECIPIENTS` unset (matches `send_email_report` convention).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_notifier_ppt.py
from unittest.mock import MagicMock, patch


def test_send_ppt_email_skips_when_env_unset(monkeypatch):
    from notifier import send_ppt_email

    monkeypatch.delenv("EMAIL_FROM", raising=False)
    monkeypatch.delenv("EMAIL_RECIPIENTS", raising=False)

    with patch("notifier.boto3") as mock_boto3:
        send_ppt_email(b"fake-bytes", "Sprint 42")
        mock_boto3.client.assert_not_called()


@patch("notifier.boto3")
def test_send_ppt_email_sends_when_configured(mock_boto3, monkeypatch):
    from notifier import send_ppt_email

    monkeypatch.setenv("EMAIL_FROM", "sender@company.com")
    monkeypatch.setenv("EMAIL_RECIPIENTS", "a@company.com,b@company.com")

    mock_client = MagicMock()
    mock_boto3.client.return_value = mock_client

    send_ppt_email(b"fake-bytes", "Sprint 42")

    mock_client.send_raw_email.assert_called_once()
    call_kwargs = mock_client.send_raw_email.call_args.kwargs
    assert call_kwargs["Source"] == "sender@company.com"
    assert call_kwargs["Destinations"] == ["a@company.com", "b@company.com"]
    assert b"fake-bytes" in call_kwargs["RawMessage"]["Data"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_notifier_ppt.py -v`
Expected: FAIL with `ImportError: cannot import name 'send_ppt_email' from 'notifier'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/notifier.py — append to end of file
def send_ppt_email(pptx_bytes: bytes, sprint_name: str) -> None:
    sender = os.environ.get("EMAIL_FROM")
    recipients_raw = os.environ.get("EMAIL_RECIPIENTS")
    if not sender or not recipients_raw:
        return

    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
    region = os.environ.get("AWS_REGION", "us-east-1")
    safe_name = sprint_name.replace(" ", "-").replace("/", "-")
    filename = f"{safe_name}-summary.pptx"

    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"Sprint Summary: {sprint_name}"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(f"Sprint summary deck for {sprint_name} attached.", "plain"))

    attachment = MIMEApplication(
        pptx_bytes,
        _subtype="vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    attachment.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(attachment)

    client = boto3.client("ses", region_name=region)
    client.send_raw_email(
        Source=sender,
        Destinations=recipients,
        RawMessage={"Data": msg.as_bytes()},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_notifier_ppt.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/notifier.py tests/test_notifier_ppt.py
git commit -m "feat: add SES PPT email delivery"
```

---

### Task 5: Orchestrator — `run_ppt` + CLI flag

**Files:**
- Modify: `src/main.py`
- Test: `tests/test_main_ppt.py`

**Interfaces:**
- Consumes: `sprint_summary_agent.summarize` (Task 1), `ppt_narrative.generate` (Task 2), `ppt_generator.build` (Task 3, imported as `build_ppt`), `send_ppt_email` (Task 4).
- Produces: `run_ppt(project_key: str, sprint_name: str, dry_run: bool = False) -> bytes`. CLI: `python src/main.py <project_key> [sprint_name] --ppt [--dry-run]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main_ppt.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main_ppt.py -v`
Expected: FAIL with `AttributeError: <module 'main'> does not have the attribute 'build_ppt'` (or `run_ppt` missing)

- [ ] **Step 3: Write minimal implementation**

```python
# src/main.py — replace the full file
import os
import sys

from dotenv import load_dotenv

from jira_fetcher import get_jira_client, fetch_active_sprint_issues
from agents import staleness_agent, estimation_agent, priority_agent, blocker_agent
from agents import sprint_summary_agent, ppt_narrative
from agents.commit_agent import run as commit_run
from agents.report_composer import compose
from notifier import send_email_report, send_ppt_email
from ppt_generator import build as build_ppt

load_dotenv()

PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "ENG")


def run(project_key: str, sprint_name: str, dry_run: bool = False) -> list[dict]:
    jira = get_jira_client()
    issues = fetch_active_sprint_issues(jira, project_key)

    ignore_label = os.environ.get("JIRA_IGNORE_LABEL", "sanity-ignore")
    issues = [i for i in issues if ignore_label not in i["labels"]]

    all_findings = (
        staleness_agent.run(issues)
        + estimation_agent.run(issues)
        + priority_agent.run(issues)
        + blocker_agent.run(issues)
        + commit_run(issues)
    )

    if not all_findings:
        print("Sprint looks clean. Nothing to flag.")
        return []

    report = compose(all_findings, sprint_name=sprint_name)
    print(report)

    if not dry_run:
        send_email_report(report, sprint_name)

    return all_findings


def run_ppt(project_key: str, sprint_name: str, dry_run: bool = False) -> bytes:
    jira = get_jira_client()
    issues = fetch_active_sprint_issues(jira, project_key)

    ignore_label = os.environ.get("JIRA_IGNORE_LABEL", "sanity-ignore")
    issues = [i for i in issues if ignore_label not in i["labels"]]

    stats = sprint_summary_agent.summarize(issues)
    narrative = ppt_narrative.generate(stats, issues)
    pptx_bytes = build_ppt(sprint_name, stats, narrative)

    if not dry_run:
        send_ppt_email(pptx_bytes, sprint_name)

    return pptx_bytes


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/main.py <project_key> [sprint_name] [--ppt] [--dry-run]")
        sys.exit(1)
    project_key = sys.argv[1]
    sprint_name = next(
        (a for a in sys.argv[2:] if not a.startswith("--")),
        "Current Sprint",
    )
    dry_run = "--dry-run" in sys.argv
    if "--ppt" in sys.argv:
        run_ppt(project_key, sprint_name, dry_run=dry_run)
    else:
        run(project_key, sprint_name, dry_run=dry_run)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_main_ppt.py tests/test_main.py -v`
Expected: PASS (all tests, including the pre-existing `test_main.py` still passing unmodified)

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/test_main_ppt.py
git commit -m "feat: add run_ppt orchestrator and --ppt CLI flag"
```

---

### Task 6: Lambda Mode Dispatch

**Files:**
- Modify: `src/lambda_handler.py`
- Test: `tests/test_lambda_handler.py`

**Interfaces:**
- Consumes: `run` and `run_ppt` from `main` (Task 5).
- Produces: `handler(event: dict, context) -> dict` — dispatches on `event.get("mode", "sanity")`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lambda_handler.py
from unittest.mock import patch

import lambda_handler


@patch("lambda_handler.run_ppt")
@patch("lambda_handler.run")
def test_handler_dispatches_ppt_mode(mock_run, mock_run_ppt):
    mock_run_ppt.return_value = b"BYTES"

    result = lambda_handler.handler(
        {"mode": "ppt", "project_key": "ENG", "sprint_name": "Sprint 42"}, None
    )

    mock_run_ppt.assert_called_once_with("ENG", "Sprint 42", dry_run=False)
    mock_run.assert_not_called()
    assert result["statusCode"] == 200


@patch("lambda_handler.run_ppt")
@patch("lambda_handler.run")
def test_handler_defaults_to_sanity_mode(mock_run, mock_run_ppt):
    mock_run.return_value = []

    result = lambda_handler.handler(
        {"project_key": "ENG", "sprint_name": "Sprint 42"}, None
    )

    mock_run.assert_called_once_with("ENG", "Sprint 42", dry_run=False)
    mock_run_ppt.assert_not_called()
    assert result["statusCode"] == 200


@patch("lambda_handler.run_ppt")
@patch("lambda_handler.run")
def test_handler_returns_500_on_exception(mock_run, mock_run_ppt):
    mock_run.side_effect = RuntimeError("boom")

    result = lambda_handler.handler(
        {"project_key": "ENG", "sprint_name": "Sprint 42"}, None
    )

    assert result["statusCode"] == 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_lambda_handler.py -v`
Expected: FAIL with `AttributeError: <module 'lambda_handler'> does not have the attribute 'run_ppt'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/lambda_handler.py — replace the full file
import json
import os
import traceback

from main import run, run_ppt

PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "ENG")


def handler(event: dict, context) -> dict:
    project_key = event.get("project_key", PROJECT_KEY)
    sprint_name = event.get("sprint_name", "Current Sprint")
    mode = event.get("mode", "sanity")

    try:
        if mode == "ppt":
            pptx_bytes = run_ppt(project_key, sprint_name, dry_run=False)
            return {
                "statusCode": 200,
                "body": json.dumps({"mode": "ppt", "bytes": len(pptx_bytes)}),
            }

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

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_lambda_handler.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/lambda_handler.py tests/test_lambda_handler.py
git commit -m "feat: dispatch lambda handler on event mode (sanity/ppt)"
```

---

### Task 7: Weekly EventBridge Cron

**Files:**
- Modify: `infra/scheduler.tf`
- Modify: `infra/variables.tf`
- Modify: `infra/terraform.tfvars.example`

**Interfaces:**
- Consumes: `aws_lambda_function.app` (existing, defined in `infra/scheduler.tf`).
- Produces: `aws_cloudwatch_event_rule.ppt_weekly`, `aws_cloudwatch_event_target.lambda_ppt`, `aws_lambda_permission.allow_eventbridge_ppt`, `var.ppt_schedule_expression`.

- [ ] **Step 1: Add the variable**

```hcl
# infra/variables.tf — append
variable "ppt_schedule_expression" {
  type        = string
  default     = "cron(0 17 ? * FRI *)"
  description = "EventBridge cron for weekly sprint summary PPT — default Friday 5PM UTC"
}
```

- [ ] **Step 2: Add the cron rule, target, and permission**

```hcl
# infra/scheduler.tf — append
resource "aws_cloudwatch_event_rule" "ppt_weekly" {
  name                = "${var.project}-ppt-weekly"
  description         = "Jira Sanity Checker — weekly sprint summary PPT"
  schedule_expression = var.ppt_schedule_expression
}

resource "aws_cloudwatch_event_target" "lambda_ppt" {
  rule      = aws_cloudwatch_event_rule.ppt_weekly.name
  target_id = "JiraSanityCheckerPPTLambda"
  arn       = aws_lambda_function.app.arn

  input = jsonencode({
    mode        = "ppt"
    project_key = var.jira_project_key
    sprint_name = "Current Sprint"
  })
}

resource "aws_lambda_permission" "allow_eventbridge_ppt" {
  statement_id  = "AllowEventBridgeInvokePPT"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.app.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ppt_weekly.arn
}
```

- [ ] **Step 3: Document the new var in the example tfvars**

```hcl
# infra/terraform.tfvars.example — append
# EventBridge cron for weekly PPT summary — default Friday 5PM UTC
ppt_schedule_expression = "cron(0 17 ? * FRI *)"
```

- [ ] **Step 4: Validate**

Run (from `infra/`): `terraform validate`
Expected: `Success! The configuration is valid.`

- [ ] **Step 5: Commit**

```bash
git add infra/scheduler.tf infra/variables.tf infra/terraform.tfvars.example
git commit -m "feat: add weekly EventBridge cron for sprint summary PPT"
```

---

### Task 8: Full-Suite Verification

**Files:** none (verification only — no new code)

**Interfaces:** none — this task runs the complete test suite built by Tasks 1–6 and confirms no regressions in the pre-existing suite.

- [ ] **Step 1: Run the full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS — the 6 new PPT test files (Tasks 1–6) plus every pre-existing test file (`test_commit_agent.py`, `test_estimation_agent.py`, `test_jira_fetcher.py`, `test_main.py`, `test_priority_agent.py`, `test_staleness_agent.py`) unchanged and green.

- [ ] **Step 2: If anything fails, fix forward**

Do not skip or delete a failing test to make the suite green. If a failure surfaces a real bug in Tasks 1–6, fix the implementation in its own file and re-run. If a failure is in a pre-existing test, stop and report — it means an earlier task touched something it shouldn't have (see Global Constraints).

- [ ] **Step 3: Confirm `terraform validate` still passes**

Run (from `infra/`): `terraform validate`
Expected: `Success! The configuration is valid.`

- [ ] **Step 4: Report**

Summarize: total test count, pass count, any fixes made during this task, confirmation that Tasks 1–7 are all committed.
