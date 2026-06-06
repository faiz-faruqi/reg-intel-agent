# budget_alert.tf
# DEPLOY THIS FIRST — before making any Bedrock API calls.
# Tracks Bedrock token spend tagged to this project.
# Railway hosting costs are billed separately via Railway dashboard.
# This only covers AWS spend (Bedrock tokens + IAM — expected ~$5–15 USD/month).

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      project     = "reg-intel-agent"
      environment = "demo"
      managed-by  = "terraform"
    }
  }
}

variable "aws_region" {
  description = "AWS region — ca-central-1 for Canadian FSI demo"
  default     = "ca-central-1"
}

variable "alert_email" {
  description = "Email address for budget alerts"
  type        = string
}

variable "monthly_budget_usd" {
  description = "Monthly AWS budget ceiling in USD (Bedrock tokens only in demo phase)"
  default     = 30
}

# Budget alert — Bedrock token spend for this project
resource "aws_budgets_budget" "monthly_cap" {
  name         = "reg-intel-agent-monthly"
  budget_type  = "COST"
  limit_amount = var.monthly_budget_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["project$reg-intel-agent"]
  }

  # Alert at 80% actual spend
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  # Alert at 100% forecasted — warns before you hit the ceiling
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}

output "budget_name" {
  value       = aws_budgets_budget.monthly_cap.name
  description = "Name of the AWS budget alert"
}
