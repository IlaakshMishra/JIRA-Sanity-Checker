"""Bulk-create demo stories crafted to trip every sanity-agent finding.

Each ticket is built so its fields alone (no waiting for time to pass) fire a
specific check in staleness_agent / estimation_agent / priority_agent /
blocker_agent, so the very next sanity-report or PPT run against the sprint
has real findings to show. Requires the same .env as main.py (JIRA_URL,
JIRA_EMAIL, JIRA_API_TOKEN, JIRA_STORY_POINTS_FIELD).

Usage:
    PYTHONPATH=src python scripts/seed_demo_stories.py ENG
    PYTHONPATH=src python scripts/seed_demo_stories.py ENG --sprint-name "Sprint 42"
    PYTHONPATH=src python scripts/seed_demo_stories.py ENG --dry-run
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv

from jira_fetcher import get_jira_client

load_dotenv()

STORY_POINTS_FIELD = os.environ.get("JIRA_STORY_POINTS_FIELD", "customfield_10016")


def find_active_sprint(jira, project_key: str, sprint_name: str | None):
    for board in jira.boards(projectKeyOrID=project_key):
        try:
            sprints = jira.sprints(board.id, state="active")
        except Exception:
            continue
        if sprint_name:
            match = next((s for s in sprints if s.name == sprint_name), None)
            if match:
                return match
        elif sprints:
            return sprints[0]
    return None


def set_status(jira, issue, target_substring: str) -> bool:
    for t in jira.transitions(issue):
        if target_substring.lower() in t["name"].lower():
            jira.transition_issue(issue, t["id"])
            return True
    return False


def create(jira, project_key: str, dry_run: bool, **fields) -> object | None:
    payload = {"project": project_key, **fields}
    if dry_run:
        print(f"[dry-run] would create: {payload}")
        return None
    try:
        return jira.create_issue(fields=payload)
    except Exception as exc:
        print(f"FAILED to create {fields.get('summary')!r}: {exc}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project_key")
    parser.add_argument("--sprint-name", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    jira = get_jira_client()
    sprint = find_active_sprint(jira, args.project_key, args.sprint_name)
    if not sprint and not args.dry_run:
        print("No active sprint found — tickets would be created but ignored "
              "by main.py's JQL (`sprint in openSprints()`). Aborting.")
        sys.exit(1)

    created = []  # (key_or_none, description) for the summary table

    def report(issue, description):
        key = issue.key if issue else "(dry-run)"
        created.append((key, description))
        return issue

    # 1. Staleness: In Progress, unassigned, zero comments (999d default)
    i = create(jira, args.project_key, args.dry_run,
               summary="[DEMO] Login page redirect loop",
               issuetype={"name": "Story"}, priority={"name": "Medium"},
               **{STORY_POINTS_FIELD: 3})
    if i and not args.dry_run:
        set_status(jira, i, "in progress")
    report(i, "staleness: In Progress + unassigned + no comments")

    # 2. Estimation: missing story points entirely
    i = create(jira, args.project_key, args.dry_run,
               summary="[DEMO] Add retry logic to webhook consumer",
               issuetype={"name": "Story"}, priority={"name": "Medium"})
    report(i, "estimation: missing story points")

    # 3. Estimation: 0-point issue
    i = create(jira, args.project_key, args.dry_run,
               summary="[DEMO] Rename internal config key",
               issuetype={"name": "Story"}, priority={"name": "Medium"},
               **{STORY_POINTS_FIELD: 0})
    report(i, "estimation: 0-point issue")

    # 4/5. Estimation: subtask total exceeds parent estimate
    parent = create(jira, args.project_key, args.dry_run,
                     summary="[DEMO] Migrate billing service to v2 API",
                     issuetype={"name": "Story"}, priority={"name": "Medium"},
                     **{STORY_POINTS_FIELD: 3})
    report(parent, "estimation: parent (3pts)")
    if parent and not args.dry_run:
        sub = create(jira, args.project_key, args.dry_run,
                      summary="[DEMO] Migrate billing service to v2 API - data backfill",
                      issuetype={"name": "Subtask"}, priority={"name": "Medium"},
                      parent={"key": parent.key},
                      **{STORY_POINTS_FIELD: 5})
        report(sub, "estimation: subtask (5pts) exceeds parent (3pts)")
    elif args.dry_run:
        create(jira, args.project_key, args.dry_run,
               summary="[DEMO] Migrate billing service to v2 API - data backfill",
               issuetype={"name": "Subtask"}, priority={"name": "Medium"},
               **{STORY_POINTS_FIELD: 5})
        report(None, "estimation: subtask (5pts) exceeds parent (3pts)")

    # 6. Priority: Highest, unassigned, no due date
    i = create(jira, args.project_key, args.dry_run,
               summary="[DEMO] Payment gateway returning 500s intermittently",
               issuetype={"name": "Bug"}, priority={"name": "Highest"},
               **{STORY_POINTS_FIELD: 2})
    report(i, "priority: Highest + unassigned + no due date")

    # 7. Priority: label says critical, priority field says Low
    i = create(jira, args.project_key, args.dry_run,
               summary="[DEMO] Cache invalidation race on product page",
               issuetype={"name": "Bug"}, priority={"name": "Low"},
               labels=["critical"], **{STORY_POINTS_FIELD: 2})
    report(i, "priority: label/priority mismatch (critical label, Low priority)")

    # 8. Priority: orphaned escalation label (no linked escalation ticket)
    i = create(jira, args.project_key, args.dry_run,
               summary="[DEMO] Customer data export missing rows",
               issuetype={"name": "Bug"}, priority={"name": "Medium"},
               labels=["escalated"], **{STORY_POINTS_FIELD: 2})
    report(i, "priority: orphaned escalation label")

    # 9-12. Blocker chain of depth 4: A blocks B blocks C blocks D
    chain_summaries = [
        "[DEMO] Chain root: upstream schema change",
        "[DEMO] Chain hop 1: service B waiting on schema change",
        "[DEMO] Chain hop 2: service C waiting on service B",
        "[DEMO] Chain leaf: service D waiting on service C",
    ]
    chain_issues = []
    for s in chain_summaries:
        issue = create(jira, args.project_key, args.dry_run,
                        summary=s, issuetype={"name": "Story"},
                        priority={"name": "Medium"}, **{STORY_POINTS_FIELD: 2})
        chain_issues.append(issue)
    if not args.dry_run and all(chain_issues):
        # chain_issues[i] is blocked by chain_issues[i-1]
        for blocked, blocker in zip(chain_issues[1:], chain_issues[:-1]):
            jira.create_issue_link(
                type="Blocks", inwardIssue=blocked.key, outwardIssue=blocker.key,
            )
    for issue, s in zip(chain_issues, chain_summaries):
        report(issue, f"blocker chain: {s}")

    # 13. Commit agent: closed with nothing to reference (harmless if
    # GITHUB_REPO isn't configured — commit_agent.run() short-circuits then)
    i = create(jira, args.project_key, args.dry_run,
               summary="[DEMO] Fix flaky integration test",
               issuetype={"name": "Story"}, priority={"name": "Medium"},
               **{STORY_POINTS_FIELD: 1})
    if i and not args.dry_run:
        set_status(jira, i, "done")
    report(i, "commit: closed ticket, no PR/branch reference")

    if not args.dry_run:
        keys = [k for k, _ in created if k != "(dry-run)"]
        if keys and sprint:
            jira.add_issues_to_sprint(sprint.id, keys)

    print("\nCreated:" if not args.dry_run else "\nWould create:")
    for key, description in created:
        print(f"  {key:>12}  {description}")


if __name__ == "__main__":
    main()
