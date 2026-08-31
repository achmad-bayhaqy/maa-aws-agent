---
name: log-diagnosis
description: "Use when searching CloudWatch logs for errors, investigating application issues, correlating events across services, or when a user reports a problem and you need to find relevant log entries. Also use when the user asks 'what errors happened recently', 'what's in the logs', '最近有什么错误', or '查下日志'. Uses CloudWatch Insights via CLI wrapper script — does NOT require any MCP server "
---

# Log Diagnosis — CloudWatch 日志诊断

通过 CloudWatch Insights 
<!-- MAA skill seed | source: aws-ops | origin: sample-aws-ops-skills-for-agents/log-diagnosis/SKILL.md -->
查询日志，匹配已知错误模式，输出结构化诊断报告。

## 执行模式

- **单服务 / 一两个 log group → inline**：直接按下面的工作流程走，主 agent 串行查询即可，最快。
- **多服务 / 全局扫描 → workflow 扇出**：当 scope 是多个服务或"所有服务"时，主 agent 先完成 Step 0 的 scope 确认（这步必须 inline，因为要向用户提问 + 从 account.yaml 解析 log group），再把解析好的 scope 交给 `assets/multi-service-scan.workflow.js` 并行处理。详见下方「多服务扇出」。

## 工作流程

### Step 0 — 确认范围（ASK FIRST）

MUST:
- 确认目标服务/项目 → 从 `environments/<account>/account.yaml` 的 service_catalog 定位
- 确认时间范围 → 默认过去 1 小时
- 确认 region → 默认 ap-northeast-1
- 如果用户说"所有服务"或"全局"，按 service_catalog 中的服务逐个扫描

SHOULD:
- 如果用户描述了具体症状（如"API 500 错误"），在 Step 2 选择更精确的查询模板
- **如果 scope 是多服务或"所有服务"**：完成本步 scope 确认（服务清单、时间窗、region、每个服务的 log group）后，不要 inline 逐个串行扫，改走「多服务扇出」章节的 workflow。Step 1–4 的逻辑由 workflow 内的 subagent 各自执行，主 agent 只负责最后渲染报告。

### Step 1 — 定位 Log Group

MUST:
- 读 `references/log-source-map.md` 获取服务 → log group 命名惯例
- 用 `aws logs describe-log-groups --log-group-name-prefix` 确认 log group 实际存在
- 检查 `storedBytes` > 0（group 存在但无数据则提示用户）

SHOULD:
- 如果 account.yaml 中有 `log_sources` 段，优先使用其中的映射
- 对未知服务，按 `log-source-map.md` 的自动发现流程操作

注意：不要凭猜测构造 log group 名。必须 describe-log-groups 确认。

### Step 2 — 执行查询

MUST:
- 从 `references/query-templates.md` 选择合适的查询模板
- 使用 `scripts/query-logs.sh` 执行查询（封装了异步 poll 流程）
- 不要自行编写 Insights 查询——用模板库中验证过的查询
- 如果模板库没有完全匹配的场景，基于最接近的模板修改，并在 Gotchas 中记录

脚本用法：
```bash
# 单个 log group
scripts/query-logs.sh "/aws/lambda/my-func" \
    'filter @message like /(?i)(error|exception|fatal)/ | fields @timestamp, @message | sort @timestamp desc' \
    1 ap-northeast-1

# 多个 log group
scripts/query-logs.sh --multi-groups "/aws/lambda/func-a,/aws/lambda/func-b" \
    'filter @message like /(?i)error/' \
    1 ap-northeast-1 --limit 50
```

SHOULD:
- 先用通用错误扫描（模板 1a）了解全局，再用服务专属模板下钻
- 对于时间范围 > 24h 的查询，先用短窗口（1h）确认模式再扩大

### Step 3 — 分析结果

MUST:
- 读 `references/error-patterns.yaml`，将查询结果与已知模式匹配
- 按严重程度分类：CRITICAL > HIGH > MEDIUM > LOW
- 按频率排序，找 top errors
- 检查时间分布——是突发（某个时间点集中出现）还是持续（均匀分布）

SHOULD:
- 对未匹配到已知模式的错误，用 aws-knowledge MCP 搜索相关文档
- 检查是否有关联——多个错误是否有因果关系（如 timeout 导致 5xx）

### Step 4 — 输出报告

MUST:
- 用 `assets/diagnosis-template.md` 格式输出诊断报告
- 包含：错误摘要、top errors（含原始日志片段）、时间线、受影响资源、建议

SHOULD:
- 提供下一步建议（需要下钻哪个服务、是否需要触发 aws-troubleshooting skill）

## 多服务扇出（Workflow 引擎，opt-in）

当 scope 是多服务/全局时，用 `assets/multi-service-scan.workflow.js` 把每个服务的诊断扇出到独立 subagent 并行跑。**为什么用 workflow 而不是 inline 循环**：每个服务的诊断不是单纯跑 CLI，而是要读懂日志、匹配 pattern、判断时间分布——属于"每单元需 LLM 推理"，且各服务彼此独立、Insights 查询慢，适合 `pipeline` 并行；纯指标聚合那种活儿才该留给 bash。

**触发约束**：Workflow 是 opt-in 的，用户需显式带"workflow"关键词、或主 agent 在多服务 scope 下主动提议并经用户同意后调用。不要在每次"查下日志"时自动 spawn。

**调用前提（主 agent 必须先做）**：
1. 完成 Step 0 的 scope 确认（问清服务、时间窗、region）。
2. 从 `environments/<account>/account.yaml` 的 `log_sources` 解析出每个服务的 log group 名（workflow 内会再用 `describe-log-groups` 验证存在性，但不要让它凭空构造名字）。
3. 把解析结果作为 `args` 传入。

**args 契约**：
```json
{
  "account_id": "123456789012",
  "region": "ap-northeast-1",
  "hours_back": 1,
  "skill_dir": "/path/to/sample-aws-ops-skills-for-agents/log-diagnosis",
  "services": [
    { "name": "payments-api", "log_groups": ["/aws/containerinsights/payments-eks/application", "/aws/eks/payments-eks/cluster"] },
    { "name": "orders-service", "log_groups": ["/aws/lambda/orders-service-*"] }
  ]
}
```
`log_groups` 可省略——省略时 scan subagent 会按 `log-source-map.md` 自动发现并 `describe-log-groups` 验证。

**两阶段 pipeline**：
- **Scan**（每服务一个 subagent）：跑 `query-logs.sh` → 对照 `error-patterns.yaml` 正则匹配 → 分级 + 判断时间分布 → 返回结构化 findings。强制：每条 finding 必须能追溯到查询输出，`sample_message` 是原始日志行，不许编。
- **Enrich**（仅对没匹配上 pattern 的错误）：查 aws-knowledge MCP 找可能原因 + 文档来源；MCP 查不到就如实说明、标 low confidence，不编。

**返回值**：`{ scope, services: [<scan 结果，可能含 enrichment>] }`。主 agent 拿到后用 `assets/diagnosis-template.md` 渲染最终报告——**报告渲染留在主循环**，因为要套模板做人类可读的判断和路由建议（DEGRADED → aws-troubleshooting 等）。

**护栏对齐**：workflow 内的"结论必须追溯数据源""禁止凭记忆报 AWS 数字"和 CLAUDE.md 报告纪律一致；Enrich 阶段的防幻觉规则与 aws-troubleshooting 一脉相承。

## 查询参考

- CloudWatch Insights 查询模板：`references/query-templates.md`
- 已知错误模式库：`references/error-patterns.yaml`
- 服务 → Log Group 映射：`references/log-source-map.md`

不要自行编写查询命令——用参考文件中验证过的模板。

## Automation Boundary

### auto-safe
- `aws logs describe-log-groups`（发现 log groups）
- `aws logs start-query` + `get-query-results`（CloudWatch Insights 查询）
- `aws cloudtrail lookup-events`（审计日志查询）
- 运行 `scripts/query-logs.sh`
- 生成诊断报告

### human-required
- 日志删除 / 清理（`delete-log-group`, `delete-log-stream`）
- Retention 变更（`put-retention-policy`）
- 订阅过滤器修改（`put-subscription-filter`）
- 任何写操作

## Gotchas
- CloudWatch Insights 查询有 15 分钟超时限制。大 log group + 长时间范围可能触发超时 → 缩短时间窗口重试
- `like /error/` 是大小写敏感的，必须用 `/(?i)error/` 做不区分大小写匹配
- Log group 不存在不代表服务不存在——很多 AWS 服务默认不开日志（RDS 慢查询、API Gateway、EKS control plane）
- EKS 容器日志的 log group 名取决于日志方案（Fluent Bit vs CloudWatch Agent），不要硬编码
- `query-logs.sh` 的 `--limit` 参数是追加到查询尾部的，如果原始查询已有 `| limit`，会覆盖
- stats 查询（如 `stats count(*) by bin(5m)`）不受 limit 1000 限制，但 fields 查询受此限制
