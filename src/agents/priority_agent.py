HIGH_PRIORITIES = ("Highest", "High")
URGENT_PRIORITIES = ("Highest",)
CRITICAL_LABELS = {"critical", "priority-high", "priority-critical"}
LOW_PRIORITIES = ("Low", "Lowest", "Medium")


def run(issues: list[dict]) -> list[dict]:
    findings = []

    for issue in issues:
        priority = issue.get("priority") or ""
        labels = {label.lower() for label in issue.get("labels", [])}

        if priority in HIGH_PRIORITIES and not issue["assignee"]:
            findings.append({
                "agent": "priority",
                "key": issue["key"],
                "severity": "HIGH",
                "reason": f"{priority} priority with no assignee",
                "url": issue["url"],
            })

        if priority in URGENT_PRIORITIES and not issue["due_date"]:
            findings.append({
                "agent": "priority",
                "key": issue["key"],
                "severity": "HIGH",
                "reason": f"{priority} priority with no due date",
                "url": issue["url"],
            })

        label_says_critical = bool(labels & CRITICAL_LABELS)
        if label_says_critical and priority in LOW_PRIORITIES:
            matched = labels & CRITICAL_LABELS
            findings.append({
                "agent": "priority",
                "key": issue["key"],
                "severity": "MEDIUM",
                "reason": (
                    f"Label mismatch: label '{next(iter(matched))}' "
                    f"but priority is '{priority}'"
                ),
                "url": issue["url"],
            })

        if "escalated" in labels and not issue["has_escalation_link"]:
            findings.append({
                "agent": "priority",
                "key": issue["key"],
                "severity": "HIGH",
                "reason": "Orphaned escalation: 'escalated' label but no escalation ticket linked",
                "url": issue["url"],
            })

    return findings
