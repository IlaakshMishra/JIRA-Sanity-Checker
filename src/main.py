import os
import sys

from dotenv import load_dotenv

from jira_fetcher import get_jira_client, fetch_active_sprint_issues
from agents import staleness_agent, estimation_agent, priority_agent, blocker_agent
from agents.commit_agent import run as commit_run
from agents.report_composer import compose
from notifier import send_email_report

load_dotenv()

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
    sprint_name = next(
        (a for a in sys.argv[2:] if not a.startswith("--")),
        "Current Sprint",
    )
    dry_run = "--dry-run" in sys.argv
    run(project_key, sprint_name, dry_run=dry_run)
