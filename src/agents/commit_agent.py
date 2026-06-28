import os
import requests


def run(issues: list[dict]) -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO")
    if not token or not repo:
        return []

    prs = _fetch_prs(token, repo)
    branches = _fetch_branches(token, repo)
    return _correlate(issues, prs, branches)


def _fetch_prs(token: str, repo: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    resp = requests.get(
        f"https://api.github.com/repos/{repo}/pulls",
        params={"state": "all", "per_page": 100},
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_branches(token: str, repo: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    resp = requests.get(
        f"https://api.github.com/repos/{repo}/git/refs/heads",
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _pr_mentions(pr: dict, issue_key: str) -> bool:
    key_lower = issue_key.lower()
    return (
        key_lower in (pr.get("title") or "").lower()
        or key_lower in (pr.get("body") or "").lower()
        or key_lower in (pr.get("head", {}).get("ref") or "").lower()
    )


def _branch_mentions(branch: dict, issue_key: str) -> bool:
    ref = branch.get("ref", "")
    return issue_key.lower() in ref.lower()


def _correlate(issues: list[dict], prs: list[dict], branches: list[dict]) -> list[dict]:
    findings = []
    done_statuses = {"Done", "Closed", "Resolved"}

    for issue in issues:
        key = issue["key"]
        matching_prs = [pr for pr in prs if _pr_mentions(pr, key)]
        matching_branches = [b for b in branches if _branch_mentions(b, key)]

        if issue["status"] in done_statuses and not matching_prs and not matching_branches:
            findings.append({
                "agent": "commit",
                "key": key,
                "severity": "MEDIUM",
                "reason": "Ticket closed but no PR or branch found referencing it",
                "url": issue["url"],
            })

        for pr in matching_prs:
            if pr.get("merged_at") and issue["status"] not in done_statuses:
                findings.append({
                    "agent": "commit",
                    "key": key,
                    "severity": "HIGH",
                    "reason": f"PR merged ({pr['head']['ref']}) but ticket still '{issue['status']}'",
                    "url": issue["url"],
                })
                break

    return findings
