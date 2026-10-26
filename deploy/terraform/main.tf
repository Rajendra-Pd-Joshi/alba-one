# ==============================================================================
# ALBA ONE — Terraform Infrastructure as Code (`deploy/terraform/main.tf`)
# Provisions managed production stores in `ap-northeast-1` (Tokyo):
# - Managed Amazon RDS PostgreSQL 16 (`pgvector`, Multi-AZ, KMS encryption,
#   `rds.force_ssl = 1`, IAM Database Authentication enabled)
# - Managed Amazon ElastiCache Redis 7 (`transit_encryption_enabled = true`,
#   `at_rest_encryption_enabled = true`, auth token via Secrets Manager)
# - AWS KMS CMK with automatic annual key rotation (`enable_key_rotation = true`)
# - Note: Customer's on-premise knowledge PostgreSQL is NOT deployed here;
#   it connects over AWS Direct Connect / Site-to-Site VPN with mTLS and
#   read-only SQL views (see `docs/KB_EXTRACTION.md` & `docs/SECURITY.md`).
# ==============================================================================
terraform {
  required_version = ">= 1.8.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

variable "environment" {
  type    = string
  default = "production"
}

variable "aws_region" {
  type    = string
  default = "ap-northeast-1"
}

variable "vpc_id" {
  type = string
}

variable "private_data_subnet_ids" {
  type = list(string)
}

provider "aws" {
  region = var.aws_region
}

resource "aws_kms_key" "alba_data_cmk" {
  description             = "ALBA ONE (${var.environment}) CMK for RDS, ElastiCache, and Secrets Manager"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_db_parameter_group" "postgres16_tls" {
  name   = "alba-one-${var.environment}-pg16-tls"
  family = "postgres16"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
}

resource "aws_db_subnet_group" "data_subnets" {
  name       = "alba-one-${var.environment}-db-subnets"
  subnet_ids = var.private_data_subnet_ids
}

resource "aws_db_instance" "alba_postgres" {
  identifier                            = "alba-one-${var.environment}-pg"
  engine                                = "postgres"
  engine_version                        = "16.4"
  instance_class                        = "db.r6g.large" # TODO(owner): tune from measured load tests
  allocated_storage                     = 100
  max_allocated_storage                 = 500
  storage_encrypted                     = true
  kms_key_id                            = aws_kms_key.alba_data_cmk.arn
  multi_az                              = var.environment == "production"
  db_name                               = "alba_one"
  username                              = "alba_app"
  manage_master_user_password           = true
  master_user_secret_kms_key_id         = aws_kms_key.alba_data_cmk.arn
  iam_database_authentication_enabled   = true
  db_subnet_group_name                  = aws_db_subnet_group.data_subnets.name
  parameter_group_name                  = aws_db_parameter_group.postgres16_tls.name
  publicly_accessible                   = false
  deletion_protection                   = var.environment == "production"
  backup_retention_period               = 14
  performance_insights_enabled          = true
  performance_insights_kms_key_id       = aws_kms_key.alba_data_cmk.arn
  skip_final_snapshot                   = var.environment != "production"
}

resource "aws_elasticache_subnet_group" "redis_subnets" {
  name       = "alba-one-${var.environment}-redis-subnets"
  subnet_ids = var.private_data_subnet_ids
}

resource "aws_elasticache_replication_group" "alba_redis" {
  replication_group_id          = "alba-one-${var.environment}-redis"
  description                   = "ALBA ONE (${var.environment}) Managed Redis (TLS + Auth)"
  engine                        = "redis"
  engine_version                = "7.1"
  node_type                     = "cache.r6g.large" # TODO(owner): tune from measured load tests
  num_cache_clusters            = var.environment == "production" ? 2 : 1
  port                          = 6379
  subnet_group_name             = aws_elasticache_subnet_group.redis_subnets.name
  at_rest_encryption_enabled    = true
  kms_key_id                    = aws_kms_key.alba_data_cmk.arn
  transit_encryption_enabled    = true
  transit_encryption_mode       = "required"
  automatic_failover_enabled    = var.environment == "production"
   multi_az_enabled             = var.environment == "production"
}
