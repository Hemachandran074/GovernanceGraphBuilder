# Governance Graph Builder — AWS Infrastructure (Terraform)

Provisions the cloud stack for the Governance Graph Builder. The default
deployment is **Strategy 1 (unified container)**: one ECS service runs the
FastAPI backend, which also serves the built React SPA — so a single image
ships both the UI and the API, reachable at one URL via the ALB.

Provisioned resources:

- **ECR** — container registry for the unified image
- **VPC** — 2 public + 2 private subnets, single NAT gateway
- **ECS Fargate + ALB** — the app (UI + API), autoscaled on CPU, tasks in private subnets
- **Secrets Manager** — Neo4j credentials injected into the task
- **IAM** — execution role (pull/logs/secrets) + task role (Bedrock)
- **CloudWatch Logs** — structured logs
- **S3 + CloudFront** — *optional* separate frontend hosting, off by default
  (`enable_frontend_cdn`); requires a CloudFront-verified AWS account

The graph database is **managed Neo4j (e.g. Neo4j Aura)** — provision it
separately and pass its connection details as variables.

## Prerequisites
- Terraform >= 1.6 and AWS credentials configured (`aws sts get-caller-identity`)
- A Neo4j Aura instance (URI, username, password)
- Docker (to build/push the image)

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
Key outputs: `ecr_repository_url`, `app_url` (serves UI + API), `ecs_cluster_name`,
`ecs_service_name`.

## 3. Build & push the unified image, then roll the service
Build from the **repository root** so the frontend is bundled into the image:
```bash
ECR_URL=$(terraform output -raw ecr_repository_url)
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin "$ECR_URL"

# from the repo root:
docker build -f backend/Dockerfile -t "$ECR_URL:latest" .
docker push "$ECR_URL:latest"

aws ecs update-service --cluster $(terraform output -raw ecs_cluster_name) \
  --service $(terraform output -raw ecs_service_name) --force-new-deployment
```
Once the task is healthy, open **`terraform output -raw app_url`** — the UI loads
at `/` and the API at `/health`, `/docs`, `/graph`, etc. (This is also what the
`Deploy` GitHub Actions workflow automates.)

## 4. Validate against the live URL
```bash
BASE_URL=$(terraform output -raw app_url) uv run --project ../../backend python ../../backend/scripts/validate.py
```

## Notes
- **HTTPS:** provide `acm_certificate_arn` (a cert in `aws_region`) to serve the
  ALB over 443 and redirect 80→443. Otherwise it's HTTP only. Because the UI is
  same-origin with the API, no CORS or separate frontend URL is needed.
- **Separate CDN (optional):** set `enable_frontend_cdn = true` to also provision
  S3 + CloudFront (needs a CloudFront-verified account). Not required for Strategy 1.
- **Bedrock:** the task role grants `bedrock:InvokeModel`; ensure `bedrock_model_id`
  is enabled in your account/region. With no Bedrock access the app falls back to
  the offline heuristic policy parser.
- **Cost:** the NAT gateway and ALB incur ongoing charges. `terraform destroy`
  tears everything down.

## Destroy
```bash
terraform destroy
```
