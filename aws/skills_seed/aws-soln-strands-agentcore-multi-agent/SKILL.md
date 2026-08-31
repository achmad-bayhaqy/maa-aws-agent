---
name: strands-agentcore-multi-agent
description: "Build a production-ready multi-agent system on AWS using Strands Agents + Amazon Bedrock AgentCore (Runtime + Gateway + Memory). Generates an Orchestrator agent that classifies user intent and routes to (a) MCP servers via Gateway, (b) specialized Strands sub-agents via direct invoke, or (c) Bedrock Knowledge Base. Output is a full CDK Python project + Strands agent containers "
license: MIT
metadata:
  version: "1.0"
  author: aws-solution-skills
---

# Strands × AgentCore Multi-Agent Builder

## Purpose
Gather requirements through conversation with the user, and generate a custom
multi-agent system based on **Strands Agents + Amazon Bedrock AgentCore**. A single
Orchestrator classifies intent and routes to the appropriate destination among
(1) MCP server tools, (2) specialized Strands agents, and (3) a Kn
<!-- MAA skill seed | source: aws-soln | origin: sample-aws-solutions-skills/strands-agentcore-multi-agent-skill/claude-code/skills/strands-agentcore-multi-agent/SKILL.md -->
owledge Base.

## Knowledge sources
All the architecture knowledge, patterns, and examples needed to run this Skill live in `shared/`:
- `shared/reference/architecture.md` — the overall architecture and the rationale behind decisions
- `shared/reference/agentcore-primitives.md` — deep dive on Runtime/Gateway/Memory/Identity (must-read)
- `shared/reference/decision-tree.md` — choosing integration patterns / Memory / model / region
- `shared/reference/aws-services.md` — Bedrock models, AgentCore region availability, cost
- `shared/reference/constraints.md` — 25 pitfalls (must-read)
- `shared/patterns/strands-agents.md` — Orchestrator + specialized agent code
- `shared/patterns/mcp-servers.md` — FastMCP server code
- `shared/patterns/cdk-stacks.md` — Runtime/Gateway/Memory/KB CDK stacks
- `shared/patterns/memory-hooks.md` — Strands HookProvider × AgentCore Memory
- `shared/patterns/auth-patterns.md` — Cognito JWT + OAuth2 M2M + SigV4
- `shared/patterns/frontend-pages.md` — React + Vite + Tailwind + shadcn + Amplify
- `shared/examples/{devops-assistant,data-analytics-agent,customer-support-agent}.md`

## Workflow

### Phase 1: Discovery (conversational requirements gathering)

```
1. External systems to integrate: Jira/GitHub/Salesforce/Zendesk/Notion, etc.
2. Integration pattern (per system) — table 1 in `shared/reference/decision-tree.md`
   - Stateless function call → MCP Server (Gateway target)
   - Multi-step reasoning required → Specialized Strands Agent (direct invoke)
   - Single AWS API call → Local Tool
3. Data source (for specialized agents): Athena+Glue / Aurora / DynamoDB / RDS
4. Knowledge Base: Web Crawler URL list / S3 prefix / none
5. Memory strategy: raw / user_preference / semantic / summarization
6. Region — verify AgentCore availability via AWS Knowledge MCP `aws___get_regional_availability`
   - Priority 1: us-east-1 / us-west-2
7. **LLM model** — catalog in `shared/reference/aws-services.md`
   - Orchestrator default: Claude Sonnet 4 (`us.anthropic.claude-sonnet-4-20250514-v1:0`)
   - For accuracy: Opus 4.7 / for cost: Haiku 4.5
   - Always re-confirm the latest ID via MCP `aws___search_documentation`
8. Cognito auth: USER_PASSWORD_AUTH + Amplify Authenticator by default. Specify if integrating an external IdP (Okta, Auth0).
9. Frontend hosting: Amplify Hosting / S3+CloudFront / local only
10. Cost/traffic estimate: queries per day, number of users
11. Whether external API tokens are available: Jira/GitHub/Slack, etc. → organize in `.env.example`
```

⛔ **GATE 1**: Summarize the gathered requirements → get user approval.

### Phase 2: Architecture Design

Decisions based on `shared/reference/decision-tree.md`:

1. **Stack composition**:
   - `OrchestratorAgentCoreStack` — always
   - `<Domain>McpAgentCoreStack` — one per MCP server integration
   - `<Domain>AgentStack` — one per specialized agent
   - `KnowledgeBaseStack` — when a KB is used
   - `AgentCoreGatewayStack` — only when there is ≥ 1 MCP server
2. **Gateway search type**: ≤ 5 tools → LITERAL / ≥ 6 → SEMANTIC
3. **Memory** strategy + expiry
4. Verify Bedrock model ID + region availability via MCP
5. Cost estimate (`shared/reference/aws-services.md`)

⛔ **GATE 2**: Present the design table + diagram → get user approval.

### Phase 3: Code Generation

Referencing `shared/patterns/*`, generate in the following order:

1. **Scaffolding**: `cdk-infra/{app.py, cdk.json, requirements.txt, .env.example}`
2. **CDK stacks** — `shared/patterns/cdk-stacks.md`:
   ```
   cdk-infra/src/stacks/orchestrator_agent_stack.py
   cdk-infra/src/stacks/<domain>_mcp_stack.py        [per MCP server]
   cdk-infra/src/stacks/<domain>_agent_stack.py      [per specialized agent]
   cdk-infra/src/stacks/knowledge_base_stack.py      [when a KB is used]
   cdk-infra/src/stacks/agentcore_gateway_stack.py   [MCP servers ≥ 1]
   ```
3. **Agent code** — `shared/patterns/strands-agents.md`:
   ```
   agents/orchestrator-agent/
     orchestrator_agent.py + main.py
     common/{aws_config, prompts, sigv4_auth, cognito_token_manager}.py
     memory/short_term_memory.py            ← shared/patterns/memory-hooks.md
     Dockerfile (LINUX_ARM64) + requirements.txt + .dockerignore
   agents/<domain>-agent/                   [optional]
     <domain>_agent.py + Dockerfile + requirements.txt
   ```
4. **MCP servers** — `shared/patterns/mcp-servers.md`:
   ```
   mcp-servers/<domain>-mcp/
     <domain>_mcp.py                        ← FastMCP + @mcp.tool
     Dockerfile + requirements.txt
   ```
5. **Frontend** — `shared/patterns/frontend-pages.md` (React + Vite + Tailwind + shadcn + Amplify, NO Cloudscape)
6. **Scripts**: `scripts/{deploy,destroy,check-prerequisites,generate-frontend-config}.sh`

⛔ **GATE 3**: `cdk synth` passes + verify IAM actions / region via AWS Knowledge MCP.

### Phase 4: Validate
- `cdk synth` clean
- Verify the IAM actions used (`bedrock-agentcore:*`) via AWS Knowledge MCP
- Map eval scenarios (`evals/<scenario>.md`)

### Phase 5: Deploy
1. Enable Anthropic model access (Bedrock Console → Model access → Request)
2. CDK bootstrap → sequential deploy (Orchestrator → MCPs → Sub-agents → KB → Gateway)
3. Refresh the frontend config.json with `scripts/generate-frontend-config.sh`
4. Frontend build + deploy (Amplify Hosting / S3+CF)
5. Smoke test: issue a Cognito JWT → POST to the Orchestrator endpoint → confirm the SSE stream

## Generation rules

- **CDK**: Python + `aws-cdk-lib==2.231.0` + `aws-cdk.aws-bedrock-agentcore-alpha==2.231.0a0` (lockstep)
- **Agents / MCP**: Python 3.13 + uv + **LINUX_ARM64** Docker
- **Strands**: `bedrock-agentcore` + `strands-agents` + `strands-agents-tools` are all required
- **Frontend**: React 18 + Vite + Tailwind v3 + shadcn/ui + Amplify Authenticator (Cloudscape ❌)
- **Bedrock models**: specify the cross-region inference profile prefix (`us.`/`eu.`/`apac.`/`global.`)
- **MCP tool docstrings**: include a "Use for queries like:" section — critical for semantic search accuracy
- Domain terminology: follow the user's language (Korean/English)
- External API tokens: SSM Parameter Store (`WithDecryption=True`) — no env vars

## Hard Constraints

See the 25 items in `shared/reference/constraints.md` for full detail. One-line summary:

1. **LINUX_ARM64** — specify the Runtime artifact platform
2. **CDK lockstep**: `aws-cdk-lib` and `*-alpha` must share the same major.minor (2.231.0 / 2.231.0a0)
3. **Gateway IAM**: add `bedrock-agentcore:*` + `secretsmanager:GetSecretValue on bedrock-agentcore-identity*` directly (CDK L2 does NOT add these automatically)
4. **OAuth2 credential provider** Custom Resource (boto3 `bedrock-agentcore-control`) — not provided by CDK L2
5. **Endpoint URL**: via Custom Resource at deploy time, `urllib.parse.quote(arn, safe="")`
6. **Reuse Memory after `list_memories()`** — avoid duplicates with the same name
7. **Strands `MCPClient`** must be used only inside a `with` block — streaming must also finish inside it
8. **`BedrockModel(model_id=...)`** accepts only a cross-region inference profile ID (`us.`/`eu.`/`apac.`/`global.`)
9. **MCP server**: port 8000, `transport="streamable-http"`, `FastMCP(stateless_http=True)`
10. **MCP tool docstring**: "Use for queries like:" section — core of Gateway semantic search
11. **SigV4 httpx Auth**: remove the `Connection` header before signing
12. **Cognito client_secret**: Custom Resource → Secrets Manager (cannot be a CFN export)
13. **Anthropic model access**: submitting the Bedrock console use-case form is mandatory (per account, once as root)
14. **Frontend `config.json`**: load via `fetch("/config.json")` (no import) — swappable per environment
15. **Memory `actor_id` / `session_id` stability**: Frontend MUST send `customer_id` from Cognito `idToken.sub`. Backend `resolve_customer_id()` extracts JWT sub as fallback + loud-warn UUID. **Never timestamp-based session_id** — UUID only. `shared/reference/constraints.md` #25.

## When to call MCP

| When | MCP | Call |
|---|---|---|
| Check region availability | AWS Knowledge | `aws___get_regional_availability(filters=["Amazon Bedrock AgentCore"])` |
| Get the latest model ID | AWS Knowledge | `aws___search_documentation` (e.g., "claude sonnet 4 inference profile id") |
| New AgentCore features | AWS Knowledge | `aws___recommend(url=<bedrock-agentcore page>)` |
| CDK construct prop | AWS Knowledge | `aws___read_documentation(url=<aws-cdk doc>)` |
| Validate generated code | (optional) CloudFormation | validate-template |
