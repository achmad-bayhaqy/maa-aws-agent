---
name: env-discovery
description: "Use when investigating what AWS services are running, checking fleet health by service tag, responding to 'what's in my account' questions, onboarding to a new AWS account, or preparing an environment overview. Uses tag-based Fleet Intelligence: discovers tag taxonomy, aggregates resource counts by service tag, and checks alarm status — does NOT enumerate individual resources."
---

# Environm
<!-- MAA skill seed | source: aws-ops | origin: sample-aws-ops-skills-for-agents/env-discovery/SKILL.md -->
ent Discovery — Fleet Intelligence

通过 tag 导航发现环境结构，不枚举单个资源。

## 工作流程

### 1. 确认扫描目标
- 确认 account ID（默认 `<account-id>`，从 environment.md 读取）
- 确认 region 范围（默认扫描 environment.md 中列出的所有 region）

### 2. 执行扫描
- 运行 `scripts/discover-account.sh <account-id> <region>`
- 脚本三阶段独立执行：tag 发现 → 资源聚合 → 告警状态
- 输出 JSON 到 stdout，同时更新 environments/ 下的 account.yaml 和 account.md

### 3. 终端摘要输出
- 解析脚本输出的 JSON，渲染终端摘要
- 包含：各服务资源数量、当前告警、异常标记
- **报告中每条结论必须能追溯到本次扫描的 JSON 数据**，禁止从 account.yaml 旧注释、历史报告、或记忆中搬运未验证信息

### 3.1 与上次扫描对比（可选）
- 读 account.yaml 获取上次 service_catalog，与本次 JSON 做 diff
- 对比范围仅限于**本脚本覆盖的三个 phase**（tag / 资源聚合 / 告警）
- account.yaml 中的注释、log_sources 等**不在脚本扫描范围内**的信息，不得作为对比结论引用——如需报告这些信息，必须单独查询验证
- 发现变化时标注「新增 / 消失 / 数量变化」，附具体数据

### 4. 两种查询模式

#### 模式 1：全局概览（"环境怎么样"）
1. 读 environments/<account>/account.yaml 获取 service catalog
2. 查 CloudWatch Alarms in ALARM state → 按 alarm_prefix 归类到服务
3. 输出：各服务健康摘要 + 异常告警

#### 模式 2：定向下钻（"交易引擎的 DB 怎么样"）
1. 从 service catalog 找到 tag 和 resource_types
2. 用 tag 过滤查询目标资源的 CloudWatch 指标
   - RDS: CPUUtilization, FreeableMemory, ReplicaLag
   - EC2: CPUUtilization, StatusCheckFailed
   - EKS: pod restart count, node status
3. 只返回指标异常或用户关心的资源详情

## 查询参考
各服务具体的 AWS CLI 命令和解读要点见 `references/service-checklist.md`。
不要自行编写查询命令——用 checklist 中验证过的命令。

## Automation Boundary

### auto-safe
- 所有 describe / list / get 查询
- resourcegroupstaggingapi 调用
- cloudwatch describe-alarms
- 生成报告文件

### human-required
- 无（本 skill 纯只读）

## Gotchas
- `resourcegroupstaggingapi` 返回的 ARN 中 `ec2` 涵盖 instance/vpc/subnet/sg/nat/igw 等所有资源。必须从 ARN 第 6 段提取细分类型（如 `ec2:instance`），否则会误报"19 台 EC2"实际是网络资源
- Tag 推断 primary_key 时需排除 k8s 系统 tag（key 含 `.` 或 `/` 的，如 `alpha.eksctl.io/xxx`）
- 个人/实验账号可能没有业务级 tag（如 `service`），`Project` 或 `Name` 可能是最接近的替代
- **account.yaml 中的历史注释不是实时数据**。脚本只产出 tag/资源聚合/告警三类数据，account.yaml 中的 `log_sources`、手写注释等是其他流程或人工维护的。巡检报告不得把这些当作本次扫描结论。引用前必须用 CLI 验证当前状态
- **扫描后清理 account.yaml 中的过期注释**。已解决的问题标注解决时间，未验证的问题不要留着——下次扫描会误导
