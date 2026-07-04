import json
import os

import boto3

MODEL_ID = "us.anthropic.claude-sonnet-4-5"

SYSTEM = """You are a senior engineering project manager.
You receive sprint statistics and raw ticket data.
Return STRICT JSON only, no prose, no markdown fences, matching exactly:
{"highlights": [string, ...], "risks": [string, ...], "next_steps": [string, ...]}
Each list has at most 5 items, one short sentence each."""

_EMPTY = {"highlights": [], "risks": [], "next_steps": []}


def generate(stats: dict, issues: list[dict]) -> dict:
    region = os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("bedrock-runtime", region_name=region)

    payload = {
        "model": MODEL_ID,
        "max_tokens": 800,
        "system": SYSTEM,
        "messages": [{
            "role": "user",
            "content": (
                f"Stats JSON:\n{json.dumps(stats, indent=2)}\n\n"
                f"Issues JSON:\n{json.dumps(issues, indent=2)}"
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
    text = body["content"][0]["text"]

    try:
        narrative = json.loads(text)
    except json.JSONDecodeError:
        return dict(_EMPTY)

    if not isinstance(narrative, dict):
        return dict(_EMPTY)

    return {
        "highlights": list(narrative.get("highlights") or [])[:5],
        "risks": list(narrative.get("risks") or [])[:5],
        "next_steps": list(narrative.get("next_steps") or [])[:5],
    }
