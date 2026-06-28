import sys
sys.path.insert(0, "/var/task/src")

from agents.blocker_agent import run


def handler(event, context):
    issues = event.get("issues", [])
    return {"findings": run(issues)}
