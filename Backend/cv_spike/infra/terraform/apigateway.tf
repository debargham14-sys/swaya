# HTTP API (API Gateway v2) fronting the EC2 backend via a public HTTP_PROXY
# integration. Every method/path is forwarded to uvicorn on :8000.
resource "aws_apigatewayv2_api" "api" {
  name          = "${var.project}-api"
  protocol_type = "HTTP"
  tags          = local.tags

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["*"]
    allow_headers = ["*"]
  }
}

resource "aws_apigatewayv2_integration" "proxy" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "ANY"
  integration_uri        = "http://${aws_instance.api.public_dns}:8000/{proxy}"
  payload_format_version = "1.0"
}

resource "aws_apigatewayv2_integration" "root" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "ANY"
  integration_uri        = "http://${aws_instance.api.public_dns}:8000/"
  payload_format_version = "1.0"
}

resource "aws_apigatewayv2_route" "proxy" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.proxy.id}"
}

resource "aws_apigatewayv2_route" "root" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "ANY /"
  target    = "integrations/${aws_apigatewayv2_integration.root.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true
  tags        = local.tags

  # Per-request JSON access logs. $context.path is the real request path (e.g.
  # /v1/scans) — the gateway routes everything via ANY /{proxy+}, so the path
  # field is what lets you break traffic down by endpoint in Logs Insights.
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access.arn
    format = jsonencode({
      requestId          = "$context.requestId"
      ip                 = "$context.identity.sourceIp"
      requestTime        = "$context.requestTime"
      httpMethod         = "$context.httpMethod"
      path               = "$context.path"
      routeKey           = "$context.routeKey"
      status             = "$context.status"
      protocol           = "$context.protocol"
      responseLength     = "$context.responseLength"
      responseLatency    = "$context.responseLatency"
      integrationLatency = "$context.integrationLatency"
      integrationStatus  = "$context.integrationStatus"
      integrationError   = "$context.integrationErrorMessage"
    })
  }

  # Per-route CloudWatch metrics (Count / Latency / 4xx / 5xx broken out).
  # Throttle limits MUST be set explicitly — omitting them makes the provider
  # send 0/0, which API Gateway reads as "throttle everything" (429 on all
  # requests). These generous values are effectively no-op for a beta.
  default_route_settings {
    detailed_metrics_enabled = true
    throttling_rate_limit    = 1000
    throttling_burst_limit   = 2000
  }
}
