# EC2 instance role: the API uses the instance profile's temporary credentials
# (no static AWS keys baked into the box) for DynamoDB + S3 access.
data "aws_iam_policy_document" "assume_ec2" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "api" {
  name               = "${var.project}-api-role"
  assume_role_policy = data.aws_iam_policy_document.assume_ec2.json
  tags               = local.tags
}

data "aws_iam_policy_document" "api" {
  # CRUD on exactly the four DSV tables (and their indexes).
  statement {
    sid = "DynamoCrud"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:BatchGetItem",
      "dynamodb:BatchWriteItem",
      "dynamodb:DescribeTable",
    ]
    resources = concat(
      [for t in aws_dynamodb_table.tables : t.arn],
      [for t in aws_dynamodb_table.tables : "${t.arn}/index/*"],
    )
  }

  # Read/write objects in the blob bucket.
  statement {
    sid       = "S3Objects"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.blobs.arn}/*"]
  }

  statement {
    sid       = "S3List"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.blobs.arn]
  }

  # Pull the API image from ECR. GetAuthorizationToken is account-wide (not
  # resource-scoped); the layer/image reads are scoped to our one repo.
  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "EcrPull"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
    ]
    resources = [aws_ecr_repository.api.arn]
  }

  # Read the Firebase service-account secret from SSM Parameter Store (created
  # out-of-band, so the secret never enters Terraform state). Scoped to this
  # project's parameter path; KMS decrypt is gated to the SSM service.
  statement {
    sid     = "SsmFirebase"
    actions = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = [
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${var.project}/*",
    ]
  }

  statement {
    sid       = "KmsDecryptViaSsm"
    actions   = ["kms:Decrypt"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.aws_region}.amazonaws.com"]
    }
  }

  # Invoke Bedrock foundation models for the fit/design assistant (Amazon Nova,
  # Claude, etc.). Scoped to foundation models in this region; the specific model
  # is chosen via the BEDROCK_MODEL_ID env var so no IAM change is needed to switch.
  statement {
    sid     = "BedrockInvoke"
    actions = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = [
      "arn:aws:bedrock:${var.aws_region}::foundation-model/*",
      "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/*",
    ]
  }
}

resource "aws_iam_role_policy" "api" {
  name   = "${var.project}-api-policy"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

resource "aws_iam_instance_profile" "api" {
  name = "${var.project}-api-profile"
  role = aws_iam_role.api.name
  tags = local.tags
}
