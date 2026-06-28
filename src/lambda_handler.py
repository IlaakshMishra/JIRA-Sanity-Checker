import json
import os
import traceback

from main import run

PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "ENG")


def handler(event: dict, context) -> dict:
    project_key = event.get("project_key", PROJECT_KEY)
    sprint_name = event.get("sprint_name", "Current Sprint")

    try:
        findings = run(project_key, sprint_name, dry_run=False)
        return {
            "statusCode": 200,
            "body": json.dumps({
                "findings_count": len(findings),
                "findings": findings,
            }),
        }
    except Exception as exc:
        traceback.print_exc()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(exc)}),
        }
