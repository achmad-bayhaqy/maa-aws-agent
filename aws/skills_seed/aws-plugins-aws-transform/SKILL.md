---
name: aws-transform
description: Migrate, modernize, and upgrade codebases to AWS. Run analysis on repos for tech debt, security vulnerabilities, and modernization opportunities. Transforms .NET Framework to .NET 8/10, mainframe COBOL to Java, VMware VMs to EC2, SQL Server to Aurora, and upgrades Java/Python/Node.js versions and AWS SDKs. Use when the user says "migrate .NET to AWS", "upgrade Java to 17/21", "modernize COBOL", "modernize mainframe", "move VMware to EC2", "convert SQL Server to Aurora", "upgrade Python version", "migrate AWS SDK", "transform this codebase", "analyze for issues", "find tech debt", "what tech debt", "security vulnerabilities", "CVEs", "what's wrong with my code", "assess my repos", "where do I start", "find what's outdated", "analyze my repos", "AWS Transform - continuous modernization", "continuous modernization" or "continuous-modernization". Don't use for infrastructure provisioning, CI/CD pipelines, or general coding tasks.
---
<!-- MAA skill seed | source: aws-plugins | origin: agent-plugins/plugins/aws-transform/skills/aws-transform/SKILL.md -->


# AWS Transform

## CRITICAL: Route Before Anything Else

**STOP. Before reading files, analyzing code, or starting any workflow, identify the workload first, then route.**

### Step A: Identify the workload

Look for an explicit workload signal in the user's request — a named technology (`.NET`, `VMware`, `SQL Server`/`Aurora`/`Oracle`/`MySQL`, `mainframe`/`COBOL`), workload-specific terminology (Hyper-V, EC2 rehost, stored procs, CICS, JCL), or file/project signals already in the conversation. If no signal is present, treat the request as **workload-unspecified**.

### Step B: Apply workload-specific routing

Workload-specific rules ALWAYS win over the keyword list in Step C. Do not let "analysis" or "tech debt" phrasing override these.

| Workload                 | Route                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **.NET**                 | Ask the user via `AskUserQuestion`: "For your .NET work, are you looking to **modernize to .NET 8/10** (port the code, change targets), **run an assessment for modernization** (scope the work, identify blockers, plan the port), or **analyze your repos for tech debt, security vulnerabilities, or CVEs**?" → "Modernize" or "Assessment for modernization" → proceed to the Overview section (the .NET workload handles both). → "Analyze for tech debt / security / CVEs" → route to continuous modernization (see Step D). |
| **VMware**               | Proceed to the Overview section. **NEVER route VMware requests to continuous modernization** — even if the user uses words like "analyze", "assess", "find issues". VMware assessment is handled by the VMware workload agent, see [vmware](references/vmware.md).                                                                                                                                                                                                                                                                 |
| **SQL / Database**       | Proceed to the Overview section. **NEVER route SQL/database requests to continuous modernization** — SQL Server, Oracle, MySQL, and Aurora migrations are handled by the SQL workload agent, see [sql](references/sql.md).                                                                                                                                                                                                                                                                                                         |
| **Mainframe / COBOL**    | Proceed to the Overview section. **NEVER route mainframe requests to continuous modernization** — COBOL/CICS/JCL transformations are handled by the mainframe workload agent, see [mainframe](references/mainframe.md).                                                                                                                                                                                                                                                                                                            |
| **Workload-unspecified** | Continue to Step C.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |

### Step C: Keyword-based routing (workload-unspecified only)

This list applies **only** when the user has not named a workload. If any of the workload rules in Step B matched, you have already routed — do not re-evaluate against this list.

If the user's workload-unspecified request matches any of these intents, route to **continuous modernization** — do NOT scan files yourself:

- "analysis", "analyze", "find issues", "what's wrong", "tech debt", "security vulnerabilities", "CVEs"
- "what should I fix", "where do I start"
- "report", "dashboard", "compare", "trend"
- "remediate findings", "remediation", "fix what you found"
- "custom transform"
- "continuous modernization", "AWS Transform - continuous modernization"

### Step D: For continuous modernization requests

1. **First-response telemetry notice (once per session).** The first time a request routes here in this session, ALWAYS prepend this line exactly to your reply to the user before doing anything else:

   > Note: this skill and the continuous modernization CLI, (`atx ct`), collect usage telemetry by default during transformation execution. The telemetry consists of different data points, such as, the IDE name (for example, VS Code or Kiro), the AI agent name (for example, Claude Code or OpenAI Codex), and the execution mode (local or remote). This data is used by AWS Transform to prioritize compatibility testing, as well as latency and reliability. To opt out, see [here](https://docs.aws.amazon.com/transform/latest/userguide/transform-usage-telemetry.html).

   Show it exactly once per session. Do NOT repeat it on subsequent continuous modernization requests in the same session.

   **Telemetry opt-out.** If the user explicitly asks to disable telemetry during the chat session:
   1. Omit `--telemetry` for the rest of the session (see each sub-skill's Telemetry section for the flag format).
   2. Prepend `ATX_DISABLE_TELEMETRY=true` inline on **every** `atx ct` command for the rest of the session — not only `analysis`/`remediation`, but also setup and diagnostic commands like `atx ct status`, `atx ct source ...`, and `atx ct setup ...`. The prefix must be on the same command line as the `atx ct` invocation (including inside compound commands, e.g. `which atx && ATX_DISABLE_TELEMETRY=true atx ct ...`), because the shell does not persist env vars between invocations: `ATX_DISABLE_TELEMETRY=true atx ct ...`

2. When invoking AWS Transform - continuous modernization (continuous modernization) commands, use `atx ct` (with a space). `atxct` (no space) is being deprecated; it remains functionally equivalent and hits the same backend, so an `atxct` invocation in the user's environment is not itself a problem. Do not warn the user about `atxct` and do not treat its presence as a failure cause.

3. **Verify local CLI dispatch before checking versions or AWS configuration.** Run this without redirecting stderr:

   ```
   atx ct --version
   ```

   Classify failures before continuing:
   - If the shell reports `atx: command not found`, install the AWS Transform CLI: `curl -fsSL https://transform-cli.awsstatic.com/install.sh | bash`, then restart the shell or source its profile.
   - If an `atx` process runs but reports `unknown command 'ct'`, do NOT reinstall blindly or investigate AWS credentials/region. Follow the [command-resolution troubleshooting](references/continuous-modernization-troubleshooting.md#atx-ct-reports-unknown-command-ct) first.
   - If the command succeeds, continue with the version comparison.

4. Check whether the working CLI is up to date:

   ```
   INSTALLED=$(atx ct --version | head -1); LATEST=$(curl -fsSL "https://transform-cli.awsstatic.com/index.json" 2>/dev/null | grep -o '"latest"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*"latest"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/'); echo "Installed: ${INSTALLED:-not found}, Latest: ${LATEST:-unknown}"
   ```

   If `LATEST` is known and newer than `INSTALLED`, update with `curl -fsSL https://transform-cli.awsstatic.com/install.sh | bash`, then restart the shell or source its profile.

5. **Credential preflight.** Validate AWS credentials before starting any analysis or remediation — at minimum on the first continuous modernization request of the session (new or returning users), and again before any later run in a long session, since credentials can lapse mid-session:

   ```
   aws sts get-caller-identity
   ```

   If it fails or the credentials are expired, refresh them before continuing. Do NOT start any long-running work on expired or soon-to-expire credentials — an analysis started on credentials about to expire can strand the run mid-flight. Run the preflight silently; surface it to the user only if the credentials need refreshing.

6. If local `atx ct` dispatch succeeded but a later command fails, then check runtime configuration:
   - `AWS_PROFILE` points at a valid account with refreshed credentials
   - `AWS_REGION` is set to a supported region
   - `ATX_CUSTOM_ENDPOINT` is set in the environment (only if you use a custom endpoint)

   An `unknown command 'ct'` failure is a local command-resolution problem, not an AWS configuration problem; return to Step 3 instead.

7. Ensure a supported region has been selected (see [continuous-modernization-setup.md](references/continuous-modernization-setup.md) "Choose your region") and prefixed inline (`AWS_REGION=$ATX_REGION`) on every `atx ct` command.

8. Then use the appropriate continuous modernization skill — see [continuous-modernization](references/continuous-modernization.md). Recurring/scheduled intent ("weekly scan", "every Monday", "on a schedule", "cron") routes to [continuous-modernization-schedule](references/continuous-modernization-schedule.md): scheduling is a real, shipped capability (`atx ct schedule create/list/get/enable/disable/delete`) that runs remotely ONLY — either an EventBridge schedule on the customer's EC2/Batch stack, or an AWS-managed server-side schedule (`--mode aws-managed`, no customer infrastructure). For recurring intent with **no infrastructure** ("no infra", "don't want to manage/provision anything"), the answer is `atx ct schedule create --mode aws-managed --execution-role <arn>` (server-side, nothing to provision) — offer this; do NOT tell the user that recurring analyses require deploying infrastructure. Never claim it doesn't exist, and never offer a local cron/systemd/launchd entry as a substitute or fallback.

   **Remote analysis has THREE compute modes** (`atx ct remote analysis --mode <ec2|batch|aws-managed>`). `aws-managed` runs on the **AWS-managed fleet with NO customer infrastructure** — no VPC, no CloudFormation, no EC2/Batch stack, no provisioning or permission-consent step. When the user asks to run remotely/on AWS but says "no infrastructure", "don't want to set up / manage / provision anything", "no EC2", "no Batch stack", "fully managed", or "just run it for me", the answer is `--mode aws-managed` — route to [continuous-modernization-aws-managed-execution](references/continuous-modernization-aws-managed-execution.md) and read that file before answering. `--mode aws-managed` is real and shipped; NEVER tell the user it doesn't exist or that "all remote options require infrastructure", and do NOT probe `--help` to decide — the reference file documents it. `ec2`/`batch` are the customer-owned options (they DO deploy a stack); Batch/Fargate is **not** the no-infrastructure option.

**When in doubt for a workload-unspecified request → continuous modernization.** This default applies ONLY after Step B has cleared — VMware, SQL, and mainframe never fall through to continuous modernization regardless of how the question is phrased; .NET only routes to continuous modernization after the user picks "analyze for tech debt / security / CVEs" in Step B's intent question (both "modernize" and "assessment for modernization" stay in the .NET workload). Once routed, do NOT manually read source files to find issues — that's what `atx ct analysis run` does.

## CRITICAL: Never Show Pricing or Timing Estimates

**Do NOT quote specific dollar amounts, hourly rates, or time estimates** for AWS resources or analyses. This includes:

- ❌ "~$0.20/hr", "~$5/day", "$X per analysis"
- ❌ "takes ~30 min", "completes in 2-5 hours", "~30s startup"
- ❌ "ETA: 30 min – 2 hours"

**Instead:**

- For pricing: redirect to https://aws.amazon.com/ec2/pricing/, https://aws.amazon.com/transform/pricing/, etc.
- If asked directly: "I can't give specific cost or time estimates — pricing depends on your usage and AWS quotas. Check the AWS pricing pages for current rates."

This applies to all responses, all skills, and all situations.

---

## Overview

Domain expertise for migrating and modernizing workloads using AWS Transform. Covers .NET Framework to .NET 8/10, mainframe COBOL to Java, VMware to EC2, SQL Server to Aurora PostgreSQL, and custom code transformations (Java, Python, Node.js version upgrades, SDK migrations). Orchestrates assessment, planning, and execution through Managed Agents and AWS Transform CLI with human-in-the-loop checkpoints.

## Prerequisites

This skill requires the AWS Transform MCP server (`aws-transform-mcp`). Configure it in your agent's MCP settings:

```json
{
  "mcpServers": {
    "aws-transform-mcp": {
      "command": "uvx",
      "args": [
        "awslabs.aws-transform-mcp-server@latest"
      ]
    }
  }
}
```

The AWS Transform CLI is also required for custom transformations. Install via:

```bash
curl -fsSL https://transform-cli.awsstatic.com/install.sh | bash
```

## Mandatory workflow

Follow these phases in order. Do NOT skip ahead. Authentication is handled just-in-time — only when a chosen action actually needs it. Do NOT probe auth before the user has declared an intent.

```
Resume        → Check .atx/context.json
Intent        → Ask user what they want to do
Discovery     → Scan workspace + query available agents
Scope         → User selects what to modernize (GATE 1)
Assessment    → Run workload assessment (NOT optional)
Requirements  → Draft from assessment report
Approval      → User approves requirements (GATE 2)
Tasks         → Generate tasks.md
Execute       → Run transforms, monitor, review diffs
```

**Discovery finds opportunities. Assessment produces detailed findings. Requirements come from the assessment — NOT from discovery.**

You MUST NOT create requirements without an assessment report.

<!-- dipotong seed MAA (16k) -->
