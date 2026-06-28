output "lambda_function_arn" {
  value = aws_lambda_function.jira_sanity_checker.arn
}

output "lambda_function_name" {
  value = aws_lambda_function.jira_sanity_checker.function_name
}

output "eventbridge_rule_arn" {
  value = aws_cloudwatch_event_rule.nightly.arn
}
