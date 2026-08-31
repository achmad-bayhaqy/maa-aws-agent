---
name: data-platform-pipeline
description: "Build a production-ready serverless data lake pipeline on AWS. Creates S3 storage (3-bucket layout), Glue Catalog, ETL jobs, IAM roles, and Athena query layer. Use for AWS Data Lab builds, new data platform setup, or adding data sources to an existing lake. Triggers: 'build data pipeline', 'data lake setup', 'ingest data', 'ETL pipeline', 'Glue job', 'data platform', 'serverles"
---

# Data Platform Pipel
<!-- MAA skill seed | source: aws-soln | origin: sample-aws-solutions-skills/data-platform-pipeline-skill/claude-code/skills/data-platform-pipeline/SKILL.md -->
ine (AWS Serverless)

This skill builds the **ingestion → storage → catalog → query** layers of a serverless data platform. The output is a working CDK TypeScript project plus the Glue scripts and Athena DDL to run it. Downstream consumption (Quick Sight, dashboards, chat agents) is out of scope — this skill stops at "data is queryable in Athena."

The skill is opinionated: best practices are baked in, not presented as options. If a choice has a clear winner for serverless analytics on AWS, the skill picks it.

> **One deliberate exception.** If the catalog + query layers must live in a different region from storage (follow-up #8), the choice between the two mechanisms is **presented to the user, not decided** — it turns on a legal question (is data residency a mandate or a preference?) and a cost question that depends on customer-specific volume. See `reference/cross-region-query.md` §2.

---

## 🔴 CRITICAL RULES (never violate)

1. **S3 Tables catalog needs `--extra-jars` + `--user-jars-first: 'true'`** — Glue hard-fails (`Cannot find constructor for interface org.apache.iceberg.catalog.Catalog`) without the `s3-tables-catalog-for-iceberg-runtime` JAR. `--datalake-formats iceberg` alone is NOT enough.
2. **`spark.sql.extensions` is STATIC in Glue 5** — set ALL Spark/Iceberg config via the job's `--conf` in `defaultArguments`, NEVER via `spark.conf.set()` at runtime (fails with `Cannot modify the value of a static config`).
3. **No views on the S3 Tables catalog** — `CREATE VIEW` is unsupported (incl. cross-catalog refs from `AwsDataCatalog`). Use `mart_*` CTAS tables instead of `v_*` views on the Iceberg path.
4. **`DROP TABLE` (purge=false) is unsupported on S3 Tables** — use `DROP TABLE ... PURGE` or the S3 Tables API (`aws s3tables delete-table`).
5. **NEVER switch architecture due to tool versions** — upgrade the CLI/CDK instead. Tool versions are fixable in 2 minutes; architecture is permanent. Fall back to Hive only when the user explicitly opts in, or S3 Tables is genuinely unavailable in-region.

> Full failure modes, the supported/unsupported Athena DDL list, encoding rules, CDK gotchas, and the known-issues table → **`reference/gotchas.md`**.

---

> **Language**: Always respond in the language the user uses. Korean in → Korean out; English in → English out. Code and CDK output are always in English regardless of conversation language.

> **Execution Model**: This skill does NOT just generate code for the user to run manually. You ARE the builder — you have terminal access. Generate the CDK project, then:
> 1. Install dependencies (`npm install`)
> 2. Synthesize (`cdk synth`) — fix any errors before proceeding
> 3. Deploy (`cdk deploy --all --require-approval never`)
> 4. Run post-deploy verification (crawlers, queries, smoke tests)
> 5. If anything fails, diagnose, fix, and retry automatically
> 6. Only ask the user when a DECISION is needed (not for execution permission)
>
> The user provides business context and approves architecture decisions. YOUR role is to build, deploy, verify, and iterate until it works.
>
> | Agent does silently | Agent asks user |
> |---|---|
> | `npm install`, `cdk synth`, `cdk deploy` | "Deploy to production?" (if environment=production) |
> | Run crawlers, check schemas | "Column names don't match any known pattern — which mapping is correct?" |
> | Fix column mismatches (if obvious mapping) | "I found 3 possible interpretations. Which one?" |
> | Run smoke tests | Report results: "✅ All tables have data, views working" |
> | Auto-retry on transient errors | "This error persists after 3 retries: [error]. Need your input." |
> | Update ARCHITECTURE.md | — |

---

## Validation Gates

Five checkpoints where the build MUST stop. Two kinds, and the difference matters — see the Execution Model above:

- **⛔ AGENT-BLOCKING** — the agent verifies, fixes, and re-verifies **itself**. Do NOT ask the user for permission to proceed; ask only if a fix fails after retries. Never skip the check and never continue on a failure.
- **🛑 USER-BLOCKING** — the agent MUST present, stop, and **wait for an explicit answer**. These are business/legal/irreversible decisions the agent cannot make.

| Gate | Kind | When | Passes when | Detail |
|---|---|---|---|---|
| **GATE 1 — Scope & residency** | 🛑 USER | After §1 inputs + follow-ups, before ANY build | Storage pattern confirmed; `aws_region` set; **if #8 = yes**, `query_region` set AND the residency question answered *mandate* or *preference* AND the cross-boundary data-flow acknowledged | §1, `reference/cross-region-query.md` §2 |
| **GATE 2 — Preconditions** | ⛔ AGENT | Before `cdk synth` | All 5 precondition checks pass; LF not in strict mode (or user chose a path); IAM simulate shows no denies; tooling versions meet minimums | §1 ⚠️ MANDATORY block |
| **GATE 3 — Data model** | 🛑 USER | Before generating CDK/scripts | User has confirmed the base/mart table list, grains, and join keys | §1 Interactive data model design |
| **GATE 4 — Reconciliation** | ⛔ AGENT | After every pipeline run, before declaring success | Row counts + key SUMs reconcile against source within ~1%; every mart's declared grain matches its SQL; split-region: `query_region` COUNT == `aws_region` COUNT | §8 |
| **GATE 5 — Teardown intent** | 🛑 USER | Before any destructive command | User has explicitly confirmed data deletion, having been told what is deleted | §11 |

> **Gate discipline.** Never announce a gate as passed without running its check. If a gate fails, report *which* gate, *why*, and the fix — do not proceed to the next phase with a known failure and a note to fix it later. A skipped GATE 2 surfaces as an opaque deploy failure; a skipped GATE 4 ships wrong numbers that pass every structural test.

---

## Reference files (load on demand)

The core below is the default flow. Pull in a reference file when you reach its topic:

| File | When to read |
|------|-------------|
| `reference/iceberg-cdk.md` | Building the Iceberg path — full CDK (table bucket, IAM grants, Glue 5.x job + trigger, JAR upload, maintenance, teardown) |
| `reference/scripts.md` | Need any Glue job script, mart/view SQL, `run-views.py`, `smoke-test.py`, quality-check SQL, **dirty-data handling** (NFD filenames, mixed encoding, trailing-minus numbers, mixed date formats, join-key normalization, cross-source bridges, Excel normalization) |
| `reference/hive-pattern.md` | User opted into Hive — full path (3 buckets, crawlers, transform job, crawler bootstrap) |
| `reference/sap-sources.md` | Source is **SAP** (ECC / S/4HANA / BW / HANA) — native OData & HANA connectors, ODP delta, prerequisites, and the CSV-export fallback |
| `reference/vpc-connectivity.md` | JDBC source is on-prem or in a private subnet |
| `reference/cross-region-query.md` | Do the catalog + query layers need to be in a different region from storage (#8 = yes)? → read before building anything |
| `reference/gotchas.md` | Hit an opaque failure, or before generating Athena DDL on S3 Tables |

---

## 1. Prerequisites & Inputs

### Current state assessment (ask FIRST, before other questions)

Determine what already exists before any work. Present as an interactive choice:

```
What is the current state of your data platform?
  a) Starting from scratch — nothing exists yet
  b) Some infrastructure exists — I have an ARCHITECTURE.md or similar doc describing it
  c) Partial build — S3 buckets exist but no Glue/ETL yet
  d) Glue Catalog is set up — raw data is already cataloged, need ETL + views
  e) Pipeline exists — adding a new data source to existing platform
  f) Let me describe the current state: ___
```

- **(b):** Ask for the path to the architecture doc. Read it and incorporate existing state — do NOT recreate what exists.
- **(c)–(e):** Ask which components exist. Skip those steps.
- **(f):** Let them describe, then confirm your understanding before proceeding.

**Key principle:** Never deploy infrastructure that already exists. Always check first.

### Primary inputs — collect ALL before proceeding

| Input | Example | Notes |
| --- | --- | --- |
| `project_prefix` | `acme` | Lowercase, kebab-friendly. Naming convention for every resource. |
| `aws_region` | `ap-northeast-2`, `us-west-2` | Where the data lake lives — storage + ETL, and also catalog + query unless split (#8). |
| `query_region` (optional) | `ap-northeast-1`, `us-east-1` | **Defaults to `aws_region`.** Set only when #8 = yes. Owns the Glue resource link, Athena workgroup, and results bucket → `reference/cross-region-query.md`. |
| `source_type` | `jdbc` / `s3` / `sap` / `cdc` | Drives the decision tree in §3. `sap` → `reference/sap-sources.md` (native connectors exist — don't force it to `jdbc`). |
| `source_details` | see below | DB endpoint + Secrets Manager ARN, OR existing S3 path. |
| `business_questions` | "Monthly defect-rate trend, Top 5 defects by supplier" | Drives table selection and Athena view/mart design. |
| `downstream_consumer` | `bi` / `c360` / `ml` / `unknown` | **ASK THIS — do not make the user volunteer it.** Determines the mart contract. See "Downstream consumer" below. |

### Downstream consumer — ASK, then configure it yourself

> **Ask this right after `business_questions`, before the follow-up questions.** The downstream consumer changes the mart design, and retrofitting it means rewriting the mart jobs. The user should NOT have to know or state the technical requirements — you derive them.

```
What will consume this data?
  a) BI dashboards / natural-language Q&A (QuickSight, Amazon Quick)
  b) Customer 360 / identity resolution (unify customers across channels)
  c) ML / feature engineering
  d) Not sure yet — general-purpose analytics
```

Then apply the profile **silently** — announce the consequences, don't ask about them:

| Answer | What YOU configure without being told |
|---|---|
| **(a) BI** | Marts shaped to the business questions; `sum_safe_columns` declared; single-row KPI mart for cards. Consumption skill takes it from here. |
| **(b) C360** | 🔴 The full profile below. |
| **(c) ML** | Wide denormalized feature marts; keep raw grain; no aggregation-only marts. |
| **(d) Unknown** | Default BI shape; note in `ARCHITECTURE.md` that mart design may need revisiting. |

**On (b) C360 / identity resolution — apply ALL of these automatically:**

1. **Build a `mart_er_input` table** on Entity Resolution's 12-column contract (all lowercase): `variantid` (unique, ≤38 chars), `firstname`, `lastname`, `email`, `phone`, `dateofbirth`, `loyaltynumber`, `street`, `city`, `state`, `postalcode`, `country`, `sourcechannel`.
2. **Do NOT deduplicate customers across channels.** One row per (customer × source channel) — `variantid` = `V-{channel}-{id}`. Resolving those variants is Entity Resolution's job; if you merge them, the C360 build has nothing to do. **Say this to the user explicitly** — it looks like a bug otherwise.
3. **ASK the name order of EVERY source — it cannot be inferred.** `KIM MINHO` and `MINHO KIM` are indistinguishable as strings; only the source system knows its convention. Ask per source and pass it in: `family_first` (Korean-UI apps, SAP romanized exports), `given_first` (call-center free text, Western-facing forms), or `given_only` (app display names). Guessing produces opposite first/last names per channel, and a Name+Email rule then fails even with identical emails. Worked helper → `reference/gotchas.md`.
4. **Normalize phone country codes**, not just digits: `+82-10-…` and `010-…` must produce the same string.
5. **NULL out OTA/relay emails** (`*@booking.com`, `*@expedia*`) — they are per-booking aliases and will never match.
6. **Make the marts incremental** — `MERGE INTO` on a stable business key with an `updated_at` watermark, not a full CTAS rebuild. Customer attributes churn continuously.
7. **Add the ER export bridge** — Entity Resolution CANNOT read Iceberg/S3 Tables. Athena `UNLOAD` → Parquet → classic 2-level Glue table, on a dated prefix. Full mechanics + failure modes → `reference/gotchas.md` → "Downstream: AWS Entity Resolution".
8. **Tell the consumer to set `applyNormalization: false`** if any name may contain Hangul or other non-Latin script — Entity Resolution's own normalizer **strips Hangul entirely**, blanking the name fields. Record it as `er_apply_normalization: false` in `platform.yaml`.
9. **Record it** in `platform.yaml` as `downstream: {consumer: c360, er_input_table: ..., er_glue_table: ...}` so the C360 skill can discover it without being told.

> **If any source is in a VPC (Aurora, RDS, SQL Server on EC2, on-prem), create the VPC endpoints FIRST** — `s3` + `dynamodb` gateway, plus `s3tables` + `glue` + `secretsmanager` interface. Missing `s3tables` lets the job read every source successfully and then fail on the Iceberg write ~90 seconds in. Verified failure mode → `reference/vpc-connectivity.md`.

Then tell the user, in one line: *"I'll add a `mart_er_input` table shaped for Entity Resolution and keep channel variants unmerged — that's what the C360 step resolves."*

**`source_details` by type:**
- **JDBC**: `{ engine: "sqlserver"|"mysql"|"postgresql"|"oracle", host, port, database, secret_arn, tables: [...] }` — for Aurora/RDS, **probe the engine version rather than assuming one**: `aws rds describe-db-engine-versions --engine aurora-postgresql --region {region}` (a guessed version fails with `InvalidParameterCombination: Cannot find version …`).
- **Per-source name convention** (collect when the downstream is C360): `name_order: "family_first"|"given_first"|"given_only"` per source. Not inferable from the data — see the Downstream consumer section.
- **S3**: `{ bucket, prefix, format: "csv"|"json"|"parquet" }`
- **SAP**: `{ access: "odata"|"hana"|"s3_export"|"none_yet", instance_url, service_path, client_number, port, logon_language, auth: "basic"|"oauth2", entities: [...] }` — collect ALL of these for `odata`; a missing client number or service path blocks the build. See `reference/sap-sources.md` §2.1 for the customer-side prerequisite list.
- **CDC**: Out of scope — see §3. (Exception: **SAP ODP delta** is a connector option on a batch Glue job, not a streaming architecture — in scope, see `reference/sap-sources.md` §2.4.)

### Follow-up questions (ask after primary inputs, ONE AT A TIME, with a recommended default)

| # | Question | Recommended default |
|---|----------|---------------------|
| 1 | Storage pattern? | **Iceberg (S3 Tables)** — auto-compaction, ACID, time travel, schema evolution, no crawler. See §4. |
| 2 | Data volume? (rows/day + total) | **<1M rows/day, <100GB total** (DPU 2, standard for Data Lab) |
| 3 | Run frequency? (daily/hourly/weekly) | **Daily at 02:00 KST (17:00 UTC)** (off-peak) |
| 4 | Table relationships? (join columns) | **Infer from column names** (`product_code`, `supplier_id`, …; ask if ambiguous) |
| 5 | Code-to-name mappings? (status codes etc.) | **Yes, generate from source data** (query DISTINCT, propose mappings) |
| 6 | Partitioning strategy? | **Partition by date (year/month)** — optimal for time-series |
| 7 | Sensitive columns to mask/exclude? | **None** (add masking later via Lake Formation governance) |
| 8 | Catalog + query layer in a different region from storage? | **No — same region as storage** |

For question #1, present the two patterns explicitly:

```
Which storage pattern would you like to use?
  a) Iceberg / S3 Tables (recommended ✓) — automatic maintenance, ACID, time travel, schema evolution
  b) Hive (existing pattern) 

<!-- dipotong seed MAA (16k) -->
