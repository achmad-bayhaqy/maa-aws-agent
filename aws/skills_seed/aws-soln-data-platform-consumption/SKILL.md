---
name: data-platform-consumption
description: "Connect existing data sources to Amazon Quick (Quick Sight + chat agents) for visualization and natural language analytics. Works with any queryable data: Glue Catalog, Athena, Redshift, or S3. Sets up dashboards, SPICE caching, and AI-powered chat agents for business users. Triggers: 'Quick Sight setup', 'dashboard', 'Amazon Quick', 'data visualization', 'BI setup', 'chat agen"
---

# Data Platform Consumption (Amazon Quick)

This skill takes a querya
<!-- MAA skill seed | source: aws-soln | origin: sample-aws-solutions-skills/data-platform-consumption-skill/claude-code/skills/data-platform-consumption/SKILL.md -->
ble data source — typically Athena over a Glue Catalog, but optionally Redshift, S3, or RDS — and produces a working consumption layer: a Quick Sight account with datasets in SPICE, dashboards built around the customer's business questions, an Amazon Quick chat agent grounded in a semantic model, and Space-based access control for multi-team isolation. The output is a working CDK TypeScript project plus the topic/dashboard definitions to run it.

The skill is opinionated: it picks SPICE over direct query, pins SPICE refresh to off-peak, requires named synonyms for natural-language matching, and defaults to one Space per team. These can be overridden but the skill will not present them as menu options.

This skill is self-contained: it never assumes any other skill has run. It creates its own IAM role (`{prefix}-quicksight-role`) with minimum required permissions. If another stack already owns a role of the same name (e.g. the pipeline layer created a placeholder), see the import-vs-create handoff in `reference/iam-permissions.md`.

> **Naming note (as of 2026):** The product formerly known as "Amazon QuickSight" is now **Amazon Quick** (the platform), with **Quick Sight** as the BI feature (dashboards, SPICE, embedded analytics). Natural-language features (chat agents, Dataset Q&A) are part of Amazon Quick. **Topics** remain a Quick Sight feature for curating semantic models that chat agents read from. The AWS CLI/SDK namespace is NOT renamed — still `aws quicksight ...` and `quicksight.*`. This skill uses the new display names in prose and the legacy names in code/CLI.

---

## 🔴 CRITICAL RULES (never violate)

1. **The MANAGED service role — not your custom role — needs `s3tables:*` on the Iceberg path.** For a vanilla Athena-on-S3(+S3 Tables) dashboard, Quick Sight assumes an AWS-managed role (`aws-quicksight-s3-consumers-role-v0`, falling back to `aws-quicksight-service-role-v0`), NOT `{prefix}-quicksight-role`. The connection test passes while dashboard queries fail at render time. Patch the managed role.
2. **The Topic `Description` field is ≤ 256 chars.** Pasting the full persona/rules block fails the `create-topic` call. Condense to one sentence; encode agent quality via the semantic model (synonyms, calculated fields, named entities).
3. **`PhysicalTableMap`/`LogicalTableMap` keys + column IDs must match `[0-9a-zA-Z-]*`** — letters, digits, hyphens only. No underscores, no dots. Use `quality-inspections`, never `quality_inspections`.
4. **`permissions.actions` must be a complete predefined action set** (full Owner or full Reader set). A partial/custom subset is rejected with `Resultant state not supported`.
5. **`AWSQuickSightS3Policy` bucket allowlist is the #1 silent failure.** Missing buckets surface as the misleading `"Could not get query execution ID"`. The analytics-results bucket needs read **AND** write (with the "Write permission for Athena Workgroup" checkbox).

> Full IAM blocks, the managed-role patch, the S3 allowlist fix, and the Lake Formation grant → **`reference/iam-permissions.md`**. Topic 256-char handling + semantic model → **`reference/chat-agent.md`**. Dashboard schema gotchas + STRICT validation → **`reference/dashboard-patterns.md`**.

---

> **Language**: Always respond in the language the user uses. Korean in → Korean out; English in → English out. Code and CDK output are always in English regardless of conversation language.

> **Execution Model**: This skill does NOT just generate code for the user to run manually. You ARE the builder — you have terminal access. Generate the CDK project, then:
> 1. Install dependencies (`npm install`)
> 2. Synthesize (`cdk synth`) — fix any errors before proceeding
> 3. Deploy (`cdk deploy --all --require-approval never`)
> 4. Run post-deploy verification (Quick Sight CLI calls, dashboard validation, SPICE ingestion check)
> 5. If anything fails, diagnose, fix, and retry automatically
> 6. Only ask the user when a DECISION is needed (not for execution permission)
>
> The user provides business context (which questions to answer, which visuals look right) and approves architecture decisions. YOUR role is to build, deploy, verify, and iterate until it works.
>
> | Agent asks user (MUST stop and wait) | Agent does silently |
> |---|---|
> | **Architecture pattern choice** (Iceberg `s3tablescatalog` vs Hive `AwsDataCatalog`) | `npm install`, `cdk synth` |
> | **Region selection** (drives chat/Topics availability, SPICE capacity) | `cdk deploy` (non-production) |
> | **Dashboard plan** (sheets, visuals, structure) — BEFORE building | `cdk deploy` of `CfnDataSource` / `CfnDataSet` / `CfnDashboard` |
> | **Target metric values for gauges / reference lines** (Q10 — never fabricate) | Dataset creation + first SPICE ingestion (`create-ingestion`/`list-ingestions`) |
> | "Does this dashboard layout look right?" (after sharing a preview) | `--validation-strategy STRICT` dashboard validation + render-status check |
> | "Deploy to **production**?" (if environment=production) | Post-deploy KPI accuracy + layout-integrity validation (§7) |
> | Genuinely ambiguous synonym mapping ("I found 3 possible mappings. Which one?") | Auto-retry on transient errors; update `ARCHITECTURE.md` / `platform.yaml` |
> | "This error persists after 3 retries: [error]. Need your input." | — |
>
> Note: Features like AI commentary (Bedrock) are NOT proactively offered. They activate only when the user explicitly requests them (e.g., "add AI commentary"). See the reference-files routing table for keyword triggers.
>
> **KEY principle:** **Any decision that affects what the USER sees in the final dashboard MUST be approved first** (architecture pattern, region, dashboard plan, gauge targets, restricted topics). **Execution / infrastructure decisions are autonomous** (install, synth, deploy, IAM, SPICE refresh, dataset creation, validation). When unsure which side a decision falls on, ask: *"does the customer see the difference in the dashboard?"* — if yes, stop and confirm.
>
> **One genuine exception that DOES require user action:** the `AWSQuickSightS3Policy` bucket allowlist (🔴 rule 5). The console toggle for "QuickSight access to AWS services" cannot be flipped from CLI/CDK in all account configurations. If you detect the resulting "Could not get query execution ID" error after a dashboard creation, surface the exact remediation (console path + IAM policy patch fallback from `reference/iam-permissions.md`) and wait for confirmation before retrying.

---

## Reference files (load on demand)

The core below is the default flow. Pull in a reference file when you reach its topic:

| File | When to read |
|------|-------------|
| `reference/region-constraints.md` | Picking a region, hitting the chat/Topics availability gate, SPICE per-region capacity, or the identity-region error |
| `reference/quicksight-cdk.md` | Writing any CDK — `CfnDataSource`, `CfnDataSet` (Hive `relationalTable` or Iceberg `customSql`), `CfnRefreshSchedule`, `CfnDashboard`, native S3 Tables connector, RLS |
| `reference/dashboard-patterns.md` | Designing dashboards — domain layouts, the definition gotchas table, STRICT validation, the 3-step update flow |
| `reference/dashboard-definitions.md` | Building a dashboard? → read this for a complete working 4-sheet example — a real deployed, STRICT-clean definition (33 visuals across production-efficiency / quality / cost / delivery) annotated with every key pattern (KPI single-row dataset, gauge target, sparkline, TOP-N sorting) plus a "how to adapt" guide |
| `reference/chat-agent.md` | Building the chat agent — persona, topic creation, the 256-char limit, semantic model (synonyms/calculated fields/named entities), test cases |
| `reference/iam-permissions.md` | Any IAM — service role, managed-role patch, S3 allowlist, `s3tables:*` grants, Lake Formation, account/namespace setup, data-source discovery, Spaces/RLS |
| `reference/ai-commentary.md` | Need AI-generated commentary on the dashboard? → read `reference/ai-commentary.md` — Bedrock → InsightVisual `CustomNarrative` injection via `UpdateDashboard` + `UpdateDashboardPublishedVersion`, EventBridge/Lambda, no external DB |

---

## 1. Prerequisites & Inputs

### Current state assessment (ask FIRST, before other questions)

Determine what already exists before any work. Present as an interactive choice:

```
What is the current state of your analytics layer?
  a) Starting from scratch — Quick Sight not set up yet
  b) Architecture doc exists — I have an ARCHITECTURE.md or similar
  c) Quick Sight account exists — need datasets and dashboards
  d) Datasets exist in SPICE — need dashboards and/or chat agent
  e) Dashboards exist — adding chat agent / new datasets
  f) Let me describe the current state: ___
```

- **(b):** Ask for the path to the architecture doc. Read it and incorporate existing state — do NOT recreate what exists.
- **(c)–(e):** Ask which specific components exist. Skip those steps.
- **(f):** Let them describe, then confirm your understanding before proceeding.

**Key principle:** Never deploy infrastructure that already exists. Always check first.

### Ask FIRST — region

> Before `project_prefix`, before `data_source_type`, before anything else, ask:
> > "Which AWS region will you run Quick Sight in? (e.g., us-east-1, ap-northeast-2)"
>
> Region is first because it determines: the resource region, the SPICE capacity location, **chat-agent / Topics availability** (not all regions support them), and the QuickSight identity region. A wrong region invalidates almost every later decision. Pin it, then run the region availability gate (`reference/region-constraints.md` §2).

### Primary inputs — collect ALL before proceeding

| Input | Example | Notes |
|---|---|---|
| `aws_region` | `ap-northeast-2` | **Ask FIRST.** Where data lives + where Quick Sight runs. Chat features may need a different region — `reference/region-constraints.md`. |
| `data_source_type` | `athena` / `redshift` / `s3` / `other` | Drives the data source connector. |
| `data_source_details` | see below | Glue DB + workgroup, OR Redshift endpoint, OR S3 manifest. |
| `project_prefix` | `acme` | Optional. If set and matches `{prefix}_db` in Glue, the skill auto-discovers tables. |
| `business_questions` | "Monthly defect-rate trend, Top 5 defects by supplier, next-month defect-rate forecast" | Drives dashboards, topics, chat agent test cases. |
| `target_users` | "5 quality-team members, 2 executives" | Drives Space layout and persona scoping. |

**`data_source_details` shape by type:**
- **Athena**: `{ glue_database, workgroup, results_bucket }`
- **Redshift**: `{ endpoint, port, database, secret_arn, vpc_id, subnet_ids[] }` — VPC connection setup in `reference/quicksight-cdk.md` §6.
- **S3**: `{ manifest_uri, format: "csv"|"tsv"|"json" }` — the S3 manifest connector does NOT support Parquet; for Parquet use `athena` instead (`reference/quicksight-cdk.md` §5).
- **Other**: `{ description }` — recommend Athena federated query as a bridge.

### Follow-up questions (ask after primary inputs, ONE AT A TIME, with a recommended default)

| # | Question | Recommended default |
|---|----------|---------------------|
| 1 | SPICE refresh frequency? (daily / hourly / real-time via direct query) | **Daily 04:00 KST (19:00 UTC)** — just after the pipeline's nightly ingest (~03:00 KST), so SPICE is fresh before business hours (§6). |
| 2 | Chat agent response language? | **Korean** (match the target users' primary language) |
| 3 | Dashboard style? (executive summary / detailed operational / both) | **Both** — one executive summary sheet + one operational detail sheet per business question |
| 4 | Existing dashboards/reports to replicate? | **No — build fresh** (optimized for Quick Sight's native visual types) |
| 5 | How many Spaces (isolated groups)? | **1 Space** (single team; add more as the user base grows) |
| 6 | Chat agent restricted topics? | **Refuse predictions/forecasts** ("next-month forecast" → "Forecasting is not supported") |
| 7 | Dashboard format? (KPI summary / detailed operational / trend / comparison) | **KPI summary + trend** (one KPI-card sheet, one trend sheet with time-series + comparisons) |
| 8 | What insights do you expect from the data? (I can propose based on structure) | **Structure-based proposals** — scan tables/columns and suggest time-series (date+numeric), comparisons (category+metric), anomaly candidates (high-variance), TOP-N rankings (dimension+metric) |
| 9 | What data period do you have for trend analysis? (day/week/month/quarter) | **Check the distinct date count in the data and pick the right grain** — single-month data makes a "monthly trend" a single point; query the actual distinct-date count before choosing the trend grain. |
| 10 | Is there a target/threshold for each key metric? (e.g., utilization 85%, defect rate 2%) | **Use it if provided, otherwise proceed with no baseline** — gauges, reference lines, and conditional colors all need a real target. NEVER substitute a meaningless column (e.g. a line count) as a gauge target. |

When the user picks "get proposals" on Q8, enumerate columns from the dataset and propose 4–6 specific insights using those patterns. Don't propose insights for columns that don't exist — confirm against `aws glue get-table` first.

> **Q9 matters because** single-period data silently degrades trend visuals to one point — confirm the real date range (`SELECT COUNT(DISTINCT date_col)`) and pick day/week/month/quarter to match. **Q10 matters because** a gauge or reference line with no real target tempts the agent to fill garbage (a gauge "utilization target" was once set to a `line_count` of 11 instead of 85%). No target → omit the gauge/reference line, don't fabricate one.

> **Interaction pattern:** present each question as a one-at-a-time multiple-choice prompt with the default highlighted. Do NOT dump all questions at once. If the user says "just use the defaults", accept ALL defaults and proceed.

### Account preconditions — run before building

```bash
# 1. Active identity matches the target account
aws sts get-caller-identity

# 2. Quick Sight account status (CLI still uses 'quicksight')
aws quicksight describe-account-settings --aws-account-id $(aws sts get-caller-identity --query Account --output text) 2>&1 \
  || echo "Quick Sight not yet enabled in this account"

# 3. Chat / Topic availability in the target region — see region-constraints.md
aws quicksight list-topics --aws-account-id $(aws sts get-caller-identity --query Account --output text) --region {aws_region} 2>&1 \
  || echo "Amazon Quick Topics may not be available in this region"

# 4. If data_source_type=athena: validate workgroup + database exist
aws athena get-work-group --work-group {workgroup} --region {aws_region}
aws glue get-database --name {glue_database} --region {aws_region}

# 5. SPICE capacity in the TARGET region (per-region; describe-account-settings does NOT return capacity).
#    See region-constraints.md §3 — the first dataset creation in a fresh region fails if capacity is 0.
aws quicksight describe-account-settings --aws-account-id {account_id} --region {aws_region}
```

If Quick Sight is not enabled, the skill can enable it (Enterprise edition) — but only after explicit user confirmation, since it has cost implications. Account/namespace/user setup → `reference/iam-permissions.md` §7.

**Region

<!-- dipotong seed MAA (16k) -->
