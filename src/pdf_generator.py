import markdown
import weasyprint

_CSS = """
@page {
    size: A4;
    margin: 2cm;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 11pt;
    color: #1a1a1a;
    background: #ffffff;
    line-height: 1.5;
}

h1 {
    font-size: 18pt;
    border-bottom: 2px solid #e5e7eb;
    padding-bottom: 8px;
    margin-bottom: 16px;
}

h2 {
    font-size: 13pt;
    color: #374151;
    border-bottom: 1px solid #e5e7eb;
    padding-bottom: 4px;
    margin-top: 20px;
}

h3 {
    font-size: 11pt;
    color: #374151;
    margin-top: 14px;
}

ul {
    padding-left: 20px;
}

li {
    margin-bottom: 6px;
}

strong {
    font-weight: 600;
}

code {
    font-family: "Menlo", "Courier New", monospace;
    font-size: 9pt;
    background: #f3f4f6;
    padding: 1px 4px;
    border-radius: 3px;
}

.high   { color: #dc2626; font-weight: 600; }
.medium { color: #d97706; font-weight: 600; }
.low    { color: #2563eb; font-weight: 600; }

p { margin: 6px 0; }
"""

_SEVERITY_BADGES = {
    "HIGH": '<span class="high">HIGH</span>',
    "MEDIUM": '<span class="medium">MEDIUM</span>',
    "LOW": '<span class="low">LOW</span>',
}


def generate_pdf(report_md: str) -> bytes:
    html_body = markdown.markdown(report_md, extensions=["tables", "fenced_code"])

    for word, badge in _SEVERITY_BADGES.items():
        html_body = html_body.replace(f"**{word}**", badge)
        html_body = html_body.replace(word, badge)

    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>{_CSS}</style>
</head>
<body>
{html_body}
</body>
</html>"""

    return weasyprint.HTML(string=full_html).write_pdf()
