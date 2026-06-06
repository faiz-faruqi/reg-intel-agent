# iam_bedrock.tf
# Minimal IAM user for Railway → Bedrock API calls.
# Scoped to Bedrock invoke only — no other AWS permissions.
#
# IMPORTANT: This access key approach is a demo-tier concession.
# Railway is not AWS compute so IAM roles are not available.
# In production (AWS App Runner / ECS), replace with an IAM role.
# See ADR-005 in docs/adrs/.

variable "bedrock_model_arns" {
  description = "ARNs of Bedrock models this user is allowed to invoke"
  type        = list(string)
  default = [
    "arn:aws:bedrock:ca-central-1::foundation-model/anthropic.claude-3-5-sonnet*",
    "arn:aws:bedrock:ca-central-1::foundation-model/anthropic.claude-3-haiku*",
    "arn:aws:bedrock:ca-central-1::foundation-model/amazon.titan-embed*"
  ]
}

# IAM user — one per project, not per developer
resource "aws_iam_user" "bedrock_demo" {
  name = "reg-intel-agent-demo"
  path = "/reg-intel-agent/"

  tags = {
    purpose = "bedrock-api-railway-demo"
  }
}

# Policy: Bedrock invoke only, scoped to specific model ARNs
resource "aws_iam_policy" "bedrock_invoke" {
  name        = "reg-intel-agent-bedrock-invoke"
  description = "Allow Bedrock model invocation for reg-intel-agent demo only"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockInvokeOnly"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = var.bedrock_model_arns
      }
    ]
  })
}

resource "aws_iam_user_policy_attachment" "bedrock_demo_attach" {
  user       = aws_iam_user.bedrock_demo.name
  policy_arn = aws_iam_policy.bedrock_invoke.arn
}

# Access key — store output values in Railway env vars and local .env ONLY
# Never commit these values to git
resource "aws_iam_access_key" "bedrock_demo" {
  user = aws_iam_user.bedrock_demo.name
}

output "aws_access_key_id" {
  value       = aws_iam_access_key.bedrock_demo.id
  description = "Store as AWS_ACCESS_KEY_ID in Railway env vars and local .env"
  sensitive   = false
}

output "aws_secret_access_key" {
  value       = aws_iam_access_key.bedrock_demo.secret
  description = "Store as AWS_SECRET_ACCESS_KEY in Railway env vars and local .env"
  sensitive   = true
}
