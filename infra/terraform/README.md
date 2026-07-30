# Governance Graph Builder — AWS Infrastructure (Terraform)

Provisions the cloud stack for the Governance Graph Builder:

- **ECR** — backend container registry
- **VPC** — 2 public + 2 private subnets, single NAT gateway
- **ECS Fargate + ALB** — the backend API (autoscaled on CPU), tasks in private subnets
- **Secrets Manager** — Neo4j credentials injected into the task
- **IAM** — execution role (pull/logs/secrets) + task role (Bedrock)
- **S3 + CloudFront** — the static frontend (private bucket, OAC)
- **CloudWatch Logs** — structured backend logs

The graph database is **managed Neo4j (e.g. Neo4j Aura)** — provision it separately
and pass its connection details as variables.

## Prerequisites
- Terraform >= 1.6 and AWS credentials configured (`aws sts get-caller-identity`)
- A Neo4j Aura instance (URI, username, password)
- Docker (to build/push the backend image)

## 1. Configure
```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # fill in Neo4j creds etc.
```

## 2. Provision
```bash
terraform init
terraform plan
terraform apply
```
Note the outputs: `ecr_repository_url`, `api_url`, `frontend_bucket`,
`frontend_url`, `cloudfront_distribution_id`.

## 3. Build & push the backend image
```bash
ECR_URL=$(terraform output -raw ecr_repository_url)
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin "$ECR_URL"
docker build -t "$ECR_URL:latest" ../../backend
docker push "$ECR_URL:latest"
# Roll the service onto the new image:
aws ecs update-service --cluster $(terraform output -raw ecs_cluster_name) \
  --service $(terraform output -raw ecs_service_name) --force-new-deployment
```
The ECS service becomes healthy once an image is present and tasks pass the
`/health` check.

## 4. Build & deploy the frontend
Build the SPA pointing at the API URL, then sync to S3 and invalidate CloudFront:
```bash
API_URL=$(terraform output -raw api_url)
cd ../../frontend
VITE_API_BASE_URL="$API_URL" npm run build
aws s3 sync dist "s3://$(cd ../infra/terraform && terraform output -raw frontend_bucket)" --delete
aws cloudfront create-invalidation \
  --distribution-id $(cd ../infra/terraform && terraform output -raw cloudfront_distribution_id) \
  --paths "/*"
```

## 5. Lock down CORS (recommended)
After the first apply, set `cors_origins` to your `frontend_url` and re-apply so
the API only accepts the CloudFront origin:
```hcl
cors_origins = "https://dxxxxxxxx.cloudfront.net"
```

## Notes
- **HTTPS:** provide `acm_certificate_arn` (a cert in `aws_region`) to serve the
  ALB over 443 and redirect 80→443. Otherwise the API is HTTP only.
- **Bedrock:** the task role grants `bedrock:InvokeModel`; ensure the chosen
  `bedrock_model_id` is enabled in your account/region.
- **Cost:** the NAT gateway, ALB, and CloudFront incur ongoing charges. Run
  `terraform destroy` to tear everything down.

## Destroy
```bash
terraform destroy
```
