# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run (against live Jira)
PYTHONPATH=src python src/main.py "Sprint 42"

# Dry run (no Teams/Slack post, no input prompt)
PYTHONPATH=src python src/main.py "Sprint 42" --dry-run

# Tests
pytest tests/ -v

# Single test file
pytest tests/test_staleness_agent.py -v

# Single test
pytest tests/test_staleness_agent.py::test_stale_in_progress_detected -v

# Local dev (Docker, loads .env automatically)
docker compose run app

# Terraform (from infra/)
terraform init && terraform validate
terraform apply -var="lambda_zip_path=../lambda.zip" ...
```

## Architecture

**Implementation plan:** `docs/superpowers/plans/2026-06-28-jira-sanity-checker.md` — contains all task breakdowns, complete code for every file, and test fixtures. Read it before implementing anything.

**Flow:** `main.py` fetches active sprint → fans out to 5 pure-Python agents → collects findings → Bedrock composes Markdown report → human gate → Teams/Slack

**`src/` layout:**
- `jira_fetcher.py` — `get_jira_client()`, `fetch_active_sprint_issues()`, `_normalize()`. The normalized issue dict schema (22 keys) is the contract all agents consume — any new agent must work with this schema, not the raw Jira object.
- `agents/staleness_agent.py` — Agent 1
- `agents/estimation_agent.py` — Agent 2
- `agents/priority_agent.py` — Agent 3
- `agents/commit_agent.py` — Agent 4 (optional GitHub; skips if `GITHUB_TOKEN` unset)
- `agents/blocker_agent.py` — Agent 5
- `agents/report_composer.py` — Agent 6; single Bedrock call (`us.anthropic.claude-sonnet-4-5`)
- `notifier.py` — Teams (`TEAMS_WEBHOOK_URL`) and Slack (`SLACK_WEBHOOK_URL`); silently skips if URL unset
- `main.py` — orchestrator; `run(project_key, sprint_name, dry_run=False) -> list[dict]`
- `lambda_handler.py` — AWS Lambda entry; wraps `main.run()`

**Agent contract:** every agent exposes `run(issues: list[dict]) -> list[dict]`. Each finding dict must have exactly these keys: `agent`, `key`, `severity` (`HIGH`/`MEDIUM`/`LOW`), `reason`, `url`.

**Tests:** `pytest.ini` sets `pythonpath = src`, so imports work without `PYTHONPATH` prefix during test runs. `tests/fixtures/sprint_issues.json` is the canonical 12-issue fixture; all agent tests load it. Do not add live API calls to tests — mock Jira via `unittest.mock.MagicMock`, mock Bedrock via patching `boto3`.

**Key env vars:**
- `JIRA_STORY_POINTS_FIELD` — custom field ID for story points (default `customfield_10016`; varies by Jira instance)
- `JIRA_STALENESS_THRESHOLD_DAYS` — stale threshold (default `3`)
- `JIRA_IGNORE_LABEL` — tickets with this label are skipped by all agents (default `sanity-ignore`)
- `GITHUB_TOKEN` + `GITHUB_REPO` — enables commit correlation agent
- `AWS_REGION` — Bedrock region (default `us-east-1`)

**Jira writes:** system is read-only by default. `main.py` only posts to Teams/Slack after explicit `input()` confirmation. No agent writes back to Jira.

**IaC:** `infra/` contains Terraform for Lambda + EventBridge cron (2 AM UTC). Lambda zips the `src/` directory and runs `lambda_handler.handler`.
