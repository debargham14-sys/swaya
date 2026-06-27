output "api_base_url" {
  description = "Public API base URL (point the mobile app's API_BASE_URL here). e.g. /health, /v1/scans."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "ec2_public_dns" {
  description = "EC2 public DNS (direct, bypassing API Gateway — useful for debugging)."
  value       = aws_instance.api.public_dns
}

output "ec2_public_ip" {
  value = aws_instance.api.public_ip
}

output "dynamodb_tables" {
  description = "Provisioned DynamoDB table names."
  value       = [for t in aws_dynamodb_table.tables : t.name]
}

output "s3_bucket" {
  value = aws_s3_bucket.blobs.bucket
}

output "ecr_repository_url" {
  description = "Push the API image here before applying (see push_image.sh)."
  value       = aws_ecr_repository.api.repository_url
}

output "access_log_group" {
  description = "CloudWatch Logs group for per-request API Gateway access logs."
  value       = aws_cloudwatch_log_group.api_access.name
}
