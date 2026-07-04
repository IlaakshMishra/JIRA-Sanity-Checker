import json
import os

import boto3

MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

SYSTEM = """You are a senior engineering project manager.
You receive structured findings from sprint health agents.
Write a concise, actionable sprint health report in Markdown.
Group findings by severity (HIGH → MEDIUM → LOW).
For each issue, write one bullet with: ticket key, reason, and
a specific suggested action. Max 400 words. No fluff."""


def compose(all_findings: list[dict], sprint_name: str) -> str:
    region = os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("bedrock-runtime", region_name=region)

    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "system": SYSTEM,
        "messages": [{
            "role": "user",
            "content": (
                f"Sprint: {sprint_name}\n\n"
                f"Findings JSON:\n{json.dumps(all_findings, indent=2)}"
            ),
        }],
    }
    resp = client.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps(payload),
        contentType="application/json",
        accept="application/json",
    )
    body = json.loads(resp["body"].read())
    return body["content"][0]["text"]
