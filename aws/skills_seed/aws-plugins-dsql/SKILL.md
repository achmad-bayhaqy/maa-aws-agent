---
name: dsql
description: "Build with Aurora DSQL — manage schemas, execute queries, handle migrations, diagnose query plans, diagnose cluster performance, load data, and develop applications with a serverless, distributed SQL database. Covers IAM auth, multi-tenant patterns, MySQL-to-DSQL and PostgreSQL-to-DSQL schema conversion, FK replacement code generation, OCC retry patterns, ORM migration (Django/EF Core/Hibernate/Rails), DDL operations, query plan explainability, system diagnostics via CloudWatch AAS, SQL compatibility validation, and bulk data loading. Triggers on phrases like: DSQL, Aurora DSQL, distributed SQL database, serverless PostgreSQL-compatible database, migrate to DSQL, DSQL query plan, DSQL EXPLAIN ANALYZE, DSQL ENUM, DSQL foreign key, DSQL OCC retry, DSQL multi-region, DSQL JSONB, DSQL GIN index, load into DSQL, load CSV into DSQL, bulk load DSQL, aurora-dsql-loader, DSQL slow, DSQL performance, DSQL wait events, DSQL AAS."
license: Apache-2.0
metadata:
  tags: aws, aurora, dsql, distributed-sql, distributed, distributed-database, database, serverless, serverless-database, postgresql, postgres, sql, schema, migration, multi-tenant, iam-auth, aurora-dsql, mcp, orm, enum, foreign-key, occ-retry, django, ef-core, dotnet, csharp, hibernate, rails, multi-region, schema-conversion, type-mapping, data-loading, system-diagnostics, wait-events, aas, performance, cloudwatch
---
<!-- MAA skill seed | source: aws-plugins | origin: agent-plugins/plugins/databases-on-aws/skills/dsql/SKILL.md -->


# Amazon Aurora DSQL Skill

Aurora DSQL is a serverless, PostgreSQL-compatible distributed SQL database. This skill covers direct query execution via MCP tools, schema management, migrations, multi-tenant isolation, IAM auth, and bulk data loading via `aurora-dsql-loader`.

---

## Reference Files

Load these files as needed for detailed guidance:

### Core:

| Reference                                                 | When to Load                                        | Contains                                                                                   |
| --------------------------------------------------------- | --------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| [development-guide.md](references/development-guide.md)   | ALWAYS before schema changes or DB operations       | Best practices, DDL rules, transaction limits, app-layer referential integrity             |
| [language.md](references/language.md)                     | MUST load for language-specific choices             | Driver selection, DSQL Connectors, connection code                                         |
| [access-control.md](references/access-control.md)         | MUST load for roles, grants, or sensitive data      | Scoped role setup, IAM-to-database role mapping                                            |
| [troubleshooting.md](references/troubleshooting.md)       | SHOULD load for errors or unexpected behavior       | OCC errors, connection failures, cluster state errors, token expiry, DDL rejection causes  |
| [dsql-examples.md](references/dsql-examples.md)           | Load for implementation examples                    | Multi-tenant schema examples, batch operations, FK validation patterns, connection pooling |
| [onboarding.md](references/onboarding.md)                 | User requests "Get started with DSQL"               | Interactive step-by-step guide                                                             |
| [occ-retry-patterns.md](references/occ-retry-patterns.md) | MUST load for OCC retry code or conflict mitigation | DSQL Connectors, manual retry pattern, idempotent design                                   |

### MCP:

| Reference                               | When to Load                                                    | Contains                                                           |
| --------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------ |
| [mcp-setup.md](mcp/mcp-setup.md)        | Always for MCP server guidance                                  | Setup instructions, 2 configuration options                        |
| [mcp-tools.md](mcp/mcp-tools.md)        | For MCP tool syntax and examples                                | Tool parameters, [input validation](mcp/tools/input-validation.md) |
| [dsql-lint.md](references/dsql-lint.md) | MUST load before running `dsql_lint` or processing external SQL | Tool reference, fix statuses, unfixable error resolution           |

### DDL Migrations:

| Reference                                                                                     | When to Load                                                 | Contains                                |
| --------------------------------------------------------------------------------------------- | ------------------------------------------------------------ | --------------------------------------- |
| [ddl-migrations/overview.md](references/ddl-migrations/overview.md)                           | MUST load for DROP COLUMN, ALTER TYPE, DROP CONSTRAINT       | Table recreation pattern, verify & swap |
| [ddl-migrations/column-operations.md](references/ddl-migrations/column-operations.md)         | DROP COLUMN, ALTER TYPE, SET/DROP NOT NULL/DEFAULT           | Column-level migration patterns         |
| [ddl-migrations/constraint-operations.md](references/ddl-migrations/constraint-operations.md) | ADD/DROP CONSTRAINT, VALIDATE CONSTRAINT, MODIFY PRIMARY KEY | Constraint and structural changes       |
| [ddl-migrations/batched-migration.md](references/ddl-migrations/batched-migration.md)         | Tables exceeding 3,000 rows                                  | Batching patterns, progress tracking    |

### MySQL Migrations:

| Reference                                                                           | When to Load                         | Contains                                 |
| ----------------------------------------------------------------------------------- | ------------------------------------ | ---------------------------------------- |
| [mysql-migrations/type-mapping.md](references/mysql-migrations/type-mapping.md)     | MUST load for MySQL → DSQL migration | Data type mappings, feature alternatives |
| [mysql-migrations/ddl-operations.md](references/mysql-migrations/ddl-operations.md) | Translating MySQL DDL to DSQL        | AUTO_INCREMENT, ENUM, SET, FK patterns   |
| [mysql-migrations/full-example.md](references/mysql-migrations/full-example.md)     | Complete MySQL table migration       | End-to-end example with decision summary |

### PostgreSQL Migrations:

| Reference                                                                         | When to Load                                                     | Contains                                           |
| --------------------------------------------------------------------------------- | ---------------------------------------------------------------- | -------------------------------------------------- |
| [pg-migrations/type-mapping.md](references/pg-migrations/type-mapping.md)         | MUST load for PG → DSQL type questions                           | C collation rules, NUMERIC precision, JSON/JSONB   |
| [pg-migrations/fk-replacement.md](references/pg-migrations/fk-replacement.md)     | MUST load for FK validation code generation                      | Tenant-scoped validate_fk_*() template, cascade    |
| [pg-migrations/index-conversion.md](references/pg-migrations/index-conversion.md) | MUST load for unfixable index diagnostics                        | GIN/GiST/BRIN → btree, partial, expression indexes |
| [pg-migrations/schema-objects.md](references/pg-migrations/schema-objects.md)     | MUST load for ENUM, materialized views, extensions, multi-schema | ENUM → CHECK, views, role/IAM mapping              |
| [pg-migrations/multi-region.md](references/pg-migrations/multi-region.md)         | Multi-region, active-active, or HA questions                     | Architecture, geographic partitioning              |

### ORM Guides:

| Reference                                                   | When to Load              | Contains                                                                 |
| ----------------------------------------------------------- | ------------------------- | ------------------------------------------------------------------------ |
| [orm-guides/overview.md](references/orm-guides/overview.md) | Migrating any ORM to DSQL | Adapter names, key gotchas for Django/EF Core/Hibernate/Rails/SQLAlchemy |

### Data Loading:

| Reference                                     | When to Load                                             | Contains                                                                                  |
| --------------------------------------------- | -------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| [data-loading.md](references/data-loading.md) | Planning or running bulk loads with `aurora-dsql-loader` | Fresh-vs-warm partitions, resume/retry, `--on-conflict` semantics, throughput diagnostics |

### System Diagnostics:

| Reference                                                                                 | When to Load                                                     | Contains                                                              |
| ----------------------------------------------------------------------------------------- | ---------------------------------------------------------------- | --------------------------------------------------------------------- |
| [system-diagnostics/workflow.md](references/system-diagnostics/workflow.md)               | MUST load at Workflow 12 entry — cluster performance diagnostics | Prerequisites, 5 diagnostic phases, temporal comparison, handoff      |
| [system-diagnostics/wait-events.md](references/system-diagnostics/wait-events.md)         | ALWAYS load when interpreting AAS results                        | Canonical DSQL wait event descriptions and investigation guidance     |
| [system-diagnostics/promql-patterns.md](references/system-diagnostics/promql-patterns.md) | Load when constructing PromQL queries                            | Reusable query templates for AAS breakdown, top-SQL, temporal compare |

### Query Plan Explainability:

| Reference                                                                                           | When to Load                                          | Contains                                                                  |
| --------------------------------------------------------------------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------------------------- |
| [query-plan/workflow.md](references/query-plan/workflow.md)                                         | MUST load at Workflow 9 entry — gates all other files | Trigger criteria, context disambiguation, routing, phased workflow        |
| [query-plan/plan-interpretation.md](references/query-plan/plan-interpretation.md)                   | MUST load at Workflow 9 Phase 0                       | DSQL node types, Node Duration math, estimation-error bands               |
| [query-plan/catalog-queries.md](references/query-plan/catalog-queries.md)                           | MUST load at Workflow 9 Phase 0                       | `pg_class`/`pg_stats`/`pg_indexes` SQL, correlated-predicate verification |
| [query-plan/guc-experiments.md](references/query-plan/guc-experiments.md)                           | MUST load at Workflow 9 Phase 0                       | GUC experiment procedures, 30-second skip protocol                        |
| [query-plan/report-format.md](references/query-plan/report-format.md)                               | MUST load at Workflow 9 Phase 0                       | Required report structure, element checklist, support request template    |
| [query-plan/query-rewrites-generic.md](references/query-plan/query-rewrites-generic.md)             | SHOULD load at Phase 0; sub-files on-demand           | Index of 10 generic rewrite patterns                                      |
| [query-plan/query-rewrites-dsql-specific.md](references/query-plan/query-rewrites-dsql-specific.md) | SHOULD load at Phase 0; sub-files on-demand           | Index of DSQL-specific rewrite patterns                                   |

---

## Choosing How to Connect: MCP vs CLI/psql

The `aurora-dsql` MCP server binds a **single cluster at startup** (`--cluster_endpoint`), so
using it for another cluster means editing `.mcp.json` and restarting the session.

- **Use the `aurora-dsql` MCP tools (`readonly_query`, `transact`, `get_schema`) ONLY when the
  server already targets the cluster you need.**
- **Otherwise — unconfigured, disabled, or bound to a different cluster — do NOT reconfigure it.**
  Use the CLI + `psql` path instead: [`scripts/psql-connect.sh`](../../scripts/psql-connect.sh)
  `<cluster-id> --region <region> --command "SELECT ..."` (mints an IAM token and runs via `psql`).
- **If you cannot confirm which cluster the MCP targets, confirm first or use the CLI/psql path** —
  running against the wrong cluster is worse than the check.

The doc-only MCP tools (`dsql_lint`, `dsql_*_documentation`, `dsql_recommend`) need no cluster.
The CloudWatch MCP (Workflow 12) takes `region`/`cluster_id` per call, so one running server can
query clusters in any PromQL-enabled region (pass each cluster's region on the call). Details:
[connectivity-tools.md](references/auth/connectivity-tools.md).

## MCP Tools Available

The `aurora-dsql` MCP server provides these tools:

**Database Operations:**

1. **readonly_query** - Execute SELECT queries (returns list of dicts)
2. **transact** - Execute DDL/DML statements in transaction (takes list of SQL statements)
3. **get_schema** - Get table structure for a specific table

**SQL Validation:**

1. **dsql_lint** - Validate SQL for DSQL compatibility and optionally auto-fix issues. Use before executing externally-sourced SQL.

**Documentation & Knowledge:**

1. **dsql_search_documentation** - Search Aurora DSQL documentation
2. **dsql_read_documentation** - Read specific documentation pages
3. **dsql_recommend** - Get DSQL best practice recommendations

**Note:** There is no `list_tables` tool. Use `readonly_query` with information_schema.

See [mcp-setup.md](mcp/mcp-setup.md) for detailed setup instructions.
See [mcp-tools.md](mcp/mcp-tools.md) for detailed usage and examples.

### AWS Knowledge MCP (`awsknowledge`)

Consult for verifying DSQL service limits before advising users. The numeric limits below are
defaults that may change — when a user's decision depends on an exact limit, verify it first:

| Limit                          | Default       | Verify query                       |
| ------------------------------ | ------------- | ---------------------------------- |
| Max rows per transaction       | 3,000         | `aurora dsql transaction limits`   |
| Max data size per transaction  | 10 MiB        | `aurora dsql transaction limits`   |
| Max transaction duration       | 5 minutes     | `aurora dsql transaction limits`   |
| Max connections per cluster    | 10,000        | `aurora dsql connection limits`    |
| Auth token expiry              | 15 minutes    | `aurora dsql authentication token` |
| Max connection duration        | 60 minutes    | `aurora dsql connection limits`    |
| Max indexes per table          | 24            | `aurora dsql index limits`         |
| Max columns per index          | 8             | `aurora dsql index limits`         |
| IDENTITY/SEQUENCE CACHE values | 1 or >= 65536 | `aurora dsql sequence cache`       |
| Supported column data types    | See 

<!-- dipotong seed MAA (16k) -->
