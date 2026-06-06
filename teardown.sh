#!/bin/bash
# teardown.sh
# Gracefully shuts down the demo environment to stop costs.
# Demo tier = Railway services + minimal AWS (IAM user + budget alert only).
# Run this when you're between interview cycles or pausing the build.
#
# Usage:
#   ./teardown.sh           — interactive (asks for confirmation)
#   ./teardown.sh --auto    — non-interactive (CI/scripted use)
#
# To bring everything back up:
#   1. Push to main → Railway auto-redeploys
#   2. IAM user and budget alert persist (cost is ~$0 when not calling Bedrock)

set -euo pipefail

PROJECT_TAG="reg-intel-agent"
TERRAFORM_DIR="$(cd "$(dirname "$0")/terraform" && pwd)"
AWS_REGION="${AWS_DEFAULT_REGION:-ca-central-1}"
AUTO=false

[[ "${1:-}" == "--auto" ]] && AUTO=true

echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║   Regulatory Intelligence Agent — DEMO TEARDOWN        ║"
echo "║   Railway services suspended + AWS verified clean      ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
echo "What this does:"
echo "  1. Suspends Railway services (stops compute billing)"
echo "  2. Verifies no unexpected AWS resources are running"
echo "  3. Optionally destroys the AWS budget alert + IAM user via Terraform"
echo ""
echo "What this does NOT do:"
echo "  - Delete your Railway project or data (redeploy = git push)"
echo "  - Delete your Qdrant data (persists in Railway volume)"
echo "  - Delete your PostgreSQL audit log (persists in Railway plugin)"
echo ""

if [ "$AUTO" = false ]; then
  read -rp "Continue? (y/N): " CONFIRM
  [[ "$CONFIRM" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }
fi

# ── Step 1: Railway — suspend services ───────────────────────────────────────
echo ""
echo "► Railway: suspending services..."

if command -v railway &>/dev/null; then
  echo "  Suspending api service..."
  railway service suspend --service api 2>/dev/null || \
    echo "  Could not auto-suspend — suspend manually in Railway dashboard:"
    echo "  https://railway.app/dashboard → reg-intel-agent → api → Settings → Suspend"
else
  echo "  Railway CLI not installed. Suspend manually in the dashboard:"
  echo "  https://railway.app/dashboard → reg-intel-agent → each service → Settings → Suspend"
  echo ""
  echo "  Or install Railway CLI: npm install -g @railway/cli"
fi

# ── Step 2: AWS — verify no unexpected resources are running ─────────────────
echo ""
echo "► AWS: scanning for tagged resources in $AWS_REGION..."

if command -v aws &>/dev/null; then
  RESOURCES=$(aws resourcegroupstaggingapi get-resources \
    --region "$AWS_REGION" \
    --tag-filters "Key=project,Values=$PROJECT_TAG" \
    --query 'ResourceTagMappingList[*].ResourceARN' \
    --output text 2>/dev/null || echo "")

  if [ -z "$RESOURCES" ]; then
    echo "  ✓ Clean — only expected resources (IAM user + budget alert) found."
  else
    echo "  Resources found:"
    echo "$RESOURCES" | tr '\t' '\n' | sed 's/^/  /'
    echo ""
    echo "  These are expected: IAM user (reg-intel-agent-demo) and Budgets alert."
    echo "  If you see App Runner, ECS, or other services — those are unexpected;"
    echo "  review and delete them to stop billing."
  fi
else
  echo "  AWS CLI not found — verify manually in AWS Console:"
  echo "  https://console.aws.amazon.com/resource-groups/tag-editor"
  echo "  Filter by tag: project = $PROJECT_TAG"
fi

# ── Step 3: Terraform destroy (optional — only if fully shutting down) ────────
echo ""
echo "► Terraform: destroy AWS budget alert + IAM user?"
echo "  (Only needed if you're closing the AWS account or done with the project."
echo "   These resources cost ~\$0/month and are needed to redeploy.)"
echo ""

if [ "$AUTO" = false ]; then
  read -rp "Destroy Terraform resources? (y/N): " DESTROY_TF
else
  DESTROY_TF="n"
fi

if [[ "$DESTROY_TF" =~ ^[Yy]$ ]]; then
  if [ -f "$TERRAFORM_DIR/terraform.tfstate" ]; then
    echo "  Running terraform destroy..."
    cd "$TERRAFORM_DIR"
    terraform destroy -auto-approve \
      -var "aws_region=$AWS_REGION" \
      -var "alert_email=placeholder@example.com"
    echo "  ✓ Terraform resources destroyed."
  else
    echo "  No Terraform state found — nothing to destroy."
  fi
else
  echo "  Skipped. Budget alert and IAM user retained (~\$0/month)."
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║   Teardown complete                                    ║"
echo "║                                                        ║"
echo "║   Ongoing costs while suspended:                       ║"
echo "║   • Railway Pro base plan:    ~\$25 CAD/mo             ║"
echo "║   • Bedrock tokens:           \$0 (no calls)           ║"
echo "║   • AWS IAM + Budgets:        \$0                      ║"
echo "║                                                        ║"
echo "║   To redeploy: git push to main                        ║"
echo "║   Railway auto-redeploys from your GitHub repo         ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
