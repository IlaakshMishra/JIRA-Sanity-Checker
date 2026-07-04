import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ISSUES = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "sprint_issues.json").read_text()
)

sys.path.insert(0, str(REPO_ROOT / "src" / "agents"))

FINDING_AGENTS = ["staleness", "estimation", "priority", "blocker", "commit"]


def _load_agent_app(name: str):
    """Load agentcore/<name>/agent.py as its own module to avoid collisions
    between the 6 files that are all literally named agent.py."""
    path = REPO_ROOT / "agentcore" / name / "agent.py"
    spec = importlib.util.spec_from_file_location(f"agentcore_{name}_agent", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


@pytest.mark.parametrize("name", FINDING_AGENTS)
def test_ping(name):
    client = TestClient(_load_agent_app(name))
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


@pytest.mark.parametrize("name", ["staleness", "estimation", "priority", "blocker"])
def test_invocations_matches_underlying_function(name):
    module_name = f"{name}_agent"
    underlying = importlib.import_module(module_name)
    expected = underlying.run(FIXTURE_ISSUES)

    client = TestClient(_load_agent_app(name))
    resp = client.post("/invocations", json={"input": {"issues": FIXTURE_ISSUES}})

    assert resp.status_code == 200
    assert resp.json() == {"output": {"findings": expected}}


def test_commit_invocations_returns_empty_without_github_config(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN_SECRET_ARN", raising=False)
    monkeypatch.delenv("GITHUB_REPO", raising=False)

    client = TestClient(_load_agent_app("commit"))
    resp = client.post("/invocations", json={"input": {"issues": FIXTURE_ISSUES}})

    assert resp.status_code == 200
    assert resp.json() == {"output": {"findings": []}}


def test_ping_report_composer():
    client = TestClient(_load_agent_app("report_composer"))
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


def _bedrock_response(text: str):
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps({"content": [{"text": text}]}).encode()
    return {"body": mock_body}


def test_report_composer_invocations():
    module = importlib.import_module("report_composer")
    with patch.object(module, "boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_client.invoke_model.return_value = _bedrock_response("# Sprint Report\n\nAll clear.")
        mock_boto3.client.return_value = mock_client

        client = TestClient(_load_agent_app("report_composer"))
        resp = client.post(
            "/invocations",
            json={"input": {"findings": [], "sprint_name": "Sprint 42"}},
        )

    assert resp.status_code == 200
    assert resp.json() == {"output": {"report_markdown": "# Sprint Report\n\nAll clear."}}
