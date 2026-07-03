variable "aws_region" {
  default = "us-east-1"
}

variable "project" {
  default = "jira-sanity-checker"
}

variable "jira_url" {
  type        = string
  description = "https://yourcompany.atlassian.net"
}

variable "jira_email" {
  type        = string
  description = "Atlassian account email"
}

variable "jira_api_token" {
  type        = string
  sensitive   = true
  description = "Atlassian API token"
}

variable "jira_project_key" {
  type    = string
  default = "ENG"
}

variable "jira_ignore_label" {
  type        = string
  default     = "sanity-ignore"
  description = "Label that excludes a ticket from all agent checks"
}

variable "jira_staleness_threshold_days" {
  type        = number
  default     = 3
  description = "Days since update/comment before an in-progress ticket is flagged stale"
}

variable "jira_story_points_field" {
  type        = string
  default     = "customfield_10016"
  description = "Custom field ID for story points (varies by Jira instance)"
}

variable "email_from" {
  type        = string
  description = "Verified SES sender address"
}

variable "email_recipients" {
  type        = string
  description = "Comma-separated SES recipient addresses"
}

variable "github_token" {
  type        = string
  sensitive   = true
  default     = ""
  description = "GitHub PAT for commit correlation (optional)"
}

variable "github_repo" {
  type    = string
  default = ""
}

variable "schedule_expression" {
  type    = string
  default = "cron(0 2 * * ? *)"
}
