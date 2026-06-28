import sys
sys.path.insert(0, "/var/task/src")

from agents.report_composer import compose


def handler(event, context):
    findings = event["findings"]
    sprint_name = event.get("sprint_name", "Current Sprint")
    return {"report": compose(findings, sprint_name)}
