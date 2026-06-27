# Deploying the DSV API to real AWS

This stack runs the FastAPI service on EC2 behind an HTTP API Gateway, with
DynamoDB + S3 for storage. The container image is pulled from **ECR** (built and
pushed from your machine — nothing is cloned/built on the instance, so the repo
can stay private).

## Prerequisites
- AWS account + credentials on this machine: `aws configure` (or `AWS_*` env vars).
  Verify with `aws sts get-caller-identity`.
- A default VPC in the target region (`aws ec2 describe-vpcs --filters Name=isDefault,Values=true`).
  If none, you'll need to add subnet/VPC wiring to `ec2.tf`.
- Docker with buildx, and Terraform ≥ 1.5.

## One-time first deploy
```bash
cd Backend/cv_spike/infra/terraform

# 0. Review terraform.tfvars — fix the two TODOs (unique s3 bucket name; SSH CIDR
#    if you set key_name). The API is OPEN until auth_required="1".

terraform init

# 1. Create just the ECR registry first (the image has to exist before the box boots).
terraform apply -target=aws_ecr_repository.api

# 2. Build the image and push it.
./push_image.sh

# 3. Create everything else (EC2, DynamoDB, S3, IAM, API Gateway).
terraform apply

# 4. Grab the public URL.
terraform output api_base_url
```

The instance takes ~2–3 min after `apply` to pull the image and start (watch
`/var/log/cloud-init-output.log` on the box, or just poll `<api_base_url>/health`).

## Point the app at it
```bash
cd ../../../../Mobile/swaya_app
flutter build apk --release --dart-define=API_BASE_URL=$(terraform -chdir=../../Backend/cv_spike/infra/terraform output -raw api_base_url)
# (or pass the URL string directly to --dart-define)
```

## Redeploy a new build
`push_image.sh` tags the image with the git short SHA and prints the exact apply
command. Pinning a unique tag is what makes Terraform notice the change and
re-bootstrap the instance (re-pushing only `:latest` would show "no changes").
```bash
./push_image.sh                          # builds, pushes <sha> + :latest, prints:
terraform apply -var="image_tag=<sha>"   # instance is replaced + pulls the new image
```
Persist the new tag by setting `image_tag` in `terraform.tfvars` instead of
passing `-var` each time.

## Tear down (stops all billing)
```bash
# Empty the versioned bucket first, then:
terraform destroy
```

## Enable Firebase auth (require signed-in requests)
The instance reads the Firebase service-account JSON from SSM Parameter Store at
boot and injects it as `FIREBASE_SERVICE_ACCOUNT_JSON` — the secret never enters
Terraform state.
```bash
# 1. Store the service-account JSON as a SecureString (one time).
aws ssm put-parameter --type SecureString \
  --name /swaya-dsv/firebase-credentials \
  --value file://serviceAccount.json --region us-east-1

# 2. In terraform.tfvars set:
#      firebase_ssm_parameter = "/swaya-dsv/firebase-credentials"
#      auth_required          = "1"
# 3. Re-apply (re-bootstraps the instance with auth on).
terraform apply
```
Rotate the key later by re-`put-parameter --overwrite` then `terraform apply`
(the instance re-reads it on re-bootstrap).

## Use remote state (recommended for >1 person)
State is local by default. To move it to S3 with a DynamoDB lock:
```bash
cd bootstrap
# set state_bucket_name to something globally unique (in main.tf or -var)
terraform init && terraform apply        # creates state bucket + lock table
cd ..
# uncomment the backend "s3" block in versions.tf (match the bucket name), then:
terraform init -migrate-state            # copies existing local state up to S3
```

## Known follow-ups (not blockers)
- **API is internet-exposed on :8000** (API Gateway HTTP_PROXY reaches the box
  over the public internet). Production hardening = VPC Link + private ALB.
- `render.yaml` at the repo root is the **old Mongo deploy** — ignore it for this
  stack.
