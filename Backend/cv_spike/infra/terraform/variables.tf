variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Name prefix + tag applied to every resource."
  type        = string
  default     = "swaya-dsv"
}

variable "dynamo_table_prefix" {
  description = <<-EOT
    Prefix for the four DynamoDB tables. MUST match DYNAMO_TABLE_PREFIX in the API
    (default "dsv" -> tables dsv_scans, dsv_calibration, dsv_vest_scans,
    dsv_vest_calibration). The same value is injected into the EC2 container.
  EOT
  type        = string
  default     = "dsv"
}

variable "s3_bucket_name" {
  description = "Globally-unique S3 bucket for scan photos + bundle ZIPs."
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type. Photo-only API (no torch) — t3.medium is a safe default."
  type        = string
  default     = "t3.medium"
}

variable "key_name" {
  description = "Existing EC2 key pair name for SSH. Empty = no SSH key attached."
  type        = string
  default     = ""
}

variable "ssh_ingress_cidr" {
  description = "CIDR allowed to SSH (port 22). Set to your IP/32; default is locked shut."
  type        = string
  default     = "127.0.0.1/32"
}

variable "api_ingress_cidr" {
  description = <<-EOT
    CIDR allowed to reach the app port (8000). API Gateway HTTP_PROXY calls the
    instance from the public internet, so this defaults to open. Lock down with a
    VPC Link + private ALB for production (see README).
  EOT
  type        = string
  default     = "0.0.0.0/0"
}

variable "image_tag" {
  description = <<-EOT
    ECR image tag the EC2 box pulls (built + pushed via push_image.sh). Bump this
    (or re-push "latest") to deploy a new build; with user_data_replace_on_change
    the instance re-bootstraps on the next apply.
  EOT
  type        = string
  default     = "latest"
}

variable "auth_required" {
  description = <<-EOT
    Inject AUTH_REQUIRED into the API container. "0" = open (test), "1" = require
    Firebase-authenticated requests (also set firebase_ssm_parameter before flipping on).
  EOT
  type        = string
  default     = "0"
}

variable "alarm_email" {
  description = <<-EOT
    Email to notify when API Gateway 5xx errors spike (>5 in 5 min). Empty = no
    alarm/SNS created. When set, confirm the subscription email AWS sends you.
  EOT
  type        = string
  default     = ""
}

variable "firebase_project_id" {
  description = <<-EOT
    Firebase project id (e.g. "swayastudio"). Injected as FIREBASE_PROJECT_ID so
    the API can verify incoming ID tokens using Google's public certs — no
    service-account secret needed for verification. Set auth_required="1" to
    enforce it. Empty = don't configure.
  EOT
  type        = string
  default     = ""
}

variable "firebase_ssm_parameter" {
  description = <<-EOT
    Name of an SSM Parameter Store SecureString holding the Firebase service-account
    JSON (must live under /<project>/...). The instance reads it at boot and injects
    FIREBASE_SERVICE_ACCOUNT_JSON. Create it once, out-of-band, so the secret never
    enters Terraform state:
      aws ssm put-parameter --type SecureString \
        --name /swaya-dsv/firebase-credentials \
        --value file://serviceAccount.json
    Empty = don't wire Firebase creds.
  EOT
  type        = string
  default     = ""
}

variable "enable_fcm_wif" {
  description = <<-EOT
    Enable Workload Identity Federation for sending FCM push notifications. When
    true, the instance role impersonates the Firebase Admin SA via the WIF config
    at infra/terraform/wif/firebase-wif.json (non-secret) — no downloaded key and
    no org-policy exception needed. The container reads it via
    GOOGLE_APPLICATION_CREDENTIALS. Requires the metadata hop limit of 2 (set on
    the instance) so the container can reach IMDSv2. Leave false to disable push
    or to use firebase_ssm_parameter (a real key) instead.
  EOT
  type        = bool
  default     = false
}

variable "bedrock_model_id" {
  description = <<-EOT
    Amazon Bedrock model id for the fit/design assistant, injected as
    BEDROCK_MODEL_ID. The instance calls Bedrock via its IAM role — no API key.
    Cheapest options (us-east-1): "amazon.nova-lite-v1:0" (recommended) or
    "amazon.nova-micro-v1:0". Empty = fall back to ANTHROPIC_API_KEY, then rules.
  EOT
  type        = string
  default     = "amazon.nova-lite-v1:0"
}

variable "anthropic_ssm_parameter" {
  description = <<-EOT
    Name of an SSM Parameter Store SecureString holding the Anthropic API key
    (must live under /<project>/...). The instance reads it at boot and injects
    ANTHROPIC_API_KEY so the fit/design assistant uses Claude instead of the
    rule-based fallback. Create it once, out-of-band:
      aws ssm put-parameter --type SecureString \
        --name /swaya-dsv/anthropic-api-key --value "sk-ant-..."
    Empty = assistant stays on the rule-based fallback.
  EOT
  type        = string
  default     = ""
}
