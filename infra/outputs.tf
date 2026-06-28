output "lambda_arn" {
  value       = aws_lambda_function.app.arn
  description = "Lambda function ARN"
}

output "ecr_repository_url" {
  value       = aws_ecr_repository.app.repository_url
  description = "Push container image here before applying Lambda"
}

output "eventbridge_rule_arn" {
  value = aws_cloudwatch_event_rule.nightly.arn
}

output "dashboard_url" {
  value       = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.app.dashboard_name}"
  description = "CloudWatch observability dashboard"
}

output "jira_token_secret_arn" {
  value = aws_secretsmanager_secret.jira_api_token.arn
}
