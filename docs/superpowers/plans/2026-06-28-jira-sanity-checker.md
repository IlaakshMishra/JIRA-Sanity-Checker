# Jira Sanity Checker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-agent sprint hygiene system that fetches Jira issues nightly, runs 5 specialized rule-based checks, composes an LLM-written PM report via AWS Bedrock, and emails a PDF report via AWS SES.

**Architecture:** Orchestrator (`main.py`) fetches the active sprint via Jira API, fans out to 5 pure-Python check agents (Staleness, Estimation, Priority, Commit, Blocker), collects structured `Finding` dicts, then calls a Bedrock-backed Report Composer (Agent 6) that writes Markdown prose. `pdf_generator.py` renders Markdown → HTML → PDF via weasyprint. `notifier.py` sends via AWS SES (plain text + HTML + PDF attachment). No human approval gate — auto-sends.

**Tech Stack:** Python 3.12, `jira==3.8.0`, `boto3==1.35.0`, AWS Bedrock (claude-sonnet-4-5), AWS SES, `weasyprint==62.3`, `markdown==3.6`, `requests==2.32.0`, `python-dotenv==1.0.1`, `pytest==8.3.0`, AWS EventBridge + Lambda container image (deploy), Terraform (IaC), Docker Compose (local dev)

## Global Constraints

- Python 3.12 minimum
- `jira==3.8.0`, `boto3==1.35.0`, `requests==2.32.0`, `python-dotenv==1.0.1`, `pytest==8.3.0` — pin exact versions
- Bedrock model ID: `us.anthropic.claude-sonnet-4-5`
- Jira is read-only — no agent writes back to Jira
- No human approval gate — report auto-sends via SES after compose
- story_points field configurable via `JIRA_STORY_POINTS_FIELD` env var, default `customfield_10016`
- Agents return `list[dict]` with keys: `agent`, `key`, `severity` (HIGH/MEDIUM/LOW), `reason`, `url`
- Run from project root: `PYTHONPATH=src python src/main.py`
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
| `src/pdf_generator.py` | Markdown → HTML → PDF bytes via weasyprint |
| `src/notifier.py` | AWS SES email: plain text + HTML + PDF attachment |
| `src/main.py` | Orchestrator: fetch → agents → compose → send email |
| `src/lambda_handler.py` | AWS Lambda entry point wrapping `main.run()` |
| `tests/fixtures/sprint_issues.json` | 12-issue mock fixture covering all agent edge cases |
| `infra/main.tf` | EventBridge cron rule + Lambda function |
| `infra/variables.tf` | Terraform input variables |
| `infra/outputs.tf` | Terraform outputs (Lambda ARN, EventBridge rule) |
| `docker-compose.yml` | Local dev: runs `python src/main.py` with env loaded |

---

### Task 1: Project Scaffolding ✅ DONE

- [x] `requirements.txt`, `.env.example`, `pytest.ini`, package markers (`src/__init__.py`, `src/agents/__init__.py`, `tests/__init__.py`)

---

### Task 2: Test Fixtures + Jira Fetcher ✅ DONE

**Normalized issue dict schema** (21 keys — consumed by every downstream agent):
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
    "blocking_chain_keys": list[str],
    "has_escalation_link": bool,
    "due_date": str | None,        # "2026-07-01" ISO format
    "parent_key": str | None,
    "subtask_keys": list[str],
    "comment_count": int,
    "url": str,
}
```

- [x] `tests/fixtures/sprint_issues.json` (12-issue fixture)
- [x] `src/jira_fetcher.py` — `get_jira_client()`, `fetch_active_sprint_issues()`, `_normalize()`

---

### Task 3: Staleness Agent (Agent 1) ✅ DONE

Checks:
1. `status in ("In Progress", "In Review") AND days_since_update >= THRESHOLD` → HIGH if > 5d, else MEDIUM
2. `status == "In Progress" AND assignee is None` → HIGH
3. `days_since_last_comment >= 5 AND status in ("In Progress", "In Review")` → MEDIUM

- [x] `src/agents/staleness_agent.py`

---

### Task 4: Estimation Auditor (Agent 2) ✅ DONE

Checks:
1. `story_points is None` → HIGH
2. `story_points == 0` → MEDIUM
3. `time_logged > time_estimate * 1.5` (both non-None, non-zero) → MEDIUM
4. Sum of subtask story_points > parent story_points → MEDIUM

- [x] `src/agents/estimation_agent.py`

---

### Task 5: Priority Drift Checker (Agent 3) ✅ DONE

Checks:
1. `priority in ("Highest", "High") AND assignee is None` → HIGH
2. `priority == "Highest" AND due_date is None` → HIGH
3. Label "critical"/"priority-high" but `priority in ("Low", "Lowest", "Medium")` → MEDIUM
4. `labels contains "escalated" AND has_escalation_link is False` → HIGH

- [x] `src/agents/priority_agent.py`

---

### Task 6: Commit Correlator (Agent 4) ✅ DONE

Checks (via GitHub API — skips silently if `GITHUB_TOKEN` unset):
1. `status == "Done"` but no PR/branch referencing `issue["key"]` → MEDIUM
2. PR merged but issue still open → HIGH

- [x] `src/agents/commit_agent.py`

---

### Task 7: Blocker Analyst (Agent 5)

**Files:** `src/agents/blocker_agent.py`

Checks:
1. `is_blocked AND days_since_last_comment >= 3` → HIGH
2. Blocking chain depth > 2 (BFS over `blocking_chain_keys`) → HIGH
3. `is_blocked AND NOT has_escalation_link` → MEDIUM

- [ ] **Step 1: Write `src/agents/blocker_agent.py`**

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

- [ ] **Step 2: Commit**

```bash
git add src/agents/blocker_agent.py
git commit -m "feat: blocker agent — stale blockers, deep chains, no escalation"
```

---

### Task 8: Report Composer + Email Notifier ✅ DONE (notifier + pdf_generator)

**Files:** `src/agents/report_composer.py` (remaining), `src/pdf_generator.py` ✅, `src/notifier.py` ✅

- [x] `src/pdf_generator.py` — Markdown → styled HTML → PDF via weasyprint
- [x] `src/notifier.py` — AWS SES: `send_email_report(report_md, sprint_name)` sends multipart email (plain text + HTML + PDF attachment); skips if `EMAIL_FROM`/`EMAIL_RECIPIENTS` unset

- [ ] **Step 1: Write `src/agents/report_composer.py`**

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

- [ ] **Step 2: Commit**

```bash
git add src/agents/report_composer.py
git commit -m "feat: report composer — Bedrock Markdown report"
```

---

### Task 9: Main Orchestrator

**Files:** `src/main.py`

`main.run()` flow:
1. `fetch_active_sprint_issues()` → issues
2. Fan out to all agents, collect findings
3. If no findings → print clean message, return `[]`
4. `compose()` → Markdown report string
5. Print report
6. If not `dry_run`: call `send_email_report(report, sprint_name)` (auto-sends, no gate)
7. Return all findings

- [ ] **Step 1: Write `src/main.py`**

```python
import os
import sys

from jira_fetcher import get_jira_client, fetch_active_sprint_issues
from agents import staleness_agent, estimation_agent, priority_agent, blocker_agent
from agents.commit_agent import run as commit_run
from agents.report_composer import compose
from notifier import send_email_report

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
        print("Sprint looks clean. Nothing to flag.")
        return []

    report = compose(all_findings, sprint_name=sprint_name)
    print(report)

    if not dry_run:
        send_email_report(report, sprint_name)

    return all_findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/main.py <project_key> [sprint_name] [--dry-run]")
        sys.exit(1)
    project_key = sys.argv[1]
    sprint_name = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "Current Sprint"
    dry_run = "--dry-run" in sys.argv
    run(project_key, sprint_name, dry_run=dry_run)
```

- [ ] **Step 2: Commit**

```bash
git add src/main.py
git commit -m "feat: orchestrator main.py — all agents wired, auto-send email report"
```

---

### Task 10: Lambda Handler

**Files:** `src/lambda_handler.py`

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

- [ ] **Step 3: Commit**

```bash
git add src/lambda_handler.py
git commit -m "feat: Lambda handler wrapper for EventBridge cron invocation"
```

---

### Task 11: Docker Compose Local Dev ✅ DONE (Dockerfile)

**Files:** `Dockerfile` ✅, `docker-compose.yml`

- [x] `Dockerfile` — python:3.12-slim + weasyprint system deps (libpango, libcairo, etc.) + pip install

- [ ] **Step 1: Write `docker-compose.yml`**

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

- [ ] **Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "chore: Docker local dev setup"
```

---

### Task 12: Terraform IaC

> **Note:** Lambda must use container image (not zip) due to weasyprint system deps. Replace `filename`/`source_code_hash` with `image_uri` pointing to ECR. Add `ses:SendRawEmail` to IAM policy.

**Files:** `infra/variables.tf`, `infra/main.tf`, `infra/outputs.tf`

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

- [ ] **Step 5: Commit**

```bash
git add infra/
git commit -m "feat: Terraform — EventBridge cron + Lambda IAM + permissions"
```

---

### Task 13: OSS Packaging

**Files:** `README.md`, `LICENSE`, `.github/workflows/ci.yml`

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

See architecture diagram and env var table in the File Map above. Include quick start, agents table, deploy instructions.

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

- [ ] **Step 4: Commit**

```bash
git add README.md LICENSE .github/
git commit -m "chore: OSS packaging — README, LICENSE, GitHub Actions CI"
```

---

## Spec Coverage

| Requirement | Task |
|-------------|------|
| Nightly cron trigger | Task 12 (EventBridge) |
| Manual CLI invoke | Task 9 (`python src/main.py`) |
| Sprint start webhook | Task 10 (Lambda handler accepts event payload) |
| Orchestrator | Task 9 |
| Agent 1: Staleness Detector | Task 3 ✅ |
| Agent 2: Estimation Auditor | Task 4 ✅ |
| Agent 3: Priority Drift Checker | Task 5 ✅ |
| Agent 4: Commit Correlator | Task 6 ✅ |
| Agent 5: Blocker Analyst | Task 7 |
| Agent 6: Report Composer | Task 8 |
| Human approval gate | Task 9 |
| Teams/Slack notify | Task 8 |
| Lambda deploy | Task 10 |
| IaC (EventBridge + IAM) | Task 12 |
| Docker local dev | Task 11 |
