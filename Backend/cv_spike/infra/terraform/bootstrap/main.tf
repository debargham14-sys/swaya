# State backend bootstrap — run this ONCE before enabling the S3 backend on the
# main stack. It creates the remote-state bucket + a DynamoDB lock table. This
# config itself uses local state (the classic chicken-and-egg); commit nothing
# but its own tiny state, or just keep it local.
#
#   cd bootstrap
#   terraform init
#   terraform apply        # creates the bucket + lock table
#   # then uncomment the backend "s3" block in ../versions.tf and run, in ../:
#   terraform init -migrate-state

terraform {
  required_version = ">= 1.5"
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

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "state_bucket_name" {
  description = "Globally-unique S3 bucket for Terraform state."
  type        = string
  default     = "swaya-dsv-tfstate-CHANGEME"
}

variable "lock_table_name" {
  type    = string
  default = "swaya-dsv-tflock"
}

resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket_name
  tags   = { Project = "swaya-dsv", ManagedBy = "terraform", Purpose = "tfstate" }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "lock" {
  name         = var.lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = { Project = "swaya-dsv", ManagedBy = "terraform", Purpose = "tflock" }
}

output "state_bucket" {
  value = aws_s3_bucket.state.bucket
}

output "lock_table" {
  value = aws_dynamodb_table.lock.name
}
