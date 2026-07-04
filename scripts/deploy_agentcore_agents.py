"""Build, push, and register the 6 AgentCore Runtimes for the sanity-report agents.

Prereqs: docker buildx, AWS credentials, and the 6 ECR repos + 6 per-agent IAM
roles already created by `terraform apply` in infra/ (see infra/agentcore.tf).
Naming convention this script assumes (matches infra/agentcore.tf):
  ECR repo:  {project}-agent-{name}
  IAM role:  {project}-agentcore-{name}-role

Usage (from repo root):
    python scripts/deploy_agentcore_agents.py

Prints the 6 resulting agentRuntimeArn values, pre-formatted to paste into
infra/terraform.tfvars as `agentcore_runtime_arns = { ... }` (bootstrap step
2 of the AgentCore migration).
"""
import json
import os
import subprocess
import sys

import boto3
from dotenv import load_dotenv

load_dotenv()

PROJECT = "jira-sanity-checker"  # must match infra/variables.tf's var.project default
REGION = os.environ.get("AWS_REGION", "us-east-1")
REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")

AGENTS = ["staleness", "estimation", "priority", "blocker", "commit", "report_composer"]

sts = boto3.client("sts", region_name=REGION)
ACCOUNT_ID = sts.get_caller_identity()["Account"]

secretsmanager = boto3.client("secretsmanager", region_name=REGION)
control = boto3.client("bedrock-agentcore-control", region_name=REGION)


def _ecr_repo_name(agent: str) -> str:
    return f"{PROJECT}-agent-{agent.replace('_', '-')}"


def _ecr_uri(agent: str) -> str:
    return f"{ACCOUNT_ID}.dkr.ecr.{REGION}.amazonaws.com/{_ecr_repo_name(agent)}:latest"


def _role_arn(agent: str) -> str:
    role_name = f"{PROJECT}-agentcore-{agent.replace('_', '-')}-role"
    return f"arn:aws:iam::{ACCOUNT_ID}:role/{role_name}"


def _environment_variables(agent: str) -> dict:
    env = {"AWS_REGION": REGION}
    if agent == "commit":
        try:
            secret_arn = secretsmanager.describe_secret(
                SecretId=f"{PROJECT}/github-token"
            )["ARN"]
            env["GITHUB_TOKEN_SECRET_ARN"] = secret_arn
        except secretsmanager.exceptions.ResourceNotFoundException:
            print(f"  warning: no {PROJECT}/github-token secret found — commit-agent will skip GitHub checks")
        github_repo = os.environ.get("GITHUB_REPO")
        if github_repo:
            env["GITHUB_REPO"] = github_repo
    return env


def build_and_push(agent: str) -> None:
    ecr_uri = _ecr_uri(agent)
    print(f"[{agent}] building {ecr_uri} ...")
    subprocess.run(
        [
            "docker", "build",
            "--platform", "linux/arm64",
            "--provenance=false", "--sbom=false",
            "-f", f"agentcore/{agent}/Dockerfile",
            "-t", ecr_uri,
            ".",
        ],
        cwd=REPO_ROOT,
        check=True,
    )
    print(f"[{agent}] pushing {ecr_uri} ...")
    subprocess.run(["docker", "push", ecr_uri], check=True)


def _runtime_name(agent: str) -> str:
    # agentRuntimeName only allows [a-zA-Z][a-zA-Z0-9_]{0,47} — no hyphens.
    return f"{agent}_agent"


def find_existing_runtime_id(name: str) -> str | None:
    paginator = control.get_paginator("list_agent_runtimes")
    for page in paginator.paginate():
        for runtime in page["agentRuntimes"]:
            if runtime["agentRuntimeName"] == name:
                return runtime["agentRuntimeId"]
    return None


def create_or_update_runtime(agent: str) -> str:
    name = _runtime_name(agent)
    ecr_uri = _ecr_uri(agent)
    role_arn = _role_arn(agent)
    env = _environment_variables(agent)
    existing_id = find_existing_runtime_id(name)

    if existing_id:
        print(f"[{agent}] updating existing runtime {existing_id} ...")
        resp = control.update_agent_runtime(
            agentRuntimeId=existing_id,
            agentRuntimeArtifact={"containerConfiguration": {"containerUri": ecr_uri}},
            roleArn=role_arn,
            networkConfiguration={"networkMode": "PUBLIC"},
            environmentVariables=env,
            lifecycleConfiguration={"idleRuntimeSessionTimeout": 300, "maxLifetime": 1800},
        )
    else:
        print(f"[{agent}] creating new runtime {name} ...")
        resp = control.create_agent_runtime(
            agentRuntimeName=name,
            agentRuntimeArtifact={"containerConfiguration": {"containerUri": ecr_uri}},
            roleArn=role_arn,
            networkConfiguration={"networkMode": "PUBLIC"},
            environmentVariables=env,
            lifecycleConfiguration={"idleRuntimeSessionTimeout": 300, "maxLifetime": 1800},
        )

    return resp["agentRuntimeArn"]


def main():
    arns = {}
    for agent in AGENTS:
        build_and_push(agent)
        arns[agent] = create_or_update_runtime(agent)

    print("\nAll 6 AgentCore Runtimes deployed. Paste into infra/terraform.tfvars:\n")
    print("agentcore_runtime_arns = {")
    for agent, arn in arns.items():
        print(f'  {agent} = "{arn}"')
    print("}")


if __name__ == "__main__":
    main()
