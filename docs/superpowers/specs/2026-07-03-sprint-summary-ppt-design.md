# Sprint Summary PPT — Design

## Purpose
Weekly (end-of-sprint) auto-generated PowerPoint sprint summary, emailed to stakeholders. Separate from the existing nightly sanity-check pipeline — no shared findings, independent trigger and data flow.

## Flow
```
main.run_ppt(project_key, sprint_name, dry_run)
  → jira_fetcher.fetch_active_sprint_issues()          [reused, unmodified]
  → agents/sprint_summary_agent.summarize(issues)       → stats dict (pure Python, no Bedrock)
  → agents/ppt_narrative.generate(stats, issues)        → {highlights, risks, next_steps} JSON (Bedrock)
  → ppt_generator.build(sprint_name, stats, narrative)  → .pptx bytes (python-pptx)
  → notifier.send_ppt_email(bytes, sprint_name)         [SES; skipped if dry_run]
```

## New files

### `src/agents/sprint_summary_agent.py`
`summarize(issues: list[dict]) -> dict`. Pure computation, no I/O, no Bedrock. Output:
```python
{
  "total_issues": int,
  "committed_points": float,
  "completed_points": float,
  "status_counts": {status_name: count},
  "by_assignee": {assignee_or_"Unassigned": {"total": int, "done": int}},
  "carryover_keys": [issue_key, ...],   # status not in DONE_STATUSES
  "blocked_issues": [{"key", "summary", "blocker_count"}, ...],
}
```
`DONE_STATUSES = {"Done", "Closed", "Resolved"}` (case-insensitive match against `issue["status"]`).

### `src/agents/ppt_narrative.py`
`generate(stats: dict, issues: list[dict]) -> dict`. Single Bedrock call (`us.anthropic.claude-sonnet-4-5`, same client pattern as `report_composer.py`). System prompt instructs model to return **strict JSON only**: `{"highlights": [str, ...], "risks": [str, ...], "next_steps": [str, ...]}`, max 5 items per list, one sentence each. Parse with `json.loads`; on parse failure, fall back to `{"highlights": [], "risks": [], "next_steps": []}` and log a warning (do not raise — a broken narrative slide must not crash the whole run).

### `src/ppt_generator.py`
`build(sprint_name: str, stats: dict, narrative: dict) -> bytes`, using `python-pptx`. Five slides:
1. **Title** — sprint name, subtitle "Sprint Summary — generated {date}".
2. **Overview** — bullets: committed vs completed points, % complete, total issues, status counts.
3. **Status breakdown** — bar chart (`python-pptx` `CategoryChartData`) of `status_counts`.
4. **Highlights & Risks** — two bullet columns from `narrative["highlights"]` / `narrative["risks"]`. Empty list → single placeholder bullet "None reported."
5. **Next steps / Carryover** — bullets from `narrative["next_steps"]` + `stats["carryover_keys"]` (capped at 15 keys shown, "+N more" suffix beyond that).

Returns raw bytes (`BytesIO().getvalue()`) — caller decides what to do with them (email, write to disk, etc).

## Modified files

### `src/main.py`
Add `run_ppt(project_key: str, sprint_name: str, dry_run: bool = False) -> bytes`:
```python
def run_ppt(project_key, sprint_name, dry_run=False):
    jira = get_jira_client()
    issues = fetch_active_sprint_issues(jira, project_key)
    ignore_label = os.environ.get("JIRA_IGNORE_LABEL", "sanity-ignore")
    issues = [i for i in issues if ignore_label not in i["labels"]]

    stats = sprint_summary_agent.summarize(issues)
    narrative = ppt_narrative.generate(stats, issues)
    pptx_bytes = ppt_generator.build(sprint_name, stats, narrative)

    if not dry_run:
        send_ppt_email(pptx_bytes, sprint_name)

    return pptx_bytes
```
CLI: add `--ppt` flag to `__main__` block. `--ppt` + `--dry-run` can combine (dry run just skips the email send, same convention as existing `run()`).

### `src/lambda_handler.py`
Dispatch on `event.get("mode", "sanity")`:
```python
mode = event.get("mode", "sanity")
if mode == "ppt":
    pptx_bytes = run_ppt(project_key, sprint_name, dry_run=False)
    return {"statusCode": 200, "body": json.dumps({"mode": "ppt", "bytes": len(pptx_bytes)})}
# else existing sanity path unchanged
```

### `src/notifier.py`
Add `send_ppt_email(pptx_bytes: bytes, sprint_name: str) -> None`. Mirrors existing `send_email_report` SES pattern (same `EMAIL_FROM`/`EMAIL_RECIPIENTS` env vars, same silent-skip-if-unset convention), attaches `pptx_bytes` as MIME part with content type `application/vnd.openxmlformats-officedocument.presentationml.presentation`, filename `{sprint_name}-summary.pptx`.

### `infra/scheduler.tf`
Add second `aws_cloudwatch_event_rule "ppt_weekly"` (`schedule_expression = var.ppt_schedule_expression`), corresponding `aws_cloudwatch_event_target` (input includes `mode = "ppt"`), and `aws_lambda_permission "allow_eventbridge_ppt"` (distinct `statement_id`, `source_arn` pointing at the new rule). Same Lambda function/image — no new Lambda resource.

### `infra/variables.tf`
Add `variable "ppt_schedule_expression"` — default `"cron(0 17 ? * FRI *)"` (Friday 5PM UTC).

### `infra/terraform.tfvars.example`
Document the new var alongside existing `schedule_expression`.

### `requirements.txt`
Add `python-pptx`.

## Tests
All follow existing convention: mock Jira via `MagicMock`, mock Bedrock via patching `boto3`, load `tests/fixtures/sprint_issues.json`, no live API calls.

- `tests/test_sprint_summary_agent.py` — stats math against the 12-issue fixture (known committed/completed points, status counts, carryover list).
- `tests/test_ppt_narrative.py` — mock Bedrock response body, assert JSON parsed correctly; assert fallback dict returned on malformed JSON (no exception raised).
- `tests/test_ppt_generator.py` — call `build()`, read back bytes with `python_pptx.Presentation(io.BytesIO(...))`, assert 5 slides, assert sprint name appears on title slide, assert narrative bullets appear on slide 4.
- `tests/test_main_ppt.py` — `run_ppt()` with everything mocked; assert `dry_run=True` does not call `send_ppt_email`; assert `dry_run=False` does.

## Out of scope
- No reuse of the 5 sanity-check agents' findings — PPT risks/highlights come from Bedrock narrative over raw issues only, per explicit decision to keep pipelines decoupled.
- No S3 upload path — email attachment only.
- No new Lambda function/image — single handler, mode-dispatched.
