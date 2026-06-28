terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

resource "aws_iam_role" "lambda_role" {
  name = "jira-sanity-checker-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "jira-sanity-checker-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [var.jira_api_token_secret_arn]
      },
      {
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["ses:SendRawEmail"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_lambda_function" "jira_sanity_checker" {
  function_name = "jira-sanity-checker"
  role          = aws_iam_role.lambda_role.arn
  package_type  = "Image"
  image_uri     = var.ecr_image_uri
  timeout       = 300
  memory_size   = 512

  image_config {
    command = ["lambda_handler.handler"]
  }

  environment {
    variables = {
      JIRA_URL         = var.jira_url
      JIRA_EMAIL       = var.jira_email
      JIRA_PROJECT_KEY = var.project_key
      AWS_REGION       = var.aws_region
      EMAIL_FROM       = var.email_from
      EMAIL_RECIPIENTS = var.email_recipients
    }
  }
}

resource "aws_cloudwatch_event_rule" "nightly" {
  name                = "jira-sanity-checker-nightly"
  description         = "Trigger Jira Sanity Checker at 2 AM UTC"
  schedule_expression = var.schedule_expression
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.nightly.name
  target_id = "JiraSanityCheckerLambda"
  arn       = aws_lambda_function.jira_sanity_checker.arn

  input = jsonencode({
    project_key = var.project_key
    sprint_name = "Current Sprint"
  })
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.jira_sanity_checker.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.nightly.arn
}
