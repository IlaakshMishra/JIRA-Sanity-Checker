from unittest.mock import MagicMock, patch


def test_send_ppt_email_skips_when_env_unset(monkeypatch):
    from notifier import send_ppt_email

    monkeypatch.delenv("EMAIL_FROM", raising=False)
    monkeypatch.delenv("EMAIL_RECIPIENTS", raising=False)

    with patch("notifier.boto3") as mock_boto3:
        send_ppt_email(b"fake-bytes", "Sprint 42")
        mock_boto3.client.assert_not_called()


@patch("notifier.boto3")
def test_send_ppt_email_sends_when_configured(mock_boto3, monkeypatch):
    import base64
    from notifier import send_ppt_email

    monkeypatch.setenv("EMAIL_FROM", "sender@company.com")
    monkeypatch.setenv("EMAIL_RECIPIENTS", "a@company.com,b@company.com")

    mock_client = MagicMock()
    mock_boto3.client.return_value = mock_client

    pptx_data = b"fake-bytes"
    send_ppt_email(pptx_data, "Sprint 42")

    mock_client.send_raw_email.assert_called_once()
    call_kwargs = mock_client.send_raw_email.call_args.kwargs
    assert call_kwargs["Source"] == "sender@company.com"
    assert call_kwargs["Destinations"] == ["a@company.com", "b@company.com"]
    # MIME base64-encodes binary attachments, so check for the encoded version
    assert base64.b64encode(pptx_data) in call_kwargs["RawMessage"]["Data"]
