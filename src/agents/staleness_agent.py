import os

STALENESS_THRESHOLD = int(os.environ.get("JIRA_STALENESS_THRESHOLD_DAYS", "3"))
ACTIVE_STATUSES = ("In Progress", "In Review")


def run(issues: list[dict]) -> list[dict]:
    findings = []
    for issue in issues:
        if issue["status"] not in ACTIVE_STATUSES:
            continue

        if issue["days_since_update"] >= STALENESS_THRESHOLD:
            severity = "HIGH" if issue["days_since_update"] > 5 else "MEDIUM"
            findings.append({
                "agent": "staleness",
                "key": issue["key"],
                "severity": severity,
                "reason": f"No update in {issue['days_since_update']}d (threshold: {STALENESS_THRESHOLD}d)",
                "url": issue["url"],
            })

        if issue["status"] == "In Progress" and not issue["assignee"]:
            findings.append({
                "agent": "staleness",
                "key": issue["key"],
                "severity": "HIGH",
                "reason": "In Progress with no assignee",
                "url": issue["url"],
            })

        if issue["days_since_last_comment"] >= 5:
            findings.append({
                "agent": "staleness",
                "key": issue["key"],
                "severity": "MEDIUM",
                "reason": f"No comment in {issue['days_since_last_comment']}d",
                "url": issue["url"],
            })

    return findings
