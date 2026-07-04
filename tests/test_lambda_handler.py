from unittest.mock import patch

import lambda_handler


@patch("lambda_handler.run_ppt")
@patch("lambda_handler.run")
def test_handler_dispatches_ppt_mode(mock_run, mock_run_ppt):
    mock_run_ppt.return_value = b"BYTES"

    result = lambda_handler.handler(
        {"mode": "ppt", "project_key": "ENG", "sprint_name": "Sprint 42"}, None
    )

    mock_run_ppt.assert_called_once_with("ENG", "Sprint 42", dry_run=False)
    mock_run.assert_not_called()
    assert result["statusCode"] == 200


@patch("lambda_handler.run_ppt")
@patch("lambda_handler.run")
def test_handler_defaults_to_sanity_mode(mock_run, mock_run_ppt):
    mock_run.return_value = []

    result = lambda_handler.handler(
        {"project_key": "ENG", "sprint_name": "Sprint 42"}, None
    )

    mock_run.assert_called_once_with("ENG", "Sprint 42", dry_run=False)
    mock_run_ppt.assert_not_called()
    assert result["statusCode"] == 200


@patch("lambda_handler.run_ppt")
@patch("lambda_handler.run")
def test_handler_returns_500_on_exception(mock_run, mock_run_ppt):
    mock_run.side_effect = RuntimeError("boom")

    result = lambda_handler.handler(
        {"project_key": "ENG", "sprint_name": "Sprint 42"}, None
    )

    assert result["statusCode"] == 500
