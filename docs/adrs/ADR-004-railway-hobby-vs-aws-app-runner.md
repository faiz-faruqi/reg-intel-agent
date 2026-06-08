# ADR-004: Railway Hobby (Demo) vs. AWS App Runner/ECS (Production)

## Status
Accepted

## Date
2026-06-07

## Context

The FastAPI service needs a host. Three options were evaluated:

### Option A — Railway Hobby tier
Railway is a PaaS that builds from a GitHub repo (or Dockerfile) and deploys
containers on shared infrastructure. The Hobby tier has no monthly base fee —
you pay only for compute consumed while the service is running. Services sleep
after 30 minutes of inactivity and wake on the next request (~10–30 s cold start).

**Pricing (approximate):**
- $0 base fee
- ~$0.000463/vCPU-minute, ~$0.000231/GB-minute
- Typical idle demo service: $5–10/month with occasional traffic

**Included:**
- Automatic HTTPS with Railway-issued certificate
- Custom domain support (CNAME to Railway URL)
- GitHub integration — push to `main` triggers a redeploy
- Built-in deploy logs, HTTP logs, and health check monitoring
- Environment variable management in the dashboard

### Option B — AWS App Runner
A managed AWS service that builds from a container image (ECR) or source code
and runs it with automatic scaling, health checks, and VPC integration.

**Pricing (approximate):**
- $0.064/vCPU-hour (active) + $0.007/vCPU-hour (paused/provisioned)
- $0.007/GB-hour
- ~$15–50/month at minimal always-on configuration

**Included:**
- Automatic HTTPS, custom domain via ACM
- IAM role attachment — no static credentials needed
- VPC connector for private networking to RDS/Aurora
- Native CloudWatch integration
- WAF attachment option

### Option C — AWS ECS Fargate
AWS's container orchestration service. Tasks run on Fargate (serverless) or EC2.
More control than App Runner but significantly more operational overhead.

**Pricing:** similar to App Runner but requires explicit task definition, cluster,
service, load balancer, and target group configuration.

**Considered and set aside** — the operational overhead of ECS does not fit the
demo tier goals. App Runner is the right AWS managed option for this workload.

## Decision

**Railway Hobby** — Option A — for the demo tier.

The key factors:

1. **Cost:** Railway Hobby costs ~$5–10/month for a demo-traffic service that
   sleeps when idle. App Runner's minimum always-on cost is ~$15–50/month even
   with minimal traffic. For a portfolio demo, the additional AWS cost is not
   justified.

2. **Simplicity:** Railway deploys from a `git push` with zero cloud configuration.
   There is no ECR, no IAM role for the build pipeline, no task definition, and
   no load balancer to configure. The total Railway setup is: one service, one
   `railway.toml`, one `Dockerfile`.

3. **Custom domain:** Bluehost DNS CNAME → Railway URL provides
   `reg-intel.demo.cloudkraft.com` without AWS Route 53, ACM certificate
   provisioning, or ALB configuration.

4. **Portfolio signal:** The deliberate demo/production split is itself the
   architecture story. Railway Hobby is an honest choice for demo scale —
   not a shortcut. Interviewers who ask "why not App Runner?" get a concrete
   cost comparison and a clear migration trigger.

### The sleep behaviour is a known trade-off

Railway Hobby services sleep after 30 minutes of inactivity. The cold start
is 10–30 seconds. This is documented in the README with a pre-warm instruction:
*"open the URL once, wait 30 seconds, then run the demo."*

This is acceptable for a portfolio demo. It is explicitly not acceptable for
production, where an SLA requires always-on availability.

## Production trigger

Migrate to AWS App Runner when **any one** of the following is true:

1. The service needs **always-on availability** — an SLA with uptime requirements
   cannot tolerate Railway Hobby's sleep behaviour
2. The service needs **private networking** — calls to Amazon Bedrock, RDS/Aurora,
   or other AWS services over a VPC instead of the public internet
3. The service needs to **attach an IAM role** — App Runner tasks can assume an
   IAM role; Railway containers cannot
4. The project moves to a **production engagement** — Railway Hobby is explicitly
   not a production deployment target for a regulated industry

## Migration path (when triggered)

The application code is unchanged. The migration is purely infrastructure:

```
Railway Hobby               →   AWS App Runner
─────────────────────────────────────────────────────────────────
railway.toml                →   apprunner.yaml (or Terraform)
Railway GitHub integration  →   ECR push + App Runner auto-deploy
Railway env vars            →   AWS Secrets Manager + App Runner env
Railway Postgres plugin     →   RDS/Aurora (already migrated to Neon)
Railway CNAME               →   ACM cert + App Runner custom domain
No IAM role                 →   aws_iam_role + instance attachment
$5–10/month                 →   $15–50/month (always-on, small instance)
```

### Terraform for App Runner (out of scope now, reference only)

```hcl
resource "aws_apprunner_service" "api" {
  service_name = "reg-intel-agent-api"

  source_configuration {
    image_repository {
      image_identifier      = "${aws_ecr_repository.api.repository_url}:latest"
      image_repository_type = "ECR"
      image_configuration {
        port = "8080"
      }
    }
    auto_deployments_enabled = true
  }

  instance_configuration {
    instance_role_arn = aws_iam_role.api_task_role.arn
    cpu               = "1024"
    memory            = "2048"
  }

  network_configuration {
    egress_configuration {
      egress_type       = "VPC"
      vpc_connector_arn = aws_apprunner_vpc_connector.main.arn
    }
  }
}
```

## Deployment comparison

| Concern | Demo (Railway Hobby) | Production (App Runner) |
|---------|---------------------|------------------------|
| Base cost | $0 | ~$15–50/month |
| Availability | Sleeps after 30 min idle | Always-on |
| Cold start | 10–30 s | ~1–3 s |
| Deploy trigger | Push to `main` | Push to ECR |
| Networking | Public internet | VPC private subnets |
| IAM auth | Static key (env var) | IAM role (instance) |
| Custom domain | CNAME via DNS | ACM + App Runner |
| Setup time | 15 minutes | 2–4 hours (Terraform) |
| Operational overhead | Near zero | Low (managed, not ECS) |

## Consequences

- **Positive:** Zero base cost, git-push deployment, minimal ops overhead.
  Custom domain works without AWS Route 53.
- **Positive:** The sleep behaviour is honest — it forces a pre-warm step that
  is a realistic demo constraint, not a hidden defect.
- **Positive:** Migration to App Runner changes only infrastructure, not
  application code. The Dockerfile, FastAPI app, and agents are unchanged.
- **Negative:** Not suitable for production SLAs. 30 s cold start is unacceptable
  for a customer-facing or internal production service.
- **Negative:** No IAM role attachment — requires static credentials for AWS
  services. Mitigated by using OpenRouter for models (no AWS credentials needed
  at all in the demo tier). See ADR-005.

## References
- ADR-002 — pgvector co-located vs. dedicated vector DB (DB hosting transition)
- ADR-005 — OpenRouter (demo) vs. Amazon Bedrock (production)
