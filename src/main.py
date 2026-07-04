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

    if os.environ.get("AGENT_BACKEND", "local") == "agentcore":
        import agentcore_agents as backend
        run_staleness, run_estimation = backend.staleness_run, backend.estimation_run
        run_priority, run_blocker = backend.priority_run, backend.blocker_run
        run_commit = backend.commit_run
        compose_report = backend.report_composer_compose
    else:
        run_staleness, run_estimation = staleness_agent.run, estimation_agent.run
        run_priority, run_blocker = priority_agent.run, blocker_agent.run
        run_commit = commit_run
        compose_report = lambda findings, name: compose(findings, sprint_name=name)

    all_findings = (
        run_staleness(issues)
        + run_estimation(issues)
        + run_priority(issues)
        + run_blocker(issues)
        + run_commit(issues)
    )

    if not all_findings:
        print("Sprint looks clean. Nothing to flag.")
        return []

    report = compose_report(all_findings, sprint_name)
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
