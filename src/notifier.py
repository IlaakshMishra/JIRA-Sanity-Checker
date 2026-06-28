import os
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import boto3
import markdown

from pdf_generator import generate_pdf


def send_email_report(report_md: str, sprint_name: str) -> None:
    sender = os.environ.get("EMAIL_FROM")
    recipients_raw = os.environ.get("EMAIL_RECIPIENTS")
    if not sender or not recipients_raw:
        return

    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
    region = os.environ.get("AWS_REGION", "us-east-1")

    html_body = markdown.markdown(report_md, extensions=["tables", "fenced_code"])
    pdf_bytes = generate_pdf(report_md)
    safe_name = sprint_name.replace(" ", "-").replace("/", "-")

    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"Sprint Health Report: {sprint_name}"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(report_md, "plain"))
    alt.attach(MIMEText(html_body, "html"))
    msg.attach(alt)

    attachment = MIMEApplication(pdf_bytes, Name=f"sprint-health-{safe_name}.pdf")
    attachment["Content-Disposition"] = f'attachment; filename="sprint-health-{safe_name}.pdf"'
    msg.attach(attachment)

    client = boto3.client("ses", region_name=region)
    client.send_raw_email(
        Source=sender,
        Destinations=recipients,
        RawMessage={"Data": msg.as_bytes()},
    )
