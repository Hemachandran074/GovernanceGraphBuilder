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

# The frontend is served by the API container (Strategy 1); these are populated
# only when enable_frontend_cdn = true.
output "frontend_bucket" {
  description = "S3 bucket for the built frontend (only when enable_frontend_cdn = true)."
  value       = try(aws_s3_bucket.frontend[0].bucket, null)
}

output "frontend_url" {
  description = "Public URL of the frontend via CloudFront (only when enable_frontend_cdn = true)."
  value       = try("https://${aws_cloudfront_distribution.frontend[0].domain_name}", null)
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution id (only when enable_frontend_cdn = true)."
  value       = try(aws_cloudfront_distribution.frontend[0].id, null)
}

output "app_url" {
  description = "Public URL serving both the UI and API (Strategy 1, via the ALB)."
  value       = var.acm_certificate_arn == "" ? "http://${aws_lb.this.dns_name}" : "https://${aws_lb.this.dns_name}"
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
