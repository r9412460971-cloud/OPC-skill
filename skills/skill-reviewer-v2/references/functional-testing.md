# 功能验证标准

## 概述

功能验证由 Stage 03 负责。`review.py` 先生成 `03-functional-test.json`
阶段信封，里面包含目标 `SKILL.md` 路径、description、配置需求、脚本预检
结果和场景生成上下文。主 agent 必须基于这些信息构造真实用户 prompt，实际观察
目标 skill 的输出，然后再提交结构化结果。

## 触发条件

| 场景 | 处理 |
|------|------|
| workflow 首次上架 | 必须执行功能验证 |
| workflow 版本更新 | 默认跳过，`--force-test` 时执行 |
| review-only | 必须执行功能验证 |

## 前置门禁

1. 脚本/可执行文件预检：对 `scripts/` 和根目录可执行 helper 做安全的解析或
   编译检查，不执行包体业务逻辑。Python 使用编译检查，JavaScript 使用
   `node --check`，shell/PowerShell 使用语法解析；无法安全检查的文件记录为
   warning 并要求后续 runtime 场景覆盖。
2. 配置门禁：如果 API Key、Token、MCP、登录账号、本地依赖或配置文件真实缺失，
   Stage 03 返回 `needs_config`；其它 `requires_ai_review` 状态继续生成场景并提交 verdict。

## 对话验证流程

1. Stage 03 输出 `scenario_generation_context`，包含目标 `SKILL.md` 路径、计划场景数、场景类型要求和参考约束候选，不内联完整正文。
2. 主 agent 先使用已读上下文；若上下文不足，再按路径阅读 `SKILL.md`，基于用户可见能力构造真实用户意图场景，不从 description/body 机械抽取文本片段。
3. 安全规范、路径定位、API 配置、命令示例和实现说明只能作为 `reference_context` 或 `validation_focus`，不能直接作为 `user_request`。
4. 主 agent 为每个生成场景创建目标 subagent prompt，格式只能是“<自然用户请求>\n\n请使用这个 Skill 完成上述请求：\"<SKILL.md path>\"”。`SKILL.md` 路径只能以这条中性 Skill 使用指引出现。
5. 主 agent 按生成场景启动目标 subagent：一个场景一个隔离 subagent。
6. 简单 skill 至少 2 个场景/目标 subagent；复杂多功能 skill 根据功能复杂度提升到 3-5 个。
7. 主 agent 跟踪每个目标 subagent 的真实响应、工具调用和产物。
8. 主 agent 记录意图是否识别、skill 行为是否被调用、是否有工具/产物证据、输出质量是否可接受。
9. 当流程天然需要澄清、补充参数或二次优化时，主 agent 继续发送自然追问回合。
10. 主 agent 对 subagent 报告的每条问题做源码或安全实测验证，未验证的说法只能写入 notes，不能作为 finding。
11. reviewer 根据观察结果提交 `03-functional-dialogue-test-result.json`。

目标 skill 只能收到自然用户请求和中性的 `SKILL.md` 使用指引。不要把 reviewer 指令、JSON schema、评分标准、
“You are functional testing the skill at SKILL.md path: ...”、“trace through SKILL.md”、“模拟测试场景”或“按 JSON 输出测试结果”等内容发送给目标 skill。

## 结果要求

结构化结果是 reviewer 观察后的记录，不是目标 skill 的输出要求。结果必须包含：

- `execution_method`: `subagent_dialogue` 或 `isolated_test_agent`
- `static_analysis_only`: `false`
- 至少两个场景
- 每个场景对应的 `agent_task_id`
- 每个场景的自然 `user_request`
- 实际 user/assistant 或 user/subagent 对话片段
- `intent_recognized`: `yes`、`partial` 或 `no`
- `skill_invoked`: `yes`、`partial`、`no` 或 `not_observable`
- `artifacts_observed`: 实际观察到的文件、链接、组件、工具输出等
- `output_quality`: `pass`、`warn` 或 `blocked`
- 具体 observed evidence
- `status`: `pass`、`blocked` 或 `needs_config`

静态代码分析、指令阅读、SKILL.md 流程走查、未完成命令输出、未验证的 subagent 问题归因、或承认没有实际调用目标 skill 的结果，
都不能作为 `pass`。

## 阻断规则

当核心广告能力无法被执行、脚本预检存在 blocker、目标 skill 输出伪造成功、跳过
必要工具调用、或对话结果与说明明显矛盾时，功能验证必须返回 `blocked`。
