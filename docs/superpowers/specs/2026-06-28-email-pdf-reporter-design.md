# Email PDF Reporter — Design Spec

**Date:** 2026-06-28  
**Replaces:** Teams/Slack webhook notifications (`src/notifier.py`)  
**Status:** Approved

---

## Goal

Replace Teams/Slack webhook notifications with an email containing:
- Plain text body (Markdown report as-is)
- HTML body (styled rendering of the same Markdown)
- PDF attachment (high-quality rendered report)

Email sent via AWS SES. No human approval gate — auto-sends always.

---

## Architecture

### New Modules

**`src/pdf_generator.py`**  
Single public function: `generate_pdf(report_md: str) -> bytes`

Pipeline:
1. `markdown` lib converts Markdown string → HTML string
2. Inject CSS (see Styling section) into `<style>` tag
3. `weasyprint.HTML(string=html).write_pdf()` → PDF bytes

**`src/notifier.py`** (rewritten)  
Single public function: `send_email_report(report_md: str, sprint_name: str) -> None`

Pipeline:
1. Call `generate_pdf(report_md)` → PDF bytes
2. Convert Markdown → HTML (reuse same conversion for HTML body)
3. Build `email.mime.multipart.MIMEMultipart("mixed")` with:
   - `MIMEText(report_md, "plain")` — plain text part
   - `MIMEText(html_body, "html")` — HTML part
   - `MIMEApplication(pdf_bytes, Name="sprint-health-{sprint_name}.pdf")` — PDF attachment
4. `boto3.client("ses", region_name=AWS_REGION).send_raw_email(RawMessage={"Data": msg.as_bytes()})`
5. Skip silently if `EMAIL_FROM` or `EMAIL_RECIPIENTS` unset

### Modified Files

**`src/main.py`**
- Remove `input()` approval gate
- Remove `post_to_teams()` / `post_to_slack()` calls
- Add `send_email_report(report, sprint_name)` call after `print(report)`

**`requirements.txt`**
```
weasyprint==62.3
markdown==3.6
```
(added alongside existing pinned deps)

**`Dockerfile`**
Add system packages before `pip install`:
```dockerfile
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*
```

**Lambda deploy:** must use container image (not zip) due to weasyprint system deps. `Dockerfile` already exists — Terraform Task 12 updated to use `aws_lambda_function` with `image_uri` instead of `filename`.

**`.env.example`**
```
EMAIL_FROM=jira-checker@yourco.com
EMAIL_RECIPIENTS=pm@yourco.com,eng@yourco.com
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `EMAIL_FROM` | Yes | — | Verified SES sender address |
| `EMAIL_RECIPIENTS` | Yes | — | Comma-separated recipient list |
| `AWS_REGION` | No | `us-east-1` | SES + Bedrock region (already exists) |

`EMAIL_FROM` must be a verified SES identity (address or domain). `EMAIL_RECIPIENTS` supports multiple addresses: `a@co.com,b@co.com`.

---

## Email Structure

**Subject:** `Sprint Health Report: {sprint_name}`  
**From:** `EMAIL_FROM`  
**To:** all addresses in `EMAIL_RECIPIENTS`  
**Parts:**
1. `text/plain` — raw Markdown (readable in any client)
2. `text/html` — styled HTML rendering
3. `application/pdf` attachment — `sprint-health-{sprint_name}.pdf`

---

## PDF Styling

Inline CSS in `pdf_generator.py`:
- Font: system sans-serif, 11pt body
- Page: A4, 2cm margins
- Severity badges: `HIGH` = `#dc2626` red, `MEDIUM` = `#d97706` amber, `LOW` = `#2563eb` blue
- Agent section headers: bold, subtle bottom border
- White background, dark text

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| `EMAIL_FROM` or `EMAIL_RECIPIENTS` unset | Skip silently (same as old webhook pattern) |
| SES send failure | `raise` — Lambda returns 500, CLI prints traceback |
| weasyprint render failure | `raise` — broken PDF attachment is worse than no email |
| Invalid recipient address | SES raises `MessageRejected` → propagates up |

---

## Data Flow

```
report_composer.compose() → Markdown string
         ↓
pdf_generator.generate_pdf() → PDF bytes
         ↓
notifier.send_email_report()
    ├── text/plain  (Markdown)
    ├── text/html   (styled HTML)
    └── PDF attachment
         ↓
boto3 SES send_raw_email()
```

---

## SES Prerequisites (outside codebase)

- Verify `EMAIL_FROM` address/domain in SES console
- If AWS account still in SES sandbox: verify each recipient address too, or request production access
- IAM role (Lambda) needs `ses:SendRawEmail` permission — add to `infra/main.tf` policy

---

## Files Changed

| File | Change |
|------|--------|
| `src/pdf_generator.py` | New |
| `src/notifier.py` | Rewritten — SES replaces webhooks |
| `src/main.py` | Remove gate + webhook calls; add `send_email_report()` |
| `requirements.txt` | Add `weasyprint==62.3`, `markdown==3.6` |
| `Dockerfile` | Add system deps for weasyprint |
| `.env.example` | Add `EMAIL_FROM`, `EMAIL_RECIPIENTS`; remove webhook vars |
| `infra/main.tf` | Switch Lambda to container image; add `ses:SendRawEmail` to IAM policy |
| Implementation plan Task 8 | Update to reflect new notifier design |
| Implementation plan Task 11 | Update Dockerfile steps |
| Implementation plan Task 12 | Update Terraform to container image deploy |
