locals {
  # One entry per AgentCore-hosted agent. extra_statements grants only the
  # IAM actions that specific agent's code actually needs (least-priv):
  # the 4 deterministic finding-agents get nothing beyond logs + ECR pull;
  # commit needs the GitHub secret; report_composer needs Bedrock.
  agentcore_agents = {
    staleness = {
      extra_statements = []
    }
    estimation = {
      extra_statements = []
    }
    priority = {
      extra_statements = []
    }
    blocker = {
      extra_statements = []
    }
    commit = {
      extra_statements = [
        {
          Effect   = "Allow"
          Action   = ["secretsmanager:GetSecretValue"]
          Resource = [aws_secretsmanager_secret.github_token.arn]
        }
      ]
    }
    report_composer = {
      extra_statements = [
        {
          Effect = "Allow"
          Action = ["bedrock:InvokeModel"]
          Resource = [
            "arn:aws:bedrock:*::foundation-model/*",
            "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/*",
          ]
        }
      ]
    }
  }
}

resource "aws_ecr_repository" "agentcore" {
  for_each             = local.agentcore_agents
  name                 = "${var.project}-agent-${replace(each.key, "_", "-")}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_iam_role" "agentcore" {
  for_each = local.agentcore_agents
  name     = "${var.project}-agentcore-${replace(each.key, "_", "-")}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "bedrock-agentcore.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "agentcore" {
  for_each = local.agentcore_agents
  name     = "${var.project}-agentcore-${replace(each.key, "_", "-")}-policy"
  role     = aws_iam_role.agentcore[each.key].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"
      },
      {
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability",
        ]
        Resource = aws_ecr_repository.agentcore[each.key].arn
      },
    ], each.value.extra_statements)
  })
}
