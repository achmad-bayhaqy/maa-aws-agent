---
name: llm-gateway-governance
description: "Build a governed LLM gateway that lets internal developers use code agents (Claude Code, Codex) against Amazon Bedrock through a single control point — enforcing identity, per-user virtual keys, model/cost tiering, Bedrock Guardrails, managed web search, and tracing. Supports two developer-auth modes: IAM Identity Center organization-instance SSO (`org-sso`, permission sets + A"
license: MIT
metadata:
  version: "1.1"
  author: aws-solution-skills
  reference-implementation: llm-gateway-multi-agent
---

# LLM Gateway Governance

## Purpose

Generate a production-shaped **code-agent governance gateway** on AWS: a single LiteLLM proxy
(on ECS Fargate) that internal developers reach with **per-user virtual keys minted from a
verified identity**, with **Bedrock Guardrails**, **model/cost tiering**, **managed web search
(AgentCore)**, **network isolation**, and **observability**. The solution supports two
developer-auth modes: `org-sso` for IAM Identity Center organization instances using
permission-set roles, and `cognito-native` for environments where org-sso is not usable — an
Amazon Cognito User Pool is the sole identity source (no external IdP, no IdC federation) and
native Cognito User Pool Groups are the teams. `cognito-native` is the correct choice for an IdC
**account instance** (a m
<!-- MAA skill seed | source: aws-soln | origin: sample-aws-solutions-skills/llm-gateway-governance-skill/claude-code/skills/llm-gateway-governance/SKILL.md -->
ember/standalone account whose IdC cannot host a SAML customer-managed
application, so IdC-federated login is impossible at the AWS level) or any account with no usable
IdC at all. It lets an org give developers Claude Code / Codex access to Amazon Bedrock while
centrally controlling *who*, *which models*, *how much*, *what content*, and *with what audit
trail* — without requiring LiteLLM Enterprise.

This skill produces AWS CDK (TypeScript), Lambda (Python), the LiteLLM container config, and
developer-onboarding scripts, customized to the user's domain (custom domain or not, Langfuse or
not, which models, which tiers, **which region**, web search on/off).

## Knowledge sources

Read these before generating. All real knowledge lives in `shared/`:

- `shared/reference/prerequisites.md` — **check before Phase 1**: local tooling (Docker, Node, CDK CLI, AWS CLI), AWS account access/IAM, Bedrock model access, IdC readiness, custom-domain/Route53 needs — incl. the **two image-build paths** (local Docker default / CodeBuild when Docker can't run locally)
- `shared/reference/architecture.md` — the **10-stack** architecture, request lifecycle, and the "why"
- `shared/reference/decision-tree.md` — map Discovery answers → `config/dev.json` + stack choices (region, web search, Mantle)
- `shared/reference/aws-services.md` — service/model catalog (verify volatile IDs via MCP)
- `shared/reference/constraints.md` — failure modes & gotchas (bootstrap, edge TLS/certMode, Mantle guardrail, secrets, AgentCore web search, Mantle peering, Marketplace, region)
- `shared/reference/sso-setup.md` — IAM Identity Center **organization instance** Discovery + permission-set provisioning + generated `config.sso` block & AuthStack outputs
- `shared/reference/account-instance-setup.md` — **`cognito-native` setup** for IdC account instances (and any account without usable org-sso): why IdC federation is impossible on an account instance (no SAML customer-managed app), Cognito User Pool as sole identity source, User Pool Groups as teams, `cognito:groups` claim → LiteLLM team, and cross-platform `llmgw-login`
- `shared/reference/litellm-admin-guide.md` — **post-deploy operations**: Admin UI login, creating teams/users (`org-sso` permission set → team, `cognito-native` Cognito User Pool Group → team), checking logs/traces (LiteLLM UI, Langfuse, CloudWatch), applying per-team/per-key budgets, **offboarding** (revoke virtual keys — IdC/Cognito removal alone does NOT cut off access; see `constraints.md` → "Virtual-key lifetime ≠ SSO session")
- `shared/patterns/cdk-stacks.md` — full CDK source for the platform stacks + interfaces + config validation
- `shared/patterns/agentcore-websearch.md` — **AgentCore Web Search gateway** stack (Gateway + built-in `web-search` connector) + LiteLLM wiring (replaces Tavily)
- `shared/patterns/mantle-peering.md` — **Bedrock Mantle in us-east-1 via cross-region VPC peering** (MantleNetworkStack + MantlePeeringRoutesStack)
- `shared/patterns/lambda-handlers.md` — Token Service (org-sso ARN parse / cognito-native `cognito:groups`) + db-init Custom Resource (Python)
- `shared/patterns/litellm-gateway.md` — LiteLLM `config.yaml`, Dockerfile (base pin `v1.98.0`), entrypoint, and the Mantle **Bearer-token** auth (runtime-minted short-term Bedrock API key via `aws-bedrock-token-generator` + refresh callback — deterministic; a present Bearer bypasses the upstream-disputed v1.98.0 SigV4 fallback)
- `shared/patterns/developer-onboarding.md` — cross-platform client core `gateway_auth.py` (`setup`/`login`/`token`/`healthcheck`/`mcp-headers`; **both auth modes** — org-sso SigV4 included, so Windows works without bash) + thin `.sh`/`.ps1` launchers (every `.ps1` ends `exit $LASTEXITCODE`), Claude Code / Codex client config, MCP `headersHelper` registration
- `shared/examples/` — domain instantiations (enterprise SSO, domain-less PoC, economy tiering)

## Workflow

### Phase 1: Discovery (ask only what you don't know)
0. **Prerequisites check** — before asking anything else, confirm the operator has what `shared/reference/prerequisites.md` lists: Docker daemon running, Node/CDK CLI/AWS CLI v2 installed, deploy access to the target account, Bedrock model access requested (gateway region for Claude, us-east-1 for GPT-5.x/Mantle), and IdC enabled (required for the SSO path — see #6). Surface any gap now rather than discovering it mid-deploy. **Docker is the ONLY waivable item**: if `docker info` succeeds, use the default local `fromAsset()` build; if Docker **cannot run on this machine at all** (e.g. managed Windows laptop — WSL2/Hyper-V install needs admin + a reboot) set `litellm.imageBuild.mode='codebuild'` (conditional ImageBuildStack builds the image on native ARM in CodeBuild — `cdk-stacks.md` §4-1, 3-step deploy order). Everything else in the local toolchain is a **hard prerequisite** — do NOT offer a remote/EC2 deploy host as a workaround: running the skill off the operator's machine breaks operator-locality (the `albIngressCidrs` Discovery answer is the operator's real egress IP, unknowable from a remote host; the generated onboarding bundle — including the secret-bearing `admin-onboarding.html` — lands on the remote host and needs yet another transfer channel to reach anyone).
1. **Edge TLS (`certMode`)?** CloudFront is removed — the ALB is the edge, **always internet-facing, always SG CIDR-restricted**. Choose: `acm` (own a domain + Route53 hosted zone → HTTPS:443 with a public ACM cert; ✅ recommended / PROD) or `http` (no domain → HTTP:80, no cert; ⛔ the virtual key **and prompt/response bodies** travel plaintext on the wire — PoC-only, a GATE-1 acknowledgement item). **Both modes**: ask which source CIDRs may reach the ALB (`litellm.albIngressCidrs`, required — the SG allowlist is the primary access control). `0.0.0.0/0` with `http` means the plaintext endpoint is reachable from the whole internet → its own explicit GATE-1 acknowledgement.
2. **Models?** Which Claude / GPT(Mantle) models? **GPT tiers: `gpt-5.6-sol` (flagship coding/agentic, 1M context) / `gpt-5.6-terra` (balanced) / `gpt-5.6-luna` (economy/latency) / `gpt-5.5` (proven flagship) / `gpt-5.4` (proven economy).** ⛔ If any `gpt-5.6-*` alias is selected, tell the user now that it carries a **mandatory post-deploy Codex smoke test** before developer onboarding (real-deploy incident history: the Codex `namespace` tool-type 400 — since fixed server-side — plus open Codex-CLI issues like the ≥ 0.147 `functions`-namespace collision), and keep `gpt-5.5`/`gpt-5.4` in the model list as the fallback pair — see `shared/reference/constraints.md` → the GPT-5.6 gate. ⚠️ **Confirm the fallback pair actually exists in this account/region before promising it** (`aws bedrock list-inference-profiles`) — a real deploy had `gpt-5.6-*` and `gpt-oss-*` profiles but NO `gpt-5.5`/`gpt-5.4` at all; if absent, say so explicitly rather than offering a fallback that cannot be routed. **Per-team governance (optional)**: which teams need their own budget cap + model allowlist? In `org-sso`, each permission set maps 1:1 to a same-named LiteLLM team; in `cognito-native`, each Cognito User Pool Group name maps 1:1 to a same-named LiteLLM team. Discovery should capture the team names plus initial `models`/`max_budget` seeds. Onboarding additional teams later is then a console action (IdC permission set / Cognito group + LiteLLM Admin UI) only, never a code change. ("economy/standard" is just one illustrative naming — not a required split; name groups/permission sets/teams after real orgs/teams.)
   - **2b. Fable/Mythos-class data-retention opt-in (GATE-blocking).** If any requested model is a Fable/Mythos-class model (e.g. `claude-fable-5`), it is restricted to `allowed_modes: ["provider_data_share"]` — the account (per-region) data-retention mode must be set to `provider_data_share` or the model is blocked outright. Opting in means prompts/responses to that model **may be retained by Anthropic for 30 days and subject to human safety review**. This is a policy decision, so it **must be surfaced at GATE 1 and explicitly approved by the account owner** — never assume it. The opt-in is per-region and set only via the Bedrock control-plane REST API (no console UI). See `shared/reference/constraints.md`.
3. **Observability?** Langfuse (prompt/trace level) on, or CloudWatch only? Either way, the **CloudWatch usage dashboard** (ObservabilityStack, `dashboardEnabled`) ships by default: token usage by model & team, spend, latency, failures, per-user top-N and hourly-activity tables (Logs Insights over the `cloudwatch_usage` EMF records) — so per-user token accounting exists even without Langfuse. Langfuse adds the prompt/trace level on top.
4. **Region & account?** Target gateway region (`config.awsRegion`, **authoritative**). AgentCore Web Search, CDN, and Mantle are pinned to **us-east-1** — so confirm Claude access in the gateway region and GPT-5.x (Mantle) + Web Search access in us-east-1.
5. **Web search?** Use the managed **AgentCore Web Search Tool** (built-in `web-search` connector on an AgentCore Gateway, us-east-1)? Or no web search? (Tavily/3rd-party API keys are no longer used.)
6. **Identity and `authMode`?** Decide between `org-sso` and `cognito-native` before choosing the auth path. Detect IdC state first when possible:
   - `aws sso-admin list-instances --region <idc-region>` → capture `InstanceArn`, `IdentityStoreId`, `OwnerAccountId` (empty result = no IdC in this region).
   - `aws organizations describe-organization` → if available, compare the management account to `OwnerAccountId`.
   - **`OwnerAccountId == management account` (organization instance)** → `authMode="org-sso"` is available.
   - **Account instance** (`OwnerAccountId != management account`, or a standalone account instance), **or no usable IdC at all** → use `authMode="cognito-native"`. ⚠️ Do **not** attempt `account-sso`/IdC federation here: an IdC **account instance cannot host a SAML 2.0 customer-managed application** (AWS-confirmed), so Cognito↔IdC SAML federation is impossible at the AWS level. Its only customer-managed app type is OAuth 2.0 for *trusted identity propagation*, which is the inverse direction and cannot serve as a login/IdP. Never force an account instance down the permission-set or SAML-federation path.
   - Helper signal: org-sso relies on permission sets; `cognito-native` uses none. When the partner/payer owns the org IdC and you only have an account instance, `cognito-native` is the answer.

   **If `authMode="org-sso"`**: Is IdC enabled + in which region? Identity source (IdC directory vs external IdP)? **Permission set: create a NEW one for this gateway or reuse an existing one — and what name?** (Default to creating a new, uniquely-named one; a name match like `LlmGatewayUser` is NOT proof of ownership — never silently reuse/edit a pre-existing permission set, as it may belong to other groups/another gateway.) **Which group(s) or users to assign?** Optional tier mapping. These populate `config.sso`. See `shared/reference/sso-setup.md`.

   **If `authMode="cognito-native"`**: Do not use `aws sso login`, permission sets, or IdC/Identity Store at all — the Cognito User Pool is the sole identity source. Ask for/plan: team → Cognito **User Pool Group** names (each group name IS the LiteLLM team, 1:1), `teamGroupPrefix` (recommended `llmgw-`) to scope which groups count as teams, `multiGroupStrategy` (`require-single-team-group`), and optional `passwordMinLength` / `refreshTokenValidityDays`. **Also ask for the initial user(s)** — email + the team group to assign — because the AuthStack creates the pool and groups but **zero users**, and the full-path verification (login → token → virtual key) needs at least one group-assigned user; the agent creates them right after deploy (Phase 5). These populate `config.cognitoNative`. See `shared/reference/account-instance-setup.md`.

⛔ **GATE 1**: summarize requirements + the resulting `config/dev.json` (incl. `awsRegion`, `authMode`, `sso` or `cognitoNative` — for `cognito-native` also the **initial user(s)** to create post-deploy, `agentcore`, `mantle`, `litellm.certMode` + `litellm.albIngressCidrs` — with the plaintext acknowledgement if `http`, and — if any Fable/Mythos-class model is requested — the `provider_data_share` opt-in acknowledgement from #2b below); await confirmation.

### Phase 2: Architecture Design
- Apply `shared/reference/decision-tree.md` to choose `certMode` (acm/http), `enableLangfuse` (**acm only** — Langfuse UI needs a real domain/cert; http → CloudWatch only), tiers, capacity, region, web search, Mantle peering.
- **Verify model IDs + regional availability via AWS Knowledge MCP** (`aws___search_documentation`, `aws___get_regional_availability`) — never hard-code stale IDs. **Resolve each Claude model's actual inference-profile ID with `aws bedrock list-inference-profiles`; do NOT assume a `us.` prefix.** Recent (2026) models (Opus 4.8, Sonnet 5, Haiku 4.5, Fable 5) exist only as `global.` GLOBAL profiles — a `us.` call returns `The provided model identifier is invalid.` Confirm Web Search + Mantle PrivateLink in us-east-1.
- Produce the stack list (Network → Data → Guardrail → **AgentCoreGateway(us-east-1)** → LiteLLM [ALB edge per `certMode`] → Langfuse? [**acm only**] → Auth(`org-sso` API Gateway IAM authorizer or `cognito-native` Cognito User Pools authorizer) → Observability → **MantleNetwork(us-east-1)** → **MantlePeeringRoutes**) and a cost estimate. **There is no CdnStack — CloudFront is removed; the ALB is the edge.**

⛔ **GATE 2**: present architecture + cost; await confirmation.

### Phase 3: Code Generation
- Emit from `shared/patterns/`: `bin/app.ts`, `lib/*-stack.ts` (incl. `agentcore-gateway-stack.ts`, `mantle-network-stack.ts`, `mantle-peering-routes-stack.ts` — and `image-build-sta

<!-- dipotong seed MAA (16k) -->
