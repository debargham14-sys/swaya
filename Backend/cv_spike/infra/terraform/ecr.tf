# Container registry the EC2 box pulls the API image from. We push the image
# here from a laptop/CI (see push_image.sh) instead of building on the instance —
# no source checkout on the box, so the repo can stay private.
resource "aws_ecr_repository" "api" {
  name                 = "${var.project}-api"
  image_tag_mutability = "MUTABLE" # allow re-pushing the same tag (e.g. "latest")
  force_delete         = true      # let `terraform destroy` remove images too

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.tags
}

# Keep only the most recent images so old layers don't accrue storage cost.
resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire all but the 10 most recent images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      }
    ]
  })
}

locals {
  # Full image reference the instance pulls, e.g.
  # 1234.dkr.ecr.us-east-1.amazonaws.com/swaya-dsv-api:latest
  api_image = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"
}
