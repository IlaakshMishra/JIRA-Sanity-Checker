resource "aws_lambda_function" "app" {
  function_name = var.project
  role          = aws_iam_role.lambda_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.app.repository_url}:latest"
  architectures = ["arm64"]
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
      JIRA_IGNORE_LABEL         = var.jira_ignore_label
      JIRA_STALENESS_THRESHOLD_DAYS = var.jira_staleness_threshold_days
      JIRA_STORY_POINTS_FIELD   = var.jira_story_points_field
      EMAIL_FROM                = var.email_from
      EMAIL_RECIPIENTS          = var.email_recipients
      GITHUB_REPO               = var.github_repo
      GITHUB_TOKEN_SECRET_ARN   = aws_secretsmanager_secret.github_token.arn

      AGENT_BACKEND                 = var.agent_backend
      AGENTCORE_STALENESS_ARN       = lookup(var.agentcore_runtime_arns, "staleness", "")
      AGENTCORE_ESTIMATION_ARN      = lookup(var.agentcore_runtime_arns, "estimation", "")
      AGENTCORE_PRIORITY_ARN        = lookup(var.agentcore_runtime_arns, "priority", "")
      AGENTCORE_BLOCKER_ARN         = lookup(var.agentcore_runtime_arns, "blocker", "")
      AGENTCORE_COMMIT_ARN          = lookup(var.agentcore_runtime_arns, "commit", "")
      AGENTCORE_REPORT_COMPOSER_ARN = lookup(var.agentcore_runtime_arns, "report_composer", "")
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

resource "aws_cloudwatch_event_rule" "ppt_weekly" {
  name                = "${var.project}-ppt-weekly"
  description         = "Jira Sanity Checker — weekly sprint summary PPT"
  schedule_expression = var.ppt_schedule_expression
}

resource "aws_cloudwatch_event_target" "lambda_ppt" {
  rule      = aws_cloudwatch_event_rule.ppt_weekly.name
  target_id = "JiraSanityCheckerPPTLambda"
  arn       = aws_lambda_function.app.arn

  input = jsonencode({
    mode        = "ppt"
    project_key = var.jira_project_key
    sprint_name = "Current Sprint"
  })
}

resource "aws_lambda_permission" "allow_eventbridge_ppt" {
  statement_id  = "AllowEventBridgeInvokePPT"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.app.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ppt_weekly.arn
}
