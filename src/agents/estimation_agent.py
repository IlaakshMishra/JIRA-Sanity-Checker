def run(issues: list[dict]) -> list[dict]:
    issue_map = {i["key"]: i for i in issues}
    findings = []

    for issue in issues:
        pts = issue["story_points"]

        if pts is None:
            findings.append({
                "agent": "estimation",
                "key": issue["key"],
                "severity": "HIGH",
                "reason": "Missing story points estimate",
                "url": issue["url"],
            })
            continue

        if pts == 0:
            findings.append({
                "agent": "estimation",
                "key": issue["key"],
                "severity": "MEDIUM",
                "reason": "0-point issue in sprint",
                "url": issue["url"],
            })

        est = issue["time_estimate"]
        logged = issue["time_logged"]
        if est and est > 0 and logged and logged > est * 1.5:
            pct = int((logged / est) * 100)
            findings.append({
                "agent": "estimation",
                "key": issue["key"],
                "severity": "MEDIUM",
                "reason": f"Time overrun: logged {pct}% of estimate",
                "url": issue["url"],
            })

        if issue["subtask_keys"] and pts is not None:
            subtask_total = sum(
                issue_map[sk]["story_points"] or 0
                for sk in issue["subtask_keys"]
                if sk in issue_map
            )
            if subtask_total > pts:
                findings.append({
                    "agent": "estimation",
                    "key": issue["key"],
                    "severity": "MEDIUM",
                    "reason": (
                        f"Subtask total ({subtask_total}pts) exceeds "
                        f"parent ({pts}pts)"
                    ),
                    "url": issue["url"],
                })

    return findings
