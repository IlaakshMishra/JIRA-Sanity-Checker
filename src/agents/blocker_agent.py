COMMENT_STALE_DAYS = 3
MAX_CHAIN_DEPTH = 2


def run(issues: list[dict]) -> list[dict]:
    issue_map = {i["key"]: i for i in issues}
    findings = []

    for issue in issues:
        if not issue["is_blocked"]:
            continue

        if issue["days_since_last_comment"] >= COMMENT_STALE_DAYS:
            findings.append({
                "agent": "blocker",
                "key": issue["key"],
                "severity": "HIGH",
                "reason": (
                    f"Blocked for {issue['days_since_last_comment']}d "
                    f"with no comment update"
                ),
                "url": issue["url"],
            })

        if not issue["has_escalation_link"]:
            findings.append({
                "agent": "blocker",
                "key": issue["key"],
                "severity": "MEDIUM",
                "reason": "Blocked with no escalation ticket linked",
                "url": issue["url"],
            })

    findings.extend(_find_deep_chains(issues, issue_map))
    return findings


def _chain_depth(start_key: str, issue_map: dict, visited: set | None = None) -> int:
    if visited is None:
        visited = set()
    if start_key in visited or start_key not in issue_map:
        return 0
    visited.add(start_key)
    issue = issue_map[start_key]
    if not issue["blocking_chain_keys"]:
        return 1
    return 1 + max(
        _chain_depth(k, issue_map, visited)
        for k in issue["blocking_chain_keys"]
    )


def _find_deep_chains(issues: list[dict], issue_map: dict) -> list[dict]:
    reported = set()
    findings = []
    for issue in issues:
        if not issue["is_blocked"]:
            continue
        depth = _chain_depth(issue["key"], issue_map)
        if depth > MAX_CHAIN_DEPTH and issue["key"] not in reported:
            reported.add(issue["key"])
            findings.append({
                "agent": "blocker",
                "key": issue["key"],
                "severity": "HIGH",
                "reason": f"Blocking chain depth {depth} (max: {MAX_CHAIN_DEPTH})",
                "url": issue["url"],
            })
    return findings
