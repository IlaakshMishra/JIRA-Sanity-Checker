# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Sanity report — run against live Jira
PYTHONPATH=src python src/main.py "Sprint 42"

# Sanity report — dry run (no SES send)
PYTHONPATH=src python src/main.py "Sprint 42" --dry-run

# PPT sprint summary deck instead of the sanity report
PYTHONPATH=src python src/main.py ENG "Sprint 42" --ppt
PYTHONPATH=src python src/main.py ENG "Sprint 42" --ppt --dry-run

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

**Implementation plan:** `docs/superpowers/plans/2026-06-28-jira-sanity-checker.md` — original task breakdown, code, and test fixtures for the sanity-check flow. Read it before implementing sanity-agent changes; it predates the PPT/summary flow below.

There are **two independent entry points** off the same fetched issue list, both reachable via `main.py` and `lambda_handler.py`:

1. **Sanity report** (`main.run`) — fetch active sprint → fan out to 5 pure-Python agents → collect findings → single Bedrock call composes a Markdown report → `notifier.send_email_report` sends it via SES (plain text + HTML + PDF attachment, PDF built by `pdf_generator.py` via weasyprint).
2. **PPT summary** (`main.run_ppt`) — fetch active sprint → `sprint_summary_agent.summarize` computes stats (points, status counts, per-assignee, carryover, blocked) → `ppt_narrative.generate` makes a second, separate Bedrock call turning stats+issues into `{highlights, risks, next_steps}` JSON → `ppt_generator.build` renders a `.pptx` → `notifier.send_ppt_email` sends it via SES.

`lambda_handler.handler` dispatches between the two based on `event["mode"]` (`"sanity"` default, or `"ppt"`). Terraform (`infra/scheduler.tf`) wires two separate EventBridge rules onto the same Lambda: the nightly sanity cron (`var.schedule_expression`) invokes with no mode (defaults to sanity), and a weekly cron (`var.ppt_schedule_expression`) invokes with `mode: "ppt"`.

**No human-in-the-loop gate**: delivery is unconditional — both `run()` and `run_ppt()` send via SES automatically unless `dry_run=True`. There is no Teams/Slack integration and no `input()` confirmation prompt anywhere in this codebase; treat any reference to those as stale.

**`src/` layout:**
- `jira_fetcher.py` — `get_jira_client()`, `fetch_active_sprint_issues()`, `_normalize()`. The normalized issue dict schema (21 keys, see the `return` in `_normalize`) is the contract all agents and the summary/narrative code consume — any new agent must work with this schema, not the raw Jira object.
- `agents/staleness_agent.py` — Agent 1 (sanity)
- `agents/estimation_agent.py` — Agent 2 (sanity)
- `agents/priority_agent.py` — Agent 3 (sanity)
- `agents/commit_agent.py` — Agent 4 (sanity; optional GitHub — skips if no token resolved)
- `agents/blocker_agent.py` — Agent 5 (sanity)
- `agents/report_composer.py` — sanity report Bedrock call (`us.anthropic.claude-sonnet-4-5-20250929-v1:0`), returns Markdown
- `agents/sprint_summary_agent.py` — pure aggregation (no Bedrock) over issues into PPT stats
- `agents/ppt_narrative.py` — PPT Bedrock call, returns structured JSON; **never raises** — any Bedrock/parse failure is caught and falls back to `{highlights: [], risks: [], next_steps: []}` so a narrative failure never blocks deck delivery
- `ppt_generator.py` — builds the `.pptx` from stats + narrative
- `pdf_generator.py` — Markdown → HTML → PDF via weasyprint, used only by the sanity report path
- `notifier.py` — `send_email_report()` (sanity, multipart w/ PDF) and `send_ppt_email()` (PPT, `.pptx` attachment); both are SES-only and both silently no-op if `EMAIL_FROM`/`EMAIL_RECIPIENTS` are unset
- `main.py` — `run(project_key, sprint_name, dry_run=False) -> list[dict]` (sanity) and `run_ppt(project_key, sprint_name, dry_run=False) -> bytes` (PPT); CLI dispatches on `--ppt` flag
- `lambda_handler.py` — AWS Lambda entry; dispatches on `event["mode"]`

**Agent contract (sanity agents only):** every sanity agent exposes `run(issues: list[dict]) -> list[dict]`. Each finding dict must have exactly these keys: `agent`, `key`, `severity` (`HIGH`/`MEDIUM`/`LOW`), `reason`, `url`. `sprint_summary_agent` and `ppt_narrative` do not follow this contract — they're a stats aggregator and a narrative generator, not finding-emitters.

**Tests:** `pytest.ini` sets `pythonpath = src`, so imports work without `PYTHONPATH` prefix during test runs. `tests/fixtures/sprint_issues.json` is the canonical 12-issue fixture; most agent tests load it. Do not add live API calls to tests — mock Jira via `unittest.mock.MagicMock`, mock Bedrock via patching `boto3`.

**Key env vars:**
- `JIRA_STORY_POINTS_FIELD` — custom field ID for story points (default `customfield_10016`; varies by Jira instance)
- `JIRA_STALENESS_THRESHOLD_DAYS` — stale threshold (default `3`)
- `JIRA_IGNORE_LABEL` — tickets with this label are skipped by all agents and by the summary/narrative flow (default `sanity-ignore`)
- `GITHUB_TOKEN` / `GITHUB_TOKEN_SECRET_ARN` + `GITHUB_REPO` — enables commit correlation agent; Secrets Manager ARN takes priority over the plain env var
- `EMAIL_FROM` + `EMAIL_RECIPIENTS` — required for either SES send path; both no-op silently if missing
- `AWS_REGION` — Bedrock + SES region (default `us-east-1`)

**Jira writes:** system is read-only. No agent writes back to Jira.

**IaC:** `infra/` contains Terraform for Lambda + two EventBridge cron rules (nightly sanity report, weekly PPT summary). Lambda zips the `src/` directory and runs `lambda_handler.handler`.
