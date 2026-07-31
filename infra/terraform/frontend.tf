# Optional separate frontend hosting (S3 + CloudFront).
#
# Strategy 1 (the default) serves the SPA from the API container, so these
# resources are disabled unless `enable_frontend_cdn = true`. Enabling requires
# a CloudFront-verified AWS account.

data "aws_caller_identity" "current" {}

locals {
  cdn_count = var.enable_frontend_cdn ? 1 : 0
}

# Private bucket holding the built SPA; only CloudFront may read it.
resource "aws_s3_bucket" "frontend" {
  count  = local.cdn_count
  bucket = "${local.name}-frontend-${data.aws_caller_identity.current.account_id}"
  # Allow teardown even when the bucket still holds built assets.
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  count                   = local.cdn_count
  bucket                  = aws_s3_bucket.frontend[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  count                             = local.cdn_count
  name                              = "${local.name}-frontend-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "frontend" {
  count               = local.cdn_count
  enabled             = true
  default_root_object = "index.html"
  comment             = "${local.name} frontend"
  price_class         = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.frontend[0].bucket_regional_domain_name
    origin_id                = "s3-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend[0].id
  }

  default_cache_behavior {
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 3600
    max_ttl     = 86400
  }

  # SPA routing: serve index.html for client-side routes / missing keys.
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# Allow only this CloudFront distribution to read the bucket (via OAC).
data "aws_iam_policy_document" "frontend_bucket" {
  count = local.cdn_count

  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend[0].arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.frontend[0].arn]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  count  = local.cdn_count
  bucket = aws_s3_bucket.frontend[0].id
  policy = data.aws_iam_policy_document.frontend_bucket[0].json
}
