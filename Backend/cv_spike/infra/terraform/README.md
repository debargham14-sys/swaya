# DSV API — AWS infrastructure (Terraform)

Provisions the cloud stack for the Swaya/DSV body-measurement API:

```
                 ┌──────────────────┐
  mobile app ──▶ │  API Gateway      │  (HTTP API, public invoke URL)
                 │  ANY /{proxy+}    │
                 └────────┬─────────┘
                          │ HTTP_PROXY → :8000
                 ┌────────▼─────────┐     IAM role (no static keys)
                 │  EC2 (AL2023)     │────────────┐
                 │  Docker: uvicorn  │            │
                 └──────────────────┘            ▼
                          │              ┌─────────────────┐
                          ├────────────▶ │ DynamoDB (x4)    │  metadata
                          └────────────▶ │ S3 bucket        │  photos + bundles
                                         └─────────────────┘
```

Replaces the previous Render + MongoDB setup. DynamoDB holds the JSON metadata the
Mongo collections used to (`{prefix}_scans`, `_calibration`, `_vest_scans`,
`_vest_calibration`); S3 holds the binary blobs (DynamoDB items cap at 400 KB).

## What gets created

| File             | Resources |
|------------------|-----------|
| `dynamodb.tf`    | 4 on-demand tables (PITR on) |
| `s3.tf`          | private, encrypted, versioned bucket |
| `iam.tf`         | EC2 instance role scoped to those tables + bucket |
| `ec2.tf`         | AL2023 instance + security group; `user_data.sh.tftpl` builds & runs the Docker image |
| `apigateway.tf`  | HTTP API → EC2 `:8000` proxy |

## Deploy

```bash
cd Backend/cv_spike/infra/terraform
cp terraform.tfvars.example terraform.tfvars   # set s3_bucket_name + ssh_ingress_cidr

terraform init
terraform plan      # review — nothing is created yet
terraform apply     # type "yes" to provision
```

After apply:

```bash
terraform output api_base_url        # https://xxxx.execute-api.us-east-1.amazonaws.com
curl "$(terraform output -raw api_base_url)/health"   # {"status":"ok","dynamodb":true,...}
```

The EC2 bootstrap (clone → `docker build` → run) takes ~3–5 min after the instance
boots; `/health` returns 502 from the gateway until the container is up. Watch it:

```bash
ssh ec2-user@$(terraform output -raw ec2_public_dns)   # needs key_name + ssh_ingress_cidr set
sudo tail -f /var/log/cloud-init-output.log
docker logs -f swaya-api
```

Point the mobile app at the gateway: `--dart-define=API_BASE_URL=$(terraform output -raw api_base_url)`.

## Notes & hardening

- **Credentials:** the API uses the EC2 instance role — no AWS keys on the box or in
  env. The IAM policy is scoped to exactly the four tables and the one bucket.
- **`api_ingress_cidr` defaults to `0.0.0.0/0`.** API Gateway's HTTP_PROXY calls the
  instance from the public internet, so port 8000 is open. To lock it down, put the
  EC2 in a private subnet behind an internal ALB and use an API Gateway **VPC Link**
  instead of the public proxy — more resources, but the box is never internet-facing.
- **`repo_url` must be reachable from EC2.** For a private repo, bake a deploy key /
  token into `user_data.sh.tftpl`, or build the image in CI and pull from ECR.
- **State:** `terraform.tfstate` is git-ignored (it holds resource IDs). For team use,
  move it to an S3 backend with DynamoDB state locking.
- **Teardown:** `terraform destroy`. The S3 bucket must be emptied first if it has
  objects (versioned bucket → delete all versions).
```
