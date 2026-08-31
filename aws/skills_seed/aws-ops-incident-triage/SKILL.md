---
name: incident-triage
description: "Use when an alarm fires, a user reports an outage or degradation, or when you need to quickly assess severity, identify affected services, and determine immediate next steps. Also use when the user says '有告警', '服务挂了', '出问题了', 'incident', or 'on-call'. Focuses on the FIRST 5 MINUTES: classify severity, scope blast radius, route to action. For deep diagnosis use aws-troubleshooti"
---

# Incident Triage — 快速分诊

前 5 
<!-- MAA skill seed | source: aws-ops | origin: sample-aws-ops-skills-for-agents/incident-triage/SKILL.md -->
分钟的决策框架：分类 → 定界 → 路由。不做深度诊断。

## 和其他 skills 的关系

- **incident-triage** 是入口——快速判断后路由到具体 skill
- SEV1/2 诊断 → **aws-troubleshooting**（深度排查）
- 需要看日志 → **log-diagnosis**
- 需要全面巡检 → **health-check**

## 工作流程

### Step 1 — 收集信号（< 1 分钟）

MUST:
- 如果是告警触发：
  - 读告警详情：`aws cloudwatch describe-alarms --alarm-names {name} --region {region}`
  - 记录 metric, threshold, duration, current value
- 如果是用户报告：
  - 确认症状（什么不工作了）
  - 确认开始时间（什么时候开始的）
  - 确认影响范围（谁受影响）
- 快速查当前告警全景：
  - `aws cloudwatch describe-alarms --state-value ALARM --region {region}`
  - 对账号的主要 region 都查一遍
- 查最近 15 分钟的变更事件：
  - `aws cloudtrail lookup-events --lookup-attributes AttributeKey=ReadOnly,AttributeValue=false --start-time {T-15m} --region {region}`

SHOULD:
- 检查 AWS Health Dashboard：`aws health describe-events --filter '{"eventStatusCodes":["open","upcoming"]}' --region us-east-1`
- 如果有 dashboard，快速看关键指标趋势

### Step 2 — 判定 Severity

MUST:
- 读 `references/severity-matrix.md` 做分类
- 基于证据判断，不基于猜测

分类速查：
- **SEV1**：服务完全不可用 / 数据风险 → 立即行动
- **SEV2**：服务降级 / 部分受影响 → 15 分钟内行动
- **SEV3**：异常观察 / 不影响服务 → 1 小时内行动

### Step 3 — 定界影响范围

MUST:
- 判断 blast radius：单资源 → 单服务 → 单 AZ → 单 region → 跨 region
- 检查关联服务（参考 aws-troubleshooting/references/investigation-framework.md 的依赖链表）

SHOULD:
- 用 health-check 做快速全局巡检确认是否有连锁影响
- 检查是否是 AWS 侧事件（Health Dashboard）

### Step 4 — 路由 + 输出

MUST:
- 输出 incident report（`assets/incident-report-template.md` 格式）
- 包含：severity, blast radius, 信号摘要, 初步判断, 建议操作

路由规则：
- SEV1 → 路由到 aws-troubleshooting（实时查 aws-knowledge MCP + SSM Automation runbooks）
- SEV2 + 需要日志 → 路由到 log-diagnosis
- SEV2 + 需要指标 → 路由到 health-check
- SEV3 → 路由到 health-check 做全面巡检

SHOULD:
- 对 SEV1/2 提供具体的缓解命令（但标记 human-required，不自动执行）

## 查询参考

- Severity 分类规则：`references/severity-matrix.md`
- 跨服务依赖链：`../aws-troubleshooting/references/investigation-framework.md`
- 具体服务排查 SOP：aws-troubleshooting skill（实时查 aws-knowledge MCP）

## Automation Boundary

### auto-safe
- `aws cloudwatch describe-alarms`（查告警状态）
- `aws cloudtrail lookup-events`（查最近变更）
- `aws health describe-events`（查 AWS 侧事件）
- describe / list / get 类资源查询
- 生成 incident report

### human-required
- 所有缓解/修复操作（重启 pod、扩容、回滚、修改配置）
- 开 AWS Support Case
- 通知其他人

## Gotchas
- CloudTrail 事件有 ~5 分钟延迟，最近的变更可能还没出现
- `aws health` API 只在 us-east-1 有全局事件，其他 region 只有 region-specific 事件
- INSUFFICIENT_DATA 告警不一定是问题——可能是新创建的告警还没收到足够数据
- 部署期间（rolling update）的短暂告警是正常的，要看是否在部署窗口内
- 不要在 SEV1 上花超过 5 分钟做分析——如果 5 分钟内找不到根因，升级
