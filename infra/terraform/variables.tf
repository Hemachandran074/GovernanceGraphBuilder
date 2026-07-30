# --- General ---
variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short name used to prefix resources."
  type        = string
  default     = "ggb"
}

variable "environment" {
  description = "Deployment environment (prod, staging, ...)."
  type        = string
  default     = "prod"
}

# --- Networking ---
variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.20.0.0/16"
}

# --- Backend container / ECS ---
variable "image_tag" {
  description = "Tag of the backend image in ECR to run."
  type        = string
  default     = "latest"
}

variable "container_port" {
  description = "Port the backend container listens on."
  type        = number
  default     = 8000
}

variable "task_cpu" {
  description = "Fargate task CPU units (256, 512, 1024, ...)."
  type        = number
  default     = 512
}

variable "task_memory" {
  description = "Fargate task memory (MiB)."
  type        = number
  default     = 1024
}

variable "desired_count" {
  description = "Number of backend tasks to run."
  type        = number
  default     = 2
}

variable "min_capacity" {
  description = "Autoscaling minimum task count."
  type        = number
  default     = 2
}

variable "max_capacity" {
  description = "Autoscaling maximum task count."
  type        = number
  default     = 6
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for HTTPS on the ALB. Empty = HTTP only."
  type        = string
  default     = ""
}

variable "cors_origins" {
  description = "Comma-separated allowed CORS origins for the API. Set to the CloudFront URL in production instead of '*'."
  type        = string
  default     = "*"
}

# --- Neo4j (managed, e.g. Neo4j Aura) ---
variable "neo4j_uri" {
  description = "Bolt URI of the Neo4j instance (e.g. neo4j+s://xxxx.databases.neo4j.io)."
  type        = string
}

variable "neo4j_username" {
  description = "Neo4j username."
  type        = string
  default     = "neo4j"
}

variable "neo4j_password" {
  description = "Neo4j password."
  type        = string
  sensitive   = true
}

variable "neo4j_database" {
  description = "Neo4j database name."
  type        = string
  default     = "neo4j"
}

# --- LLM ---
variable "llm_provider" {
  description = "LLM provider for policy parsing (bedrock recommended in AWS)."
  type        = string
  default     = "bedrock"
}

variable "bedrock_model_id" {
  description = "Bedrock model id (or inference profile id) for policy parsing."
  type        = string
  default     = "anthropic.claude-3-5-sonnet-20241022-v2:0"
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days."
  type        = number
  default     = 30
}
