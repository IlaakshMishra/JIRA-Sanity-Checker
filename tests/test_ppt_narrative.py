import json
from unittest.mock import MagicMock, patch


def _bedrock_response(text: str):
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps({
        "content": [{"text": text}]
    }).encode()
    return {"body": mock_body}


@patch("agents.ppt_narrative.boto3")
def test_generate_parses_valid_json(mock_boto3):
    from agents.ppt_narrative import generate

    mock_client = MagicMock()
    mock_client.invoke_model.return_value = _bedrock_response(
        json.dumps({
            "highlights": ["Shipped SSO"],
            "risks": ["DB migration blocked"],
            "next_steps": ["Unblock ENG-9"],
        })
    )
    mock_boto3.client.return_value = mock_client

    result = generate({"total_issues": 1}, [])

    assert result == {
        "highlights": ["Shipped SSO"],
        "risks": ["DB migration blocked"],
        "next_steps": ["Unblock ENG-9"],
    }


@patch("agents.ppt_narrative.boto3")
def test_generate_falls_back_on_malformed_json(mock_boto3):
    from agents.ppt_narrative import generate

    mock_client = MagicMock()
    mock_client.invoke_model.return_value = _bedrock_response("not valid json")
    mock_boto3.client.return_value = mock_client

    result = generate({"total_issues": 1}, [])

    assert result == {"highlights": [], "risks": [], "next_steps": []}


@patch("agents.ppt_narrative.boto3")
def test_generate_caps_lists_at_five_items(mock_boto3):
    from agents.ppt_narrative import generate

    mock_client = MagicMock()
    mock_client.invoke_model.return_value = _bedrock_response(
        json.dumps({
            "highlights": [f"h{i}" for i in range(10)],
            "risks": [],
            "next_steps": [],
        })
    )
    mock_boto3.client.return_value = mock_client

    result = generate({"total_issues": 1}, [])

    assert len(result["highlights"]) == 5
