resource "aws_lambda_function" "app" {
  function_name = var.project
  role          = aws_iam_role.lambda_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.app.repository_url}:latest"
  timeout       = 300
  memory_size   = 512

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      JIRA_URL                  = var.jira_url
      JIRA_EMAIL                = var.jira_email
      JIRA_API_TOKEN_SECRET_ARN = aws_secretsmanager_secret.jira_api_token.arn
      JIRA_PROJECT_KEY          = var.jira_project_key
      EMAIL_FROM                = var.email_from
      EMAIL_RECIPIENTS          = var.email_recipients
      GITHUB_REPO               = var.github_repo
      AWS_REGION                = var.aws_region
    }
  }
}

resource "aws_cloudwatch_event_rule" "nightly" {
  name                = "${var.project}-nightly"
  description         = "Jira Sanity Checker — nightly sprint health check"
  schedule_expression = var.schedule_expression
}

resource "aws_cloudwatch_event_target" "lambda" {
  rule      = aws_cloudwatch_event_rule.nightly.name
  target_id = "JiraSanityCheckerLambda"
  arn       = aws_lambda_function.app.arn

  input = jsonencode({
    project_key = var.jira_project_key
    sprint_name = "Current Sprint"
  })
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.app.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.nightly.arn
}
