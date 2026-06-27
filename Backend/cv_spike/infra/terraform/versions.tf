terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state (recommended once more than one person touches this). First run
  # the bootstrap/ config to create the bucket + lock table, set the bucket name
  # below to match, then run `terraform init -migrate-state` in this directory.
  # backend "s3" {
  #   bucket         = "swaya-dsv-tfstate-CHANGEME" # must match bootstrap/state_bucket_name
  #   key            = "dsv/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "swaya-dsv-tflock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region
}
