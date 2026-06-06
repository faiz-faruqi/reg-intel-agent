# ADR-005: IAM Access Key (Railway) vs. IAM Role (AWS Compute)

## Status
Accepted

## Date
2026-06-05

## Context

The API service needs credentials to call Amazon Bedrock from Railway. Two
authentication mechanisms exist in AWS IAM:

**Option A — IAM access key (long-lived static credential)**
An IAM user is created with a scoped policy. The `aws iam create-access-key`
command (or `terraform apply`) generates an `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY` pair. These are stored as environment variables in the
host platform and rotated manually.

**Option B — IAM role with instance/task metadata credentials (short-lived)**
An IAM role is attached to an AWS compute resource (EC2 instance, ECS task, App
Runner service, Lambda function). The AWS SDK automatically retrieves and rotates
short-lived credentials via the Instance Metadata Service (IMDS) or the
ECS/App Runner credential provider. No static secrets exist in the environment.

Railway is a third-party PaaS that runs containers on its own infrastructure.
It is not AWS compute. The EC2 Instance Metadata Service, ECS task metadata
endpoint, and App Runner credential provider are all AWS-internal mechanisms —
they are not reachable from Railway containers.

An IAM role cannot be attached to a Railway service. Therefore Option B is
architecturally unavailable in the demo tier.

## Decision

Use an **IAM access key** (Option A) for the Railway demo tier, with the
following least-privilege mitigations to compensate for the weaker credential
type:

### IAM user scope (terraform/iam_bedrock.tf)
```hcl
Statement = [
  {
    Sid    = "BedrockInvokeOnly"
    Effect = "Allow"
    Action = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream"
    ]
    Resource = [
      "arn:aws:bedrock:ca-central-1::foundation-model/anthropic.claude-3-5-sonnet*",
      "arn:aws:bedrock:ca-central-1::foundation-model/anthropic.claude-3-haiku*",
      "arn:aws:bedrock:ca-central-1::foundation-model/amazon.titan-embed*"
    ]
  }
]
```

The IAM user `reg-intel-agent-demo` has **no console access, no other AWS
service permissions, and no ability to create, modify, or delete any resource**
beyond calling `bedrock:InvokeModel` on the three named model ARNs. A leaked
credential cannot be used to access S3, EC2, RDS, or any other AWS service. The
blast radius of a compromise is limited to Bedrock token spend, which is bounded
by the AWS Budgets alert in `budget_alert.tf`.

### Credential storage
Credentials are stored **only** in:
- Railway dashboard environment variables (encrypted at rest)
- Local `.env` file (never committed — enforced by `.gitignore`)

They are never hardcoded, never logged, and never included in Docker image layers.

### Rotation policy
The access key must be rotated **every 90 days** using:
```bash
aws iam create-access-key --user-name reg-intel-agent-demo
# Update Railway env vars and local .env with new values
aws iam delete-access-key --user-name reg-intel-agent-demo \
  --access-key-id <old-key-id>
```

## Consequences

### What this buys
- **Works with Railway**: the only viable option given the platform constraint.
- **Simple ops**: one env var pair, standard boto3 credential chain (`AWS_ACCESS_KEY_ID`
  + `AWS_SECRET_ACCESS_KEY` are picked up automatically without any SDK
  configuration).
- **Auditable IAM policy**: the Terraform resource is the source of truth; the
  permissions are narrow, reviewable, and version-controlled.

### What this costs (accepted trade-offs)
- **Static, long-lived credential**: unlike role credentials (which expire every
  15 minutes to 12 hours), an access key is valid until explicitly deleted or
  deactivated. If leaked and not immediately detected, it remains exploitable.
- **Manual rotation burden**: role credentials rotate automatically; access keys
  require a deliberate rotation process every 90 days. Forgetting is a real risk
  in a solo/small-team project.
- **No credential audit trail by default**: CloudTrail records the API calls made
  with the key but does not alert on inactivity or anomalous usage patterns
  without additional GuardDuty configuration.
- **No SCP or permission boundary**: in a real enterprise, the IAM user would sit
  inside an AWS Organization with a Service Control Policy that prevents privilege
  escalation even if the policy were accidentally broadened. This demo account has
  no SCP layer.

## Production trigger

Switch to an IAM role when **any one** of the following is true:

1. The API service moves to **AWS compute** (App Runner, ECS Fargate, EC2).
   At that point, attaching a role is a one-line Terraform change and eliminates
   the static credential entirely.
2. A **security audit or compliance review** flags the long-lived key as a
   finding (common in OSFI, SOC 2, or FedRAMP assessments).
3. The project **onboards a second developer** with production access — shared
   static keys violate least-privilege per-identity accountability.

## Production path (out of scope for this phase)

When the service moves to AWS App Runner:

```hcl
# App Runner instance role — replaces the IAM user + access key entirely
resource "aws_iam_role" "api_task_role" {
  name = "reg-intel-agent-api-task"
  assume_role_policy = jsonencode({
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "tasks.apprunner.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "bedrock_invoke" {
  role       = aws_iam_role.api_task_role.name
  policy_arn = aws_iam_policy.bedrock_invoke.arn  # same policy, different principal
}
```

The application code does not change. The boto3 credential chain picks up the
instance role automatically — `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` env
vars are simply removed. The IAM user `reg-intel-agent-demo` is then deleted.

| Concern | Demo (now) | Production |
|---|---|---|
| Credential type | IAM access key (static) | IAM role (dynamic, auto-rotating) |
| Rotation | Manual, every 90 days | Automatic (15 min – 12 hr TTL) |
| Storage | Railway env vars + local .env | Not stored anywhere — IMDS only |
| Blast radius if leaked | Bedrock invoke on 3 model ARNs | N/A — no static credential exists |
| Terraform change | `aws_iam_user` + `aws_iam_access_key` | `aws_iam_role` + instance attachment |
| Cost delta | $0 | $0 (IAM is free; App Runner compute is separate) |

## Interview talking point

The access key is a deliberate, documented concession to the platform constraint —
not an oversight. The policy scope is tight enough that a credential leak's blast
radius is limited to Bedrock token spend, and the budget alert is the backstop for
even that. In production the entire credential surface disappears; the role
assumption is handled by AWS internally and the application code is unchanged.
That is the security posture story: make the trade-off explicit, bound the risk,
and show the clean exit path.

## References
- [AWS IAM best practices — use roles instead of long-term credentials](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [AWS App Runner IAM roles](https://docs.aws.amazon.com/apprunner/latest/dg/security-iam-roles.html)
- ADR-004 — Railway Hobby vs. AWS App Runner/ECS (hosting transition trigger)
