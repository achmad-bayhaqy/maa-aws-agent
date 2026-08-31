---
name: china-region-multi-account-routing
description: Tool selection and account routing for AWS China (aws-cn) MCP
  servers. Use this skill whenever the request mentions "中国区", "China",
  "cn-north-1", "cn-northwest-1", "Beijing", "北京", "Ningxia", "宁夏", or asks
  to inventory / list / count / map / audit resources that live in the China
  partition. It covers which tool to reach for first (a batch inventory tool
  before per-resource calls), which MCP server holds which account, that MCP
  tool names must be fully qualified as <server>_<tool>, and — critically — how
  to avoid answering a China-partition question with global-partition
  credentials.
---
<!-- MAA skill seed | source: aws-devops | origin: sample-skills-for-AWS-Devops-agent/devops-agent-cn-management/china-region-multi-account-routing/SKILL.md -->


# AWS China Region: Tool Selection and Account Routing

> **Adapt before use.** Replace `<CN_MCP_1>` / `<CN_MCP_2>` with your registered
> MCP server names and `<CN_ACCOUNT_1>` / `<CN_ACCOUNT_2>` with your account IDs.
> The agent matches on these literal strings, so leaving vague placeholders in
> place will weaken routing.

Each MCP server holds credentials for **one** `aws-cn` account, and their tool
sets may differ. They are not interchangeable — a request routed to one cannot
see resources in the other.

| MCP server | Account | Regions it can see | Extra tools |
|---|---|---|---|
| `<CN_MCP_1>` | `<CN_ACCOUNT_1>` | `cn-northwest-1` (Ningxia); also `cn-north-1` if a cross-region aggregator index exists | batch inventory |
| `<CN_MCP_2>` | `<CN_ACCOUNT_2>` | `cn-north-1` (Beijing) | `call_kubectl` if this account runs EKS |

**Account and region are separate axes.** One account can hold resources in both
China regions, and one MCP server can span both if its Resource Explorer index
is an `AGGREGATOR`. Do not assume one account means one region.

---

## Step 0 — Tool names must be fully qualified (read this first)

MCP tools are allowlisted under `<server name>_<tool name>`, **not** the bare
tool name. Calling the bare name fails with:

```
cn_list_inventory is not an allowlisted user tool and cannot be invoked.
```

That message reads like a permissions error but it is a **naming mistake**. Do
not conclude the tool is unavailable, and do not fall back to `gather_context`
or `use_aws`.

```
✅ <CN_MCP_1>_cn_list_inventory
✅ <CN_MCP_2>_call_kubectl
❌ cn_list_inventory
```

If a name is ever rejected, call `search_user_tools` with the bare name to get
the exact registered name, then retry with what it returns.

---

## Step 1 — Pick the right tool

This is where China-region questions most often go wrong. Choose by intent
(names shown bare for brevity — always prefix with the server name):

| The user is asking | Use | Notes |
|---|---|---|
| What resources exist / inventory / stocktake / count / "有哪些" | **batch inventory tool** | Start in summary mode |
| Topology, what is deployed, how the environment is laid out | **batch inventory tool** | Counts by service × type × region |
| Which CloudFormation stacks are deployed | **batch inventory tool** | Read the CFN stack names it returns |
| Where are the EKS / RDS / ECS / S3 resources | **batch inventory tool** | Filter by service |
| Full configuration of one **known** resource | `call_aws` | Only after you know it exists |
| Pod state, container logs, Kubernetes events | `call_kubectl` | Only on the server whose account runs EKS |
| Which CLI command would do X | `suggest_aws_commands` | |

### If your MCP server exposes a batch inventory tool

**No single AWS inventory API is complete in the China partition.** Measured on
a real `aws-cn` account: Resource Explorer returned 128 resources, the Resource
Groups Tagging API returned 176, and **only 27 overlapped**. They are
complementary — Resource Explorer sees untagged resources (CloudWatch log
groups, KMS keys, ECR repositories), while the Tagging API sees tagged ones
Resource Explorer misses (SageMaker, S3, ECS) and returns the
`aws:cloudformation:*` tags that carry deployment lineage.

A batch inventory tool should therefore merge both sources by ARN and report
which source saw what. Escalate through its modes; never jump straight to full
detail:

1. **summary** — bounded payload regardless of estate size. Counts by service,
   resource type and region, plus CloudFormation stack names and tag keys.
2. **list** — enumerate a subset. **Always pass a filter.** Measured at roughly
   300 bytes per resource, an unfiltered list of 5,000 resources is about
   375k tokens and will exhaust the context window.
3. **detail** — full records including every tag.

**Always read the coverage / completeness fields before answering.** A `LOCAL`
(non-aggregator) Resource Explorer index covers only one region, and a
still-building index returns partial data. Report the scope you actually saw;
never present a partial result as the complete estate.

> Querying a region with no Resource Explorer index does **not** raise an error
> — Resource Explorer auto-creates a `LOCAL` index on first access and returns a
> single-region result silently. **Absence of an error is not evidence of
> complete coverage.**

---

## Step 2 — Pick the right account

Apply in order; first match wins.

1. **Account named explicitly** ("the Beijing account", "宁夏那个账号", an
   account ID) → that server only.
2. **Region named, no account** → map the region to the server that holds it.
   If both accounts have resources in that region, query both and label the
   results, or ask which one is meant.
3. **Neither named** ("中国区的资源", "China AWS") → ambiguous. Either query both
   and merge with per-account labels (preferred), or ask one disambiguation
   question. Do not silently pick one.
4. **Comparison requests** ("对比两个账号", "两边配置一样吗") → always query
   both, present side by side.

---

## Never do these

- **Never answer a China-partition question using `use_aws` with a
  global-partition account.** This is the single most common failure mode and
  it has been observed in practice: the agent reached for the built-in
  `use_aws` tool with a global account and regions like `us-east-1` /
  `us-west-2` / `eu-west-1`, ran dozens of `describe_*` calls, and reported a
  well-formatted answer that had nothing to do with China — with no error to
  signal the problem. `aws-cn` is a **separate partition**: global credentials
  return `AuthFailure` there, and global regions contain none of these
  resources. China data is reachable **only** through the MCP servers above.
- **Never** treat `is not an allowlisted user tool` as "no permission". It means
  the tool name was not fully qualified. Prefix it with the server name (Step 0)
  and retry — do not fall back to `gather_context` or `use_aws`.
- **Never** `sts:AssumeRole` from one China account into the other unless you
  have confirmed a trust relationship exists. Typically there is none.
- **Never** assume the two accounts share IAM principals, VPCs, security groups
  or resource names. Any name collision is coincidental.
- **Never** silently fall back to the other account when one errors. If the user
  asked about account X and X is unreachable, report that failure — do not
  answer with data from a different account.
- **Never** call `call_kubectl` against a server whose account has no EKS
  cluster; that server does not register the tool.
- **Never** enumerate resource-by-resource with `call_aws` when the question is
  "what exists". It costs dozens of round trips and still misses untagged
  resources.

---

## Attributing cross-account results

Never merge results from two accounts without attribution. Every ARN, instance
ID and resource name must carry the account it came from — users have
independent access to each account, so an unattributed ARN is ambiguous or
worse, misleading.

**Side-by-side** (for narrow comparisons):

| Resource | `<CN_ACCOUNT_1>` (Ningxia) | `<CN_ACCOUNT_2>` (Beijing) |
|---|---|---|
| VPC CIDR | 10.0.0.0/16 | 10.1.0.0/16 |

**Grouped sections** (for lists):

```
### <CN_ACCOUNT_1> — cn-northwest-1
- i-0abc... (t3.medium, running)

### <CN_ACCOUNT_2> — cn-north-1
- i-0xyz... (t3.medium, running)
```

---

## Examples

**Input**: "中国区账号 `<CN_ACCOUNT_1>` 里有哪些资源？按服务汇总"
**Action**: `<CN_MCP_1>_cn_list_inventory()` in summary mode. Report counts by
service and by region, and state the coverage you saw. **Do not** use `use_aws`.

**Input**: "中国区部署了哪些 CloudFormation 栈"
**Action**: Batch inventory on both servers, read the CloudFormation stack
names, label each stack with its account.

**Input**: "北京的 EKS 集群里 pod 状态怎么样"
**Action**: `<CN_MCP_2>_call_kubectl("kubectl get pods -A")`.

**Input**: "宁夏账号有几个 RDS 实例，配置是什么"
**Action**: Batch inventory filtered to `rds` to find them, then
`<CN_MCP_1>_call_aws` per instance for full configuration.

**Input**: "两个中国区账号 VPC CIDR 有没有冲突"
**Action**: Batch inventory filtered to `ec2:vpc` on both, then
`call_aws describe-vpcs` for the CIDRs, compare, and label which CIDR belongs
to which account.
