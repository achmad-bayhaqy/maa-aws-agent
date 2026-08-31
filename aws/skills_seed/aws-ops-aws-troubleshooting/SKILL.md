---
name: aws-troubleshooting
description: "Universal AWS troubleshooting framework. Activate when: any AWS resource is unhealthy, unreachable, or degraded; status checks fail; deployments fail; connectivity issues; performance degradation; unexpected errors or state transitions; the user says something is wrong with an AWS service. Works across ALL AWS services — EC2, ECS, EKS, RDS, Lambda, S3, VPC, IAM, etc. Does NOT e"
compatibility: >
  Requires aws-knowledge MCP (https://knowledge-mcp.global.api.aws) for
  real-time doc queries. AWS CLI for resource inspection. SSM for OS-level
  diagnostics where applicable.
---

# AWS Troubleshooting

One skill for all AWS services. Reasoning framework is here; service-specific
fac
<!-- MAA skill seed | source: aws-ops | origin: sample-aws-ops-skills-for-agents/aws-troubleshooting/SKILL.md -->
ts come from MCP at runtime.

## When to use

Any AWS issue where the console alone is insufficient — status checks, logs,
connectivity, performance, permissions, deployments, state transitions.

## Investigation workflow

### Step 0 — ASK FIRST (before any diagnosis)

MUST:
- Check if critical context is missing before querying or diagnosing:
  - Network issues → need VPC topology, subnet type, NAT/endpoint config
  - Container/task failures → need exit code, error message, logs
  - Connection timeouts → need source, destination, protocol, port
  - Performance issues → need instance type, workload pattern, timeline
- If missing, ASK the user. A wrong diagnosis from assumptions wastes more
  time than a clarifying question.

### Step 1 — Identify and collect

Determine the affected service and resource, then collect initial evidence.

MUST:
- Identify the service, resource ID, and region
- Run the service's `describe-*` / `get-*` APIs to capture current state
- Check for status checks, health checks, or equivalent (service-dependent)
- Check CloudWatch metrics for anomalies in the relevant namespace
- Read `references/stable-guardrails.md` to avoid known misdiagnosis traps

SHOULD:
- Check CloudTrail for recent API calls that may have caused the issue
- Check AWS Health Dashboard for service-level events
- Collect logs (CloudWatch Logs, system logs, console output) if available

### Step 2 — Query real-time documentation

MUST:
- Use `aws-knowledge` MCP `search_documentation` to find current troubleshooting
  guidance for the specific symptom. See `references/mcp-query-patterns.md`
- If the search returns an SOP (`sop_name` field), retrieve it with
  `retrieve_agent_sop` for step-by-step instructions
- For ANY specific number (IOPS, limits, quotas, timeouts, cooldowns):
  query MCP — NEVER rely on memorized values

SHOULD:
- Cross-reference re:Post Knowledge Center articles for the error message
- Check if the service has SSM Automation runbooks (`AWSSupport-Troubleshoot*`)
  that can automate diagnosis

MAY:
- Use `aws-knowledge` `recommend` tool on a relevant doc page to discover
  related troubleshooting content

### Step 3 — Diagnose

MUST:
- Read `references/hallucination-patterns.yaml` before concluding
- State the root cause with specific evidence (API response, metric value, log excerpt)
- Classify severity: CRITICAL (service down) / HIGH (degraded) / MEDIUM (suboptimal)

SHOULD:
- Check blast radius — is only one resource affected, or is it AZ/region-wide?
- Distinguish between AWS-side issues (status checks, service events) and
  customer-side issues (config, permissions, application)

### Step 4 — Remediate and report

MUST:
- Propose immediate mitigation with specific CLI commands
- Propose long-term prevention (alarms, auto-recovery, architecture changes)
- Output structured YAML report (see Output Format below)

SHOULD:
- Verify the fix worked (re-check status/metrics after remediation)

## Output format

```yaml
service: "<aws-service>"
resource: "<resource-id>"
region: "<region>"
root_cause: "<category> — <detail>"
evidence:
  - type: <api_response|metric|log|event>
    content: "<specific finding>"
severity: CRITICAL | HIGH | MEDIUM
blast_radius: "<single resource | AZ | region | account>"
mitigation:
  immediate: "<action with CLI command>"
  long_term: "<prevention strategy>"
sources:
  - "<MCP doc URL or SSM runbook name used>"
```

## Anti-hallucination rules

1. NEVER state service-specific numbers (IOPS, limits, quotas, defaults) from
   memory. Always query MCP first.
2. Always cite evidence: API response, metric, log excerpt, or MCP doc URL.
3. Read `references/hallucination-patterns.yaml` — these are patterns where
   LLMs consistently get AWS behavior wrong.
4. Read `references/stable-guardrails.md` — these are architectural facts that
   are safe to assert without querying.
5. Spend no more than 2 minutes on any single hypothesis. Pivot if inconclusive.
6. If MCP returns no relevant results, say so explicitly. Do not fabricate guidance.

## References

| File | Purpose |
|------|---------|
| `references/stable-guardrails.md` | Architectural facts that don't change — safe to assert |
| `references/hallucination-patterns.yaml` | Cross-service LLM mistake patterns |
| `references/mcp-query-patterns.md` | How to query aws-knowledge MCP effectively |
| `references/investigation-framework.md` | Detailed Phase 1/2/3 methodology for complex cases |
