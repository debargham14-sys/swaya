# Latest Amazon Linux 2023 AMI (has dnf + docker in the default repos).
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

resource "aws_security_group" "api" {
  name        = "${var.project}-api-sg"
  description = "DSV API: app port from API Gateway, SSH from operator."
  tags        = local.tags

  ingress {
    description = "App port (uvicorn) - reached by API Gateway HTTP_PROXY."
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = [var.api_ingress_cidr]
  }

  ingress {
    description = "SSH (operator only)."
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_ingress_cidr]
  }

  egress {
    description = "All outbound (pip, git, AWS APIs, model download)."
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "api" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  iam_instance_profile   = aws_iam_instance_profile.api.name
  vpc_security_group_ids = [aws_security_group.api.id]
  key_name               = var.key_name != "" ? var.key_name : null

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    api_image              = local.api_image
    aws_region             = var.aws_region
    dynamo_prefix          = var.dynamo_table_prefix
    s3_bucket              = var.s3_bucket_name
    auth_required          = var.auth_required
    firebase_project_id     = var.firebase_project_id
    firebase_ssm_parameter  = var.firebase_ssm_parameter
    anthropic_ssm_parameter = var.anthropic_ssm_parameter
  })

  # Pull the image only after it exists in ECR. (You still push the image before
  # apply — see push_image.sh — but this orders repo creation before the box.)
  depends_on = [aws_ecr_repository.api]

  # Re-bootstrap if the deploy inputs change.
  user_data_replace_on_change = true

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
  }

  tags = merge(local.tags, { Name = "${var.project}-api" })
}
