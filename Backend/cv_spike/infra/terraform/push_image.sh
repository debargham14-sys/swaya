#!/usr/bin/env bash
# Build the DSV API image and push it to ECR so the EC2 box can pull it.
#
# Ordering for a first deploy (ECR must exist before you can push, the instance
# needs the image before it boots):
#   1. terraform init
#   2. terraform apply -target=aws_ecr_repository.api    # create just the registry
#   3. ./push_image.sh                                   # build + push the image
#   4. terraform apply                                   # create everything else
# After that, redeploy a new build with just: ./push_image.sh && terraform apply
# (user_data_replace_on_change re-bootstraps the instance to pull the new image).
#
# Requires: aws CLI (logged in), Docker with buildx. Builds linux/amd64 so it
# runs on the x86_64 EC2 instance even from an Apple-Silicon Mac.
set -euo pipefail

cd "$(dirname "$0")"

REGION="$(awk -F'"' '/aws_region/{print $2; exit}' terraform.tfvars 2>/dev/null || echo us-east-1)"
PROJECT="$(awk -F'"' '/^project/{print $2; exit}' terraform.tfvars 2>/dev/null || echo swaya-dsv)"
# Default to a unique, content-ish tag (git short SHA, +"-dirty" if uncommitted)
# so `terraform apply -var image_tag=<tag>` actually changes user_data and the
# instance re-pulls. Pushing only ":latest" would leave apply seeing "no changes".
if [ -n "${1:-}" ]; then
  TAG="$1"
else
  SHA="$(git -C "$(dirname "$0")" rev-parse --short HEAD 2>/dev/null || echo manual)"
  git -C "$(dirname "$0")" diff --quiet 2>/dev/null || SHA="${SHA}-dirty"
  TAG="$SHA"
fi

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ECR_URL="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${PROJECT}-api"
CONTEXT="$(cd ../.. && pwd)" # Backend/cv_spike — has the Dockerfile

echo "Region:   $REGION"
echo "Image:    ${ECR_URL}:${TAG}"
echo "Context:  $CONTEXT"

aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# Push the unique tag AND :latest (latest is a convenience pointer; deploys pin
# the unique tag so the instance reliably re-pulls).
docker buildx build \
  --platform linux/amd64 \
  -t "${ECR_URL}:${TAG}" \
  -t "${ECR_URL}:latest" \
  --push \
  "$CONTEXT"

echo
echo "Pushed ${ECR_URL}:${TAG} (and :latest)"
echo "Deploy it with:"
echo "    terraform apply -var=\"image_tag=${TAG}\""
