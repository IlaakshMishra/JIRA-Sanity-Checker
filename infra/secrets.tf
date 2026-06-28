resource "aws_secretsmanager_secret" "jira_api_token" {
  name                    = "${var.project}/jira-api-token"
  description             = "Atlassian API token for Jira read access"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "jira_api_token" {
  secret_id     = aws_secretsmanager_secret.jira_api_token.id
  secret_string = var.jira_api_token
}

resource "aws_secretsmanager_secret" "github_token" {
  name                    = "${var.project}/github-token"
  description             = "GitHub PAT for commit correlation (optional)"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "github_token" {
  secret_id     = aws_secretsmanager_secret.github_token.id
  secret_string = var.github_token
}
