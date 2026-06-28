import json
import os
import sys
import traceback

from dotenv import load_dotenv

sys.path.insert(0, "/var/task/src")

from jira_fetcher import get_jira_client, fetch_active_sprint_issues
from agents import staleness_agent, estimation_agent, priority_agent, blocker_agent
from agents.commit_agent import run as commit_run
from agents.report_composer import compose
from notifier import send_email_report

load_dotenv()


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

    report = compose(all_findings, sprint_name)
    print(report)

    if not dry_run:
        send_email_report(report, sprint_name)

    return all_findings


def handler(event: dict, context) -> dict:
    project_key = event.get("project_key", os.environ.get("JIRA_PROJECT_KEY", "ENG"))
    sprint_name = event.get("sprint_name", "Current Sprint")
    dry_run = event.get("dry_run", False)

    try:
        findings = run(project_key, sprint_name, dry_run=dry_run)
        return {
            "statusCode": 200,
            "body": json.dumps({"findings_count": len(findings), "findings": findings}),
        }
    except Exception as exc:
        traceback.print_exc()
        return {"statusCode": 500, "body": json.dumps({"error": str(exc)})}
