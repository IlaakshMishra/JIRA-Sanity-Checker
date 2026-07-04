import json
import os
import secrets

import boto3


def _invoke(arn_env_var: str, payload: dict) -> dict:
    region = os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("bedrock-agentcore", region_name=region)

    response = client.invoke_agent_runtime(
        agentRuntimeArn=os.environ[arn_env_var],
        runtimeSessionId=secrets.token_hex(20),
        payload=json.dumps({"input": payload}),
        qualifier="DEFAULT",
    )
    body = json.loads(response["response"].read())
    return body["output"]


def staleness_run(issues: list[dict]) -> list[dict]:
    return _invoke("AGENTCORE_STALENESS_ARN", {"issues": issues})["findings"]


def estimation_run(issues: list[dict]) -> list[dict]:
    return _invoke("AGENTCORE_ESTIMATION_ARN", {"issues": issues})["findings"]


def priority_run(issues: list[dict]) -> list[dict]:
    return _invoke("AGENTCORE_PRIORITY_ARN", {"issues": issues})["findings"]


def blocker_run(issues: list[dict]) -> list[dict]:
    return _invoke("AGENTCORE_BLOCKER_ARN", {"issues": issues})["findings"]


def commit_run(issues: list[dict]) -> list[dict]:
    return _invoke("AGENTCORE_COMMIT_ARN", {"issues": issues})["findings"]


def report_composer_compose(findings: list[dict], sprint_name: str) -> str:
    output = _invoke(
        "AGENTCORE_REPORT_COMPOSER_ARN",
        {"findings": findings, "sprint_name": sprint_name},
    )
    return output["report_markdown"]
