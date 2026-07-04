DONE_STATUSES = {"done", "closed", "resolved"}


def summarize(issues: list[dict]) -> dict:
    status_counts: dict[str, int] = {}
    by_assignee: dict[str, dict[str, int]] = {}
    carryover_keys = []
    blocked_issues = []
    committed_points = 0.0
    completed_points = 0.0

    for issue in issues:
        status = issue["status"]
        is_done = status.lower() in DONE_STATUSES
        points = issue["story_points"] or 0

        status_counts[status] = status_counts.get(status, 0) + 1
        committed_points += points
        if is_done:
            completed_points += points
        else:
            carryover_keys.append(issue["key"])

        assignee = issue["assignee"] or "Unassigned"
        entry = by_assignee.setdefault(assignee, {"total": 0, "done": 0})
        entry["total"] += 1
        if is_done:
            entry["done"] += 1

        if issue["is_blocked"]:
            blocked_issues.append({
                "key": issue["key"],
                "summary": issue["summary"],
                "blocker_count": issue["blocker_count"],
            })

    return {
        "total_issues": len(issues),
        "committed_points": committed_points,
        "completed_points": completed_points,
        "status_counts": status_counts,
        "by_assignee": by_assignee,
        "carryover_keys": carryover_keys,
        "blocked_issues": blocked_issues,
    }
