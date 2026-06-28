import os
import time
from datetime import datetime, timezone
from jira import JIRA


def get_jira_client() -> JIRA:
    return JIRA(
        server=os.environ["JIRA_URL"],
        basic_auth=(os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"]),
    )


def fetch_active_sprint_issues(jira: JIRA, project_key: str) -> list[dict]:
    """Fetch all issues in the active sprint for a project.

    Uses pagination to retrieve all results (Jira caps a single call at 100
    by default) and retries up to 3 times on transient failures.
    """
    field = os.environ.get("JIRA_STORY_POINTS_FIELD", "customfield_10016")
    jql = (
        f"project = {project_key} "
        "AND sprint in openSprints() "
        "ORDER BY updated ASC"
    )
    fields = (
        f"summary,status,priority,assignee,{field},labels,"
        "issuetype,timeoriginalestimate,timespent,issuelinks,"
        "comment,duedate,parent,subtasks"
    )

    all_issues: list = []
    start_at = 0
    page_size = 100
    max_retries = 3

    while True:
        for attempt in range(1, max_retries + 1):
            try:
                page = jira.search_issues(
                    jql,
                    startAt=start_at,
                    maxResults=page_size,
                    expand="changelog",
                    fields=fields,
                )
                break
            except Exception:
                if attempt == max_retries:
                    raise
                time.sleep(2 ** attempt)  # exponential back-off: 2s, 4s

        all_issues.extend(page)

        if len(page) < page_size:
            # Received fewer results than the page size — we've hit the end.
            break

        start_at += len(page)

    return [_normalize(issue) for issue in all_issues]


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
