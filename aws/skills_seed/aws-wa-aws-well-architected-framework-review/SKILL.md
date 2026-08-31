---
name: aws-well-architected-framework-review
description: Perform a full AWS Well-Architected Framework review evaluating all 57 questions across 6 pillars by analyzing code, IaC, and configurations to produce evidence-backed findings with Eisenhower-prioritized remediation.
not_for: single-pillar deep-dives (use the specific pillar skill), learning WA (use wa-builder), ADRs (use architecture-decision-record), migration (use migration-readiness)
version: 2.3.0
---
<!-- MAA skill seed | source: aws-wa | origin: sample-well-architected-skills-and-steering/skills/aws-well-architected-framework-review/SKILL.md -->


# Well-Architected Review

## Step 1: Define the workload scope

Ask the user to describe the workload:

> What workload would you like me to review? Please share:
> - **Workload name** and brief description
> - **Code packages/directories** to analyze (IaC, application code, CI/CD configs)
> - **Business criticality** (critical, high, standard, low)
> - **Current pain points** (optional — anything you already know is problematic)

If the user has already provided architecture details or you are in a codebase with IaC, skip the prompt and proceed with discovery.

**IMPORTANT**: When no code or IaC is available to analyze (e.g., the user describes their architecture verbally), proceed with the review based on the information provided. Produce the full report using explicit statements in the architecture description as evidence. Treat omitted details as unknown, not as evidence that a control is absent. Mark unverifiable implementation details `Cannot Determine`, state what evidence would resolve them, and do NOT ask for code if the user has already given you enough context to perform a meaningful review.

Determine if a specialized WA Lens applies:
- SaaS, Serverless, Data Analytics, Machine Learning, IoT, Containers, Games, Financial Services, Healthcare

If a lens is obvious from the code (e.g., Lambda-heavy → serverless), note it and apply lens-specific questions.

## Step 2: Infrastructure Discovery

Analyze all infrastructure-as-code and deployment configurations in the codebase.

You MUST examine:
- CDK code (TypeScript, Python, Java, Go)
- CloudFormation templates (YAML, JSON)
- Terraform configurations (.tf files)
- SAM/Serverless Framework templates
- CI/CD pipeline definitions (CodePipeline, GitHub Actions, etc.)
- Monitoring configurations (CloudWatch alarms, dashboards)
- Deployment configurations (CodeDeploy, ECS deployment settings)

For each infrastructure component, document:
- Resource type, logical name, and configuration
- File path and line numbers where defined
- Security-relevant configs (IAM, encryption, network)
- Resilience configs (multi-AZ, backups, scaling)
- Cost-relevant configs (instance types, capacity mode)

Record the workload's **primary IaC dialect** (CDK, CloudFormation, Terraform, or SAM) — Step 6 emits a per-finding **Fix:** block in this dialect. When the workload has no IaC, note that fix blocks will fall back to AWS CLI commands.

You MUST create an architecture diagram in PlantUML showing:
- All major components and their relationships
- Data flows and external dependencies
- Trust and network boundaries

## Step 3: Application Architecture Discovery

Analyze application code for architectural patterns:
- Entry points (API handlers, event processors, scheduled tasks)
- Service communication patterns (sync/async, retries, timeouts, circuit breakers)
- Data access patterns (queries, caching, connection management)
- Error handling and resilience patterns
- Authentication/authorization logic
- Observability instrumentation (logging, tracing, metrics)

---STOP---
**Checkpoint**: Discovery complete — present findings before evaluation.

> Here is what I discovered about your workload:
> - **Infrastructure**: {summary of IaC resources found}
> - **Architecture patterns**: {key patterns detected}
> - **Scope**: {number of files/resources analyzed}
>
> **Shall I proceed with the full 57-question evaluation, or would you like to adjust the scope?**

Do NOT proceed past this point until the user explicitly confirms.
---

## Step 4: Evaluate EVERY WA Framework question with code evidence

**CRITICAL — DO NOT PRODUCE A SHORT REVIEW.** The single most common failure mode is citing 20-30 BPs and stopping. The reference corpus contains **307 BPs across 57 questions**; a real full review MUST evaluate ALL 307. Every BP receives one of five statuses: Implemented, Partially Implemented, Not Implemented, Not Applicable, or Cannot Determine (with rationale). If you find yourself with fewer than 200 BP citations, you have not finished the review. Iterate until every BP is addressed.

Assess the workload against ALL 57 questions in the Well-Architected Framework. For each question, provide:
- **Status**: "Implemented", "Partially Implemented", "Not Implemented", "Not Applicable", "Cannot Determine"
- **Evidence**: specific file paths and line numbers
- **Gaps**: what's missing or could be improved
- **Risk**: what could go wrong due to the gap

### Evidence sufficiency gate

Assign a status only after applying this gate:

- **Implemented** — explicit evidence demonstrates the complete BP.
- **Partially Implemented** — explicit evidence demonstrates part of the BP and identifies a concrete gap.
- **Not Implemented** — explicit evidence states the control is absent, or an authoritative and sufficiently complete source was examined where the control would have to appear and it is absent.
- **Not Applicable** — the BP is outside the workload scope; provide a workload-specific rationale.
- **Cannot Determine** — available evidence is missing, inconclusive, runtime-only, or outside the inspected scope. State the exact artifact, metric, configuration, or interview answer needed to decide.

Absence of evidence is not evidence of absence. A verbal description omitting a control, or code/IaC that is not authoritative for that control, MUST result in `Cannot Determine`, not `Not Implemented`. For example, "no backups configured" supports `Not Implemented`; no mention of control objectives or TCO analysis supports only `Cannot Determine`.

Leave severity blank for `Implemented`, `Not Applicable`, and `Cannot Determine`. For `Cannot Determine`, provide a verification action rather than a remediation finding. Do not convert uncertainty into a High or Critical finding.

The 6 pillars and their questions:
- **Operational Excellence** (OPS 1–11): Organization, observability, deployment risk, operational readiness, event management, evolution
- **Security** (SEC 1–11): Foundations, identity, permissions, detection, network/compute protection, data protection, incident response, app security
- **Reliability** (REL 1–13): Quotas, network topology, service architecture, distributed systems, monitoring, scaling, change management, backups, fault isolation, DR
- **Performance Efficiency** (PERF 1–5): Resource selection, compute, data/storage, networking, optimization process
- **Cost Optimization** (COST 1–11): Financial management, usage governance, monitoring, decommissioning, service selection, right-sizing, pricing models, data transfer, demand management, evolution
- **Sustainability** (SUS 1–6): Region selection, demand alignment, architecture patterns, data management, hardware selection, organizational processes

### Review depth

Before starting the evaluation, determine the review depth based on the user's request:

**Full review** (default when user says "WA review", "full review", "comprehensive"):
- Evaluate ALL 57 questions
- Load `references/pillars/{pillar-slug}.md` per pillar (see Step 4b for parallel subagent dispatch); each pillar file contains every question and every best practice for that pillar
- Cite specific BP IDs in findings (e.g., "SEC03-BP02: No permission boundaries defined")

**Quick review** (when user says "quick review", "high-level", "summary", or time-constrained):
- Evaluate all 57 questions at the QUESTION level only (do not load individual BP reference files)
- Use the pillar summaries above to assess each question based on what you find in the code
- Flag obvious gaps but do not exhaustively check every BP
- Faster, less detailed, still covers all pillars

**Pillar-scoped review** (when user asks for specific pillars, e.g., "review security and reliability only", "assess my security", "identify single points of failure", "optimize our costs"):
- Evaluate ONLY the questions for the requested pillars
- Load `references/pillar-playbooks/{pillar}.md` to apply domain-specific discovery steps (specialized evidence collection beyond generic infrastructure scan)
- Apply full-review depth (load BP reference files) for those pillars
- Skip all other pillars entirely — do not comment on them unless a critical cross-pillar issue is obvious
- Produce a pillar-focused report with domain-specific scorecard (e.g., Security: 6-domain scorecard; Reliability: SPOF table + testing plan)

Trigger phrases that indicate pillar-scoped review:
- Security: "security assessment", "IAM review", "encryption audit", "assess my security posture"
- Reliability: "reliability plan", "identify SPOFs", "assess disaster recovery", "fault tolerance review"
- Cost: "cost optimization", "right-sizing review", "reduce AWS spend", "cost assessment"
- Performance: "performance assessment", "latency analysis", "bottleneck identification"
- Sustainability: "sustainability review", "carbon footprint", "resource efficiency audit"
- Operational Excellence: "operational assessment", "CI/CD review", "observability audit"

**Score mode** (when user asks for "score", "grade", "scorecard", "matrix", or "just give me a number"):
- Analyze the codebase at the provided path
- Run a quick-scan pass across all 57 questions (no BP reference files loaded)
- Produce ONLY a structured scorecard + filtered findings — no full narrative report
- Respect depth parameter:
  - "critical only" → show only Critical findings
  - "critical and high" → show Critical + High
  - "all" (default if unspecified) → show Critical + High + Medium + Low
- Output format:

```markdown
## WA Score: {workload_name}

**Overall: {X.X}/5** | OPS: {}/5 | SEC: {}/5 | REL: {}/5 | PERF: {}/5 | COST: {}/5 | SUS: {}/5

| Pillar | Score | Critical | High | Medium | Low |
|--------|-------|----------|------|--------|-----|
| Operational Excellence | {1-5} | {n} | {n} | {n} | {n} |
| Security | {1-5} | {n} | {n} | {n} | {n} |
| Reliability | {1-5} | {n} | {n} | {n} | {n} |
| Performance Efficiency | {1-5} | {n} | {n} | {n} | {n} |
| Cost Optimization | {1-5} | {n} | {n} | {n} | {n} |
| Sustainability | {1-5} | {n} | {n} | {n} | {n} |

### Findings ({depth} and above)
| # | Pillar | Severity | Finding | Evidence |
|---|--------|----------|---------|----------|
| 1 | {pillar} | {Critical/High/...} | {one-line finding} | {file:line} |
...

### Summary
{1-2 sentence takeaway: overall posture + single most impactful action}
```

Trigger phrases: "score my app", "WA scorecard", "grade this", "give me a score matrix", "how does my architecture score"

If unclear, ask:

> Would you like a **full review** (deep BP-level analysis per question — thorough but longer), a **quick review** (question-level assessment — faster), or a **score** (just the scorecard + top findings)?

### Coverage strategy — MANIFEST-FIRST, THEN PILLAR FILES

**The purpose of a full review is comprehensive BP-level coverage.** To achieve this reliably, the reference corpus is provided in THREE layers:

1. **`references/manifest.md`** (~24 KB) — Lightweight catalog of every BP ID with 1-line titles. **ALWAYS load this file first** for any full review. It shows you the complete universe of 307 BPs to cite from.
2. **`references/pillars/{pillar-slug}.md`** (6 files, ~150-580 KB each) — Merged per-pillar reference containing ALL questions and full BP content for one pillar. Load these to get full BP detail (implementation guidance, anti-patterns, resources).
3. **`references/pillar-playbooks/{pillar}.md`** (6 files, ~3-5 KB each) — Domain-specific evidence-collection guide for one pillar: what resources to examine, what patterns to flag as HIGH RISK, and a pillar-specific report format. Each full-review subagent loads its pillar's playbook (Step 4b) so findings are backed by concrete file:line evidence rather than generic BP restatements.

### Mandatory loading pattern for a full review

**Step 4a — Load the manifest (MANDATORY, 1 Read call):**

```
Read: references/manifest.md
```

This gives you every BP ID and title in ~24 KB.

**Step 4b — Dispatch 6 parallel pillar subagents (MANDATORY for full coverage):**

**Why this pattern:** Empirical measurement shows that when a single agent tries to enumerate all 307 BPs in one response, it produces **20-60 findings and stops** — regardless of prompt strength, retrieval strategy (local files, MCP, or hybrid), or explicit "evaluate all 307" instructions. This is a stable behavioral equilibrium of the model's concision priors.

**The fix:** narrow scope per subagent. When one agent reviews ONE pillar, it naturally enumerates the pillar's 30-55 BPs. Dispatching **6 parallel subagents (one per pillar)** aggregates to **~307 BPs of coverage** — measured empirically at **100% (307/307)** in evals/study_mcp with **zero hallucinations**.

Dispatch all 6 Task calls in a single turn (parallel execution). **Each subagent MUST return a structured markdown table** so the top-level aggregator can merge findings verbatim without paraphrasing.

**Required return format (every subagent):**

```markdown
## {Pillar} Findings

| BP ID | Status | Severity | Evidence | Recommendation |
|-------|--------|----------|----------|-----------------|
| SEC03-BP02 | Not Implemented | High | No permission boundaries found in cdk/iam.ts | Add IAM permission boundaries per role |
| SEC04-BP01 | Partially Implemented | Medium | CloudTrail on, but no S3 access logging | Enable S3 server access logging |
| ...one row per BP evaluated in this pillar... |
```

**Row requirements:**
- One row per BP evaluated (target 30-55 rows per pillar; MUST cover every BP in the pillar file)
- Status: exactly one of `Implemented` / `Partially Implemented` / `Not Implemented` / `Not Applicable` / `Cannot Determine`
- Severity: `Critical` / `High` / `Medium` / `Low` (or blank for Implemented/Not Applicable/Cannot Determine)
- Evidence: specific file:line references when code was analyzed, an explicit quoted fact when reviewing verbally, or `Cannot Determine — need {specific evidence}`
- BP ID in canonical `PILLAR##-BP##` format only

Append this exact calibration rule to every pillar subagent prompt:

> Apply the evidence sufficiency gate: omitted or inconclusive information is Cannot Determine, not Not Implemented. Use Not Implemented only for an explicitly absent control or absence from an authoritative source where the control must appear. Leave severity blank for Cannot Determine and state the specific evidence needed.

**Dispatch template:**

```
Task(subagent_type="general-purpose",
     description="Review Operational Excellence",
     prompt="Read references/pillars/operational-excellence.md and references/pillar-playbooks/operational-excellence.md (domain-specific evidence-collection checklist: what to examine and what to flag as HIGH RISK), then review the following workload ONLY for the OPS pillar. Enumerate EVERY BP in the pillar file (all 30+ BPs) — do not filter to 'top issues'. Return findings as the mandatory markdown table (columns: BP ID | Status | Severity | Evidence | Recommendation) with one row per BP. Do NOT prepend narrative summary text before the table. Workload: {workload description + code}")

Task(subagent_type="general-purpose",
     description="Review Security",
     prompt="Read references/pillars/security.md and references/pillar-playbooks/security.md (domain-specific evidence-collection checklist), then review the workload ONLY for the SEC pillar. [same table format, every BP as a row] Workload: {workload}")

Task(subagent_type="general-purpose",
     description="Review Reliability",
     prompt="Read

<!-- dipotong seed MAA (16k) -->
