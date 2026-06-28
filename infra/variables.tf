variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "ecr_image_uri" {
  type        = string
  description = "ECR container image URI (e.g. 123456789.dkr.ecr.us-east-1.amazonaws.com/jira-sanity-checker:latest)"
}

variable "jira_url" {
  type = string
}

variable "jira_email" {
  type = string
}

variable "jira_api_token_secret_arn" {
  type        = string
  description = "ARN of Secrets Manager secret containing the Jira API token"
}

variable "email_from" {
  type        = string
  description = "Verified SES sender address"
}

variable "email_recipients" {
  type        = string
  description = "Comma-separated SES recipient addresses"
}

variable "project_key" {
  type    = string
  default = "ENG"
}

variable "schedule_expression" {
  type    = string
  default = "cron(0 2 * * ? *)"
}
