# Observability for the HTTP API: CloudWatch access logs + an optional 5xx alarm.

# Per-request access logs (queryable in CloudWatch Logs Insights). 14-day retention
# keeps cost negligible.
resource "aws_cloudwatch_log_group" "api_access" {
  name              = "/aws/apigateway/${var.project}-api"
  retention_in_days = 14
  tags              = local.tags
}

# Optional: email alert when 5xx errors spike. Set alarm_email to enable (creates
# an SNS topic — confirm the subscription email AWS sends you).
resource "aws_sns_topic" "alerts" {
  count = var.alarm_email != "" ? 1 : 0
  name  = "${var.project}-alerts"
  tags  = local.tags
}

resource "aws_sns_topic_subscription" "alerts_email" {
  count     = var.alarm_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alerts[0].arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  count               = var.alarm_email != "" ? 1 : 0
  alarm_name          = "${var.project}-api-5xx"
  alarm_description   = "More than 5 API Gateway 5xx responses in 5 minutes."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "5xx" # HTTP API metric (AWS/ApiGateway)
  namespace           = "AWS/ApiGateway"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  dimensions = {
    ApiId = aws_apigatewayv2_api.api.id
  }
  alarm_actions = [aws_sns_topic.alerts[0].arn]
  ok_actions    = [aws_sns_topic.alerts[0].arn]
  tags          = local.tags
}
