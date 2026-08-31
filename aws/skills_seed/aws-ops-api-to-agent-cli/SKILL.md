---
name: api-to-agent-cli
description: "Use when the user has a set of internal APIs / REST endpoints / SDK and wants to expose them as an agent-friendly CLI. Also use when retrofitting an existing CLI for AI agent use, or when auditing how agent-ready an existing CLI is. Prevents the common 1:1 wrapping trap by forcing a workflow-merge step before code generation. Synthesizes Anthropic's 'Writing effective tools for"
---

# API → Agent-Friendly CLI

把内部 API 重构为 agent 真正能高效调用的 CLI。**核心约束**：不允许 1:1 包装，必须先按业务 workflow 合并；必须 ship 配套 SKILL.md；必须通过 11
<!-- MAA skill seed | source: aws-ops | origin: sample-aws-ops-skills-for-agents/api-to-agent-cli/SKILL.md -->
 维 audit。

## 何时使用

- 用户说"把这堆内部 API 做成 agent 能用的 CLI"
- 用户已有 CLI，想做 agent-readiness retrofit
- 用户想给现有 CLI 打分（直接跳到 Phase 5）
- 用户在设计新工具，想从一开始就 agent-native

## 何时不用

- 用户要的是给人类用的 CLI（这个 Skill 的所有取舍都偏向 agent）
- 用户要建 MCP server（参考 Anthropic MCP 文档，不是这个 Skill）
- 用户要做 LLM eval pipeline（这是 Phase 5 之后的事）

---

## 工作流（5 phase）

**先读 [references/principles-checklist.md](references/principles-checklist.md) 让 10 条原则烙进脑子，再开始。**

### Phase 1 · Inventory

**目标**：把"有什么 API"和"agent 要做什么任务"两份清单都列出来。

**步骤**：
1. 读用户的 API 资料：OpenAPI spec、Swagger、Postman collection、SDK 文档、源码、或纯口头描述都行
2. **关键步骤**：让用户列出 **agent 要解决的 Top 20 高频任务**。这一步用户会偷懒，你必须坚持要完整清单——没这份清单 Phase 2 就是瞎合并
3. 用 [`assets/inventory.template.md`](assets/inventory.template.md) 写出 `inventory.md`，含：
   - endpoints 列表（按 resource 分组）
   - agent task 列表（每个任务一行：触发场景 / 期望输入 / 期望输出 / 当前需要几个 endpoint）

**强制约束**：
- agent task 数量必须 ≥ 10，少于这个数说明用户没认真想，逼他/她补
- 每个 task 必须能描述出"agent 在什么对话/场景下会发起这个调用"，否则不是真任务

**Gate**：inventory.md 写完用户 review 确认才能进 Phase 2。

---

### Phase 2 · Workflow Merge ⭐ 核心阶段

**目标**：把 N 个 endpoint 合并成 30–50 个 agent-facing command，每个 command 对应一个 agent task。

**这是这个 Skill 存在的核心价值。** 跳过这一步就是 1:1 包装陷阱，agent 性能会撞穿楼板。

**步骤**：
1. 读 [references/workflow-merge-examples.md](references/workflow-merge-examples.md) 看 5 个真实合并案例
2. 对每个 agent task，回答：
   - 完成这个任务，agent **现在**要调几个 endpoint？
   - 能不能合并成 1 个 command，内部串联完成？
   - 合并后 command 的输入是不是用了 **语义化标识**（name/email/slug），不是 UUID？
3. 用 [`assets/commands.spec.template.md`](assets/commands.spec.template.md) 写出 `commands.spec.md`，每个 command 包含：
   - command 名（动词-名词，如 `schedule-meeting`，不是 `events-create`）
   - 描述（agent 一句话能看懂"这个命令解决什么任务"）
   - 输入参数（语义化标识优先）
   - 内部 fan-out（这个命令背后会调哪些 endpoint）
   - 是否 mutation（是 → Phase 3 必须加 `--dry-run`）

**强制约束 — Merge Ratio**：
- 计算 `merge_ratio = endpoint_count / command_count`
- **如果 merge_ratio < 3**：报警，告诉用户"这看起来仍像 1:1 包装，请重新思考是否每个 command 都对应真实 agent 任务"
- 目标 ratio 是 3-10。几百 API → 30-50 command 是正常区间

**Gate**：commands.spec.md 写完，merge_ratio 达标，用户 review 确认才能进 Phase 3。

---

### Phase 3 · Command Stub

**目标**：为每个 command 按模板生成 Python (Typer) 代码 stub，10 条原则在模板里全部体现。

**步骤**：
1. 读 [references/cli-template-python.md](references/cli-template-python.md) 学 Typer 写法（type hints 自动出 schema、`--help`、validation）
2. 读 [`assets/example-hello-cli/`](assets/example-hello-cli/) 看完整示例（一个 mini CLI 演示所有 10 条原则）
3. 读 [references/error-schema.md](references/error-schema.md) 拿结构化 error 的 JSON schema
4. 为每个 command 写 stub，**必须**包含：
   - `--output` flag（默认 table，可选 json，stdout 非 TTY 自动切 json）
   - `--fields` flag（field mask）
   - `--limit` 和 `--page-token`（list 类命令）
   - `--dry-run` flag（mutation 类命令）
   - input validation（control chars / path traversal / `?` `#` `%` reject）
   - structured error JSON output（含 `suggestion` 字段）
   - semantic exit codes（0/1/2/3/4/124）
   - `schema` 子命令（runtime 自省）
5. 业务逻辑（实际调 endpoint 的部分）用注释占位，让用户/后续 agent 填

**强制约束**：
- 每个 command 必须有 `--output json` flag
- mutation 类 command 必须有 `--dry-run` flag
- 不能有任何 `input("Are you sure? (y/n)")` 交互式 prompt
- 错误必须返回 [error-schema.md](references/error-schema.md) 定义的 JSON 结构

---

### Phase 4 · SKILL.md（配套 agent guide）

**目标**：写一份配套 SKILL.md，agent 拿到这个 CLI 时一并加载。

`--help` 告诉 agent 参数格式，**SKILL.md 告诉 agent 不变量和 workflow**——这是 progressive disclosure 的载体。

**步骤**：
1. 读 [`assets/SKILL.template.md`](assets/SKILL.template.md) 拿模板
2. 必须包含的 section：
   - **Invariants**（每次操作前必须满足的不变量，如 "ALWAYS use `--output json`"）
   - **Common Workflows**（3-5 个典型 agent 任务的完整执行序列）
   - **Authentication**（怎么拿 token、放哪里）
   - **Rate Limits & Pagination**（agent 该怎么处理）
   - **Examples**（每个高频 command 的真实使用例子）
3. 把 SKILL.md 放到 CLI 仓库根，agent 加载这个工具时一并 load

**强制约束**：
- SKILL.md 必须 ship；没 SKILL.md 不算完成
- "Common Workflows" section 必须 ≥ 3 个完整案例
- 不要写空话（如"Make sure to handle errors gracefully"——告诉 agent **怎么** handle）

---

### Phase 5 · Self-Audit（11 维 rubric）

**目标**：用 [references/audit-rubric.md](references/audit-rubric.md) 给生成的 CLI 打分。

**步骤**：
1. 读 [audit-rubric.md](references/audit-rubric.md) 拿 11 维评分卡
2. 用 [`assets/audit-report.template.md`](assets/audit-report.template.md) 输出评分报告
3. 每一维给 0/1/2 分（0=没做、1=部分做、2=完整做），总分 22
4. 列出未通过项的具体 gap 和修复建议

**强制约束**：
- **总分 < 18（≈ 9 项满分等价）不算通过**，必须回到对应 phase 修复
- 反模式 hits（见 [antipatterns-quickref.md](references/antipatterns-quickref.md)）每命中 1 条扣 2 分

---

## 独立调用模式

audit-rubric 可以**独立**于 5-phase 流程使用：

> 用户："帮我看看现有的 `internal-cli` agent-readiness 怎么样"

直接跳到 Phase 5：读 [audit-rubric.md](references/audit-rubric.md)，跑评分，输出 [`audit-report.template.md`](assets/audit-report.template.md) 格式的报告。不需要走 Phase 1-4。

---

## References 索引

| 文件 | 用在哪 phase | 是什么 |
|------|------------|--------|
| [principles-checklist.md](references/principles-checklist.md) | 全程 | 10 条原则 quick check |
| [workflow-merge-examples.md](references/workflow-merge-examples.md) | Phase 2 ⭐ | 5 个真实合并案例 |
| [antipatterns-quickref.md](references/antipatterns-quickref.md) | Phase 2-3 | 7 个反模式 + 解法 |
| [cli-template-python.md](references/cli-template-python.md) | Phase 3 | Typer 写法指南 |
| [error-schema.md](references/error-schema.md) | Phase 3 | 结构化 error JSON schema |
| [audit-rubric.md](references/audit-rubric.md) | Phase 5（可独立调用） | 11 维 agent-readiness 评分卡 |

## Assets 索引

| 文件 | 何时产出 | 是什么 |
|------|---------|--------|
| [inventory.template.md](assets/inventory.template.md) | Phase 1 | endpoints + agent tasks 清单模板 |
| [commands.spec.template.md](assets/commands.spec.template.md) | Phase 2 | 合并后的 command 设计模板 |
| [SKILL.template.md](assets/SKILL.template.md) | Phase 4 | 配套 SKILL.md 模板 |
| [audit-report.template.md](assets/audit-report.template.md) | Phase 5 | 11 维评分报告模板 |
| [example-hello-cli/](assets/example-hello-cli/) | Phase 3 参考 | 完整可运行示例（演示所有 10 原则） |

---

## Gotchas

- **Phase 2 是这个 Skill 的核心 — 不要妥协**。用户想跳过、想"先生成 stub 再合并"，必须拒绝。1:1 包装陷阱的本质就是用户想偷懒，而 OpenAPI spec 的存在让"先生成"看起来很合理
- **Merge ratio 检查不是装饰**。低于 3:1 就是问题，必须真的拒绝继续，不要"warn 一下就放行"
- **不要追求"自动一键转换"**。Justin Poehnelt 在 Google 也是手工设计每个 command。OpenAPI 千变万化（auth、嵌套 ref、polymorphic schema），自动转换器永远不够好。这个 Skill 的价值就是 prescriptive workflow，不是 codegen
- **type hints 是 Typer 的灵魂**。在 Phase 3，所有参数必须有完整 type hint（含 Optional、Literal、Annotated），Typer 会自动转成 schema、help、validation——10 条原则有 5 条它自动给你
- **Phase 4 SKILL.md 的"Common Workflows"section 是产出价值密度最高的部分**。Will Steuk (CWC #14) 的 62%→92% 提升核心来源就是把 system prompt 里的业务流程迁移到 SKILL.md 做 progressive disclosure
- **Phase 5 audit 不是给"看起来不错"的项目放行的**。总分 < 18 必须回去修，不是发个 warning。这一关如果松了，整个 Skill 失去意义

---

## 来源

- Anthropic, [Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents) (2025-09-11)
- Anthropic, [Building agents with the Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk) (2025-09-29)
- Justin Poehnelt (Google), [You Need to Rewrite Your CLI for AI Agents](https://justin.poehnelt.com/posts/rewrite-your-cli-for-ai-agents/) (2026-03)
- AXI: [Agent eXperience Interface benchmarks](https://github.com/kunchenguid/axi) (2026-03, 425 runs / 17 tasks / Sonnet 4.6)
- Code with Claude 2026 Session #14 (Will Steuk, Anthropic): [Tool, Skill, or Subagent?](https://www.youtube.com/watch?v=mWvtOHlZM-I)
