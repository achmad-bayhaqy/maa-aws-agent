---
name: health-check
description: "Use when performing routine environment checks, validating service health before or after deployments, checking SLO compliance, or generating a health status report. Also use when the user asks '环境健康么', '服务状态怎样', '部署前检查', or 'SLO 达标了么'. Queries CloudWatch metrics directly — works even without alarms configured."
---

# Health
<!-- MAA skill seed | source: aws-ops | origin: sample-aws-ops-skills-for-agents/health-check/SKILL.md -->
 Check — 主动健康巡检

直接查 CloudWatch 指标判断服务健康，不依赖告警配置。

## 和其他 skills 的关系

- **env-discovery**: "有什么资源" → **health-check**: "资源健不健康"
- **health-check** 发现异常 → **log-diagnosis** 下钻日志 → **aws-troubleshooting** 深度排查
- **health-check** 发现告警 → **incident-triage** 分诊

## 工作流程

### Step 0 — 确认范围

MUST:
- 确认巡检范围：全局 vs 单服务
- 确认 region（默认 ap-northeast-1）
- 确认时间窗口（默认最近 1 小时）

### Step 1 — 执行健康检查

MUST:
- 运行 `scripts/check-health.sh <account-id> <region>` 获取健康摘要
- 如果单服务，加 `--service <name>` 过滤
- 脚本自动发现 EKS / RDS / ALB 资源并查指标

SHOULD:
- 如果脚本返回 UNKNOWN（无指标数据），提示用户可能未开启 Container Insights 或相关监控

### Step 2 — 分析指标

MUST:
- 读 `references/health-metrics.md` 了解各指标含义和阈值
- 判断每个服务的健康等级：HEALTHY / DEGRADED / CRITICAL / UNKNOWN
- 如果有 SLO 定义，对比实际值 vs 目标。**优先读 `references/slo-targets.local.yaml`**（你环境的真实目标，已 gitignore），不存在时回退到示例 `references/slo-targets.yaml`

SHOULD:
- 关注趋势——指标在恶化还是稳定
- 检查多个指标的关联（如 CPU 高 + 内存低 可能是内存泄漏导致 GC 频繁）

### Step 3 — 输出报告

MUST:
- 用 `assets/health-report-template.md` 格式输出
- 包含：总体状态、每服务健康状态、异常详情、告警状态、SLO 达标情况
- 突出 CRITICAL 和 DEGRADED 的服务

### Step 4 — 联动建议

SHOULD:
- DEGRADED/CRITICAL → 建议使用 log-diagnosis 查日志
- 有告警触发 → 建议使用 incident-triage 分诊
- 需要深度排查 → 路由到 aws-troubleshooting（实时查 aws-knowledge MCP / SSM Automation）
- 无数据（UNKNOWN）→ 建议开启监控（Container Insights、RDS Enhanced Monitoring 等）

## 查询参考

- 各服务健康指标和阈值：`references/health-metrics.md`
- SLO 目标定义：`references/slo-targets.local.yaml`（真实，gitignore）优先，否则 `references/slo-targets.yaml`（示例模板）

## Automation Boundary

### auto-safe
- `aws cloudwatch get-metric-data` / `get-metric-statistics`
- `aws cloudwatch describe-alarms`
- `aws eks list-clusters` / `describe-cluster`
- `aws rds describe-db-instances` / `describe-db-clusters`
- `aws elbv2 describe-load-balancers` / `describe-target-health`
- 运行 `scripts/check-health.sh`
- 生成健康报告

### human-required
- 无（纯只读 skill）

## Gotchas
- Container Insights 不是默认开启的——如果 EKS 指标全部 UNKNOWN，不是集群有问题，是没开监控
- RDS FreeableMemory 在 Aurora 上的行为和标准 RDS 不同——Aurora 主动使用内存做缓存，低 FreeableMemory 不一定是问题
- CloudWatch 指标有 ~2 分钟延迟，最近几分钟的数据可能不完整
- ALB 的 p99 延迟需要开启 Extended Statistics，标准 statistics 只有 Average/Sum/Min/Max
- 没有告警配置（ap-northeast-1 当前 0 个告警）不代表环境健康——这就是为什么本 skill 直接查指标
- check-health.sh 使用 macOS 兼容的命令（sed 而非 grep -P）。如果在 Linux 上遇到 sed 行为差异，检查 GNU vs BSD sed
