import json
import logging
import os

import boto3

logger = logging.getLogger(__name__)

MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

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
        "anthropic_version": "bedrock-2023-05-31",
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

    try:
        resp = client.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps(payload),
            contentType="application/json",
            accept="application/json",
        )
        body = json.loads(resp["body"].read())
        text = body["content"][0]["text"].strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        narrative = json.loads(text.strip())
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        logger.warning("Parse failure in generate(); falling back to empty narrative")
        return dict(_EMPTY)
    except Exception as e:
        logger.warning(f"Bedrock invoke_model failure in generate(); falling back to empty narrative: {e}")
        return dict(_EMPTY)

    if not isinstance(narrative, dict):
        return dict(_EMPTY)

    def _extract_list(value):
        """Extract a list from a value, defaulting to empty list if not a list."""
        if isinstance(value, list):
            return value
        return []

    return {
        "highlights": _extract_list(narrative.get("highlights"))[:5],
        "risks": _extract_list(narrative.get("risks"))[:5],
        "next_steps": _extract_list(narrative.get("next_steps"))[:5],
    }
