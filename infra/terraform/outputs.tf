output "ecr_repository_url" {
  description = "Push the backend image here."
  value       = aws_ecr_repository.backend.repository_url
}

output "api_url" {
  description = "Base URL of the backend API (via the ALB)."
  value       = var.acm_certificate_arn == "" ? "http://${aws_lb.this.dns_name}" : "https://${aws_lb.this.dns_name}"
}

output "alb_dns_name" {
  description = "ALB DNS name."
  value       = aws_lb.this.dns_name
}

output "frontend_bucket" {
  description = "S3 bucket for the built frontend (aws s3 sync target)."
  value       = aws_s3_bucket.frontend.bucket
}

output "frontend_url" {
  description = "Public URL of the frontend (CloudFront)."
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution id (for cache invalidation)."
  value       = aws_cloudfront_distribution.frontend.id
}

output "neo4j_secret_arn" {
  description = "Secrets Manager ARN holding the Neo4j credentials."
  value       = aws_secretsmanager_secret.neo4j.arn
}

output "ecs_cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.this.name
}

output "ecs_service_name" {
  description = "ECS service name."
  value       = aws_ecs_service.backend.name
}
