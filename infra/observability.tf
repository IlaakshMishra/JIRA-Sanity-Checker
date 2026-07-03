resource "aws_cloudwatch_log_group" "app" {
  name              = "/aws/lambda/${var.project}"
  retention_in_days = 30
}

resource "aws_xray_group" "app" {
  group_name        = var.project
  filter_expression = "annotation.project = \"${var.project}\""
}

resource "aws_cloudwatch_log_metric_filter" "errors" {
  name           = "${var.project}-errors"
  log_group_name = aws_cloudwatch_log_group.app.name
  pattern        = "ERROR"

  metric_transformation {
    name          = "errors"
    namespace     = "JiraSanityChecker"
    value         = "1"
    default_value = "0"
    unit          = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "invocations" {
  name           = "${var.project}-invocations"
  log_group_name = aws_cloudwatch_log_group.app.name
  pattern        = "handler invoked"

  metric_transformation {
    name          = "invocations"
    namespace     = "JiraSanityChecker"
    value         = "1"
    default_value = "0"
    unit          = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "email_sent" {
  name           = "${var.project}-email-sent"
  log_group_name = aws_cloudwatch_log_group.app.name
  pattern        = "email sent"

  metric_transformation {
    name          = "email_sent"
    namespace     = "JiraSanityChecker"
    value         = "1"
    default_value = "0"
    unit          = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "${var.project}-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "errors"
  namespace           = "JiraSanityChecker"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Jira Sanity Checker logged errors in the last 5 minutes"
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_dashboard" "app" {
  dashboard_name = var.project

  dashboard_body = jsonencode({
    widgets = [
      {
        type       = "text"
        x          = 0
        y          = 0
        width      = 24
        height     = 1
        properties = { markdown = "# Jira Sanity Checker — Observability" }
      },
      {
        type   = "metric"
        x      = 0
        y      = 1
        width  = 8
        height = 6
        properties = {
          title   = "Invocations"
          region  = var.aws_region
          view    = "timeSeries"
          stat    = "Sum"
          period  = 86400
          metrics = [["JiraSanityChecker", "invocations"]]
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 1
        width  = 8
        height = 6
        properties = {
          title   = "Errors"
          region  = var.aws_region
          view    = "timeSeries"
          stat    = "Sum"
          period  = 86400
          metrics = [["JiraSanityChecker", "errors", { color = "#d62728" }]]
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 1
        width  = 8
        height = 6
        properties = {
          title   = "Emails Sent"
          region  = var.aws_region
          view    = "timeSeries"
          stat    = "Sum"
          period  = 86400
          metrics = [["JiraSanityChecker", "email_sent"]]
        }
      },
      {
        type   = "log"
        x      = 0
        y      = 7
        width  = 24
        height = 6
        properties = {
          title  = "Recent Logs"
          region = var.aws_region
          view   = "table"
          query  = "SOURCE '/aws/lambda/${var.project}' | fields @timestamp, @message | sort @timestamp desc | limit 50"
        }
      },
      {
        type   = "alarm"
        x      = 0
        y      = 13
        width  = 24
        height = 3
        properties = {
          title  = "Alarms"
          alarms = [aws_cloudwatch_metric_alarm.errors.arn]
        }
      }
    ]
  })
}
