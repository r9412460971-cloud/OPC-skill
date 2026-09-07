---
name: skill-reviewer-v2
description: >-
  Review Workbuddy skill packages with a staged Platform Mode workflow:
  structure/format and macOS/Windows portability checks, required semantic LLM
  risk review, conditional functional dialogue validation, workflow gating,
  review-only reports, and batch review coordination. Triggers on: review skill,
  check skill, validate skill, skill compliance, quality check, platform review.
version: 2.6.11
---

# Skill Reviewer v2

Use this skill to review Workbuddy skill packages. `scripts/review.py` is the
workflow router; implementation details are split by stage under `scripts/`, and
review standards live in `references/`.

## Modes

**Choose the mode based on intent, not habit.**

- `workflow` (**default — always use for real listings**): produce stage JSON
  files and sync pending-review state from `05-final.json`. Only this mode sets
  `review_gate.can_upload = true` when the final status is `reviewed`, making
  the package eligible for `skill-uploader publish`. **Any listing that will
  proceed to upload/approve must use this mode.** Omit `--mode` entirely to use
  this default.
- `review-only` (**report only — never for real listings**): inspect only.
  Never upload, approve, or sync queue state. `can_upload` is always `false`.
  **Functional validation and deep quality review are still required.**
  Review-only only skips the upload/approval workflow, not the review itself —
  a quality report is incomplete without deep review when body >= 1 KB.
  It skips listing-workflow-only gates: first-listing source metadata, upload
  eligibility, pending sync, and partner-report prompts. **Use only when the
  goal is a quality report with no intention to list** — e.g. "just check
  quality", "generate a test report", "看看这个 skill 质量怎么样". Never use
  `review-only` for a real listing pipeline.

## 自主执行策略

- 默认运行 `scripts/review.py <skill_dir> --stage all --autopilot`。
- 不在每个 stage 后询问下一步；读取 `workflow_next.actions` 并继续执行。
- 后台任务不是完成态：batch/review 命令若被运行环境转为后台任务，必须等待任务完成、读取输出文件与 stage JSON，然后继续生成/提交 verdict、重跑 final gate，直到 `reviewed`、真实 blocker 或明确用户确认点。不得以“Batch review 后台运行中”作为最终回复。
- `needs_ai_review` 不是用户确认点；生成对应 verdict JSON 后执行 submit 命令。
- `ai_actions` 不是用户确认点；基于包体、平台规则和现有脚本处理，处理结果写入 stage/final 记录。
- 只有以下情况停下询问：真实外部配置缺失、安全/合规风险需要接受、无法判断的包体删除/改写、平台状态不确定、用户偏好类选择。
- reviewer 不执行 publish、PATCH、upload-icon、approve。

## Stage Contract

Follow `references/staged-review-flow.md`. Each stage has one goal, one
previous-stage check, one output file, and one final-gate impact:

1. `01-structure.json`: deterministic structure, portability, package,
   install-guidance checks. Environment configuration guidance signals are
   recalled for LLM semantic review in stage 02. Required for every workflow
   review, including new listings and version updates.
2. `02-risk.json`: deterministic script/link risk, high-risk
   capability/obfuscation scan, plus required security-subagent semantic risk
   verdict request/result. Required for every workflow review, including new
   listings and version updates; this covers security, compliance, and
   commercial redirection/lead-generation risk. A generic LLM pass or empty
   findings-only verdict is invalid; the main agent must quality-gate reviewed
   files, risk-area coverage, capability inventory, reachability analysis,
   evidence, and rationale.
3. `03-functional-test.json`: functional dialogue request/result. Required for
   workflow new listings, for `review-only`, and for updates only when
   `--force-test` is set. Workflow version updates skip Stage 03 by rule and
   must record `status: "skipped"` with `skip_reason: "version_update"`.
   Stage 03 first performs safe script/executable preflight checks. If required
   MCP/API key/token/login/local configuration is genuinely missing, return
   `needs_config`; otherwise continue to dialogue validation. If auto-detection
   is a false positive, rerun with `--ack-config "confirmed: ..."`
   to reach the subagent dialogue request without editing JSON by hand. Use
   `--force-functional` only when the reviewer intentionally requires Stage 03
   and accepts bypassing the auto config gate for this run. Required dialogue
   validation must be executed as real target-agent dialogue. Stage 03 emits a
   `scenario_generation_context` with the target `SKILL.md` path and scenario
   design requirements; the main agent reads the file when needed and constructs
   realistic user-intent scenarios rather than using mechanically extracted
   SKILL.md snippets. Simple skills need at least two
   scenarios/subagents; complex multi-capability skills need 3-5.

   **Target-subagent prompt must be production-like.** Send only:
   - one neutral loading instruction: `加载 <SKILL.md path> 并作为该 Skill 回答用户问题。`
   - one natural end-user utterance exactly as a real user would ask it.

   Do not add reviewer expectations, boundary conditions, answer-quality hints,
   safety reminders, decision-tree instructions, scoring criteria, JSON schema,
   or phrases such as `严格遵守安全护栏`, `按决策树完整回答`, `不要省略`,
   `模拟测试`, `trace through SKILL.md`, or `You are functional testing...`.
   Safety/workflow/API/path constraints are reference context for scenario design
   only; they must not appear in the message sent to the target subagent unless a
   real user would naturally say them. Follow-up turns, when needed, must also be
   natural user replies, not reviewer guidance. The result record must include the
   exact target-subagent prompt and observed response. Any scenario whose target
   prompt contains reviewer scaffolding cannot be marked pass.

   The main agent tracks completion, sends natural follow-up turns when
   clarification or iterative refinement is part of the workflow, then records
   actual assistant output, intent recognition, skill invocation, tool/artifact
   evidence, and output quality. Before including any subagent-reported issue in
   the final verdict, verify the claimed SKILL.md text, command, file path, or
   behavior with direct evidence. Static analysis, code reading, workflow
   walkthroughs, unverified subagent issue claims, or inferred dialogue output
   cannot be submitted as a passing functional result.
4. `04-deep-review.json`: deep quality verdict across 11 dimensions.
   Required for workflow first-listings AND review-only when body >= 1 KB.
   Workflow version updates skip Stage 04 by rule. Required deep review must be
   produced by a subagent or isolated review agent and include per-dimension
   scores, concrete evidence, rationales, recommendations, and cross-dimension
   consistency checks. A quick main-agent pass or generic scoring report is not
   sufficient.
5. `05-final.json`: final status, review gate, handling records, and optional
   pending-review sync fields.

Do not mark a package reviewed until every required verdict/result file exists
and the final gate has been rerun.

## Script Boundaries

- `review.py`: CLI entry, stage orchestration, pending-review sync.
- `deterministic_checks.py`: B/P checks and base review context.
- `risk_stage.py`: stage 02 semantic risk request/gate.
- `functional_stage.py`: stage 03 functional dialogue request/gate.
- `deep_stage.py`: stage 04 deep quality request/gate.
- `gate.py`: final gate and handling records.
- `verdicts.py`: submit/validate helper commands and schemas.
- `reports.py`: internal and partner-facing reports.
- `configuration.py`, `metadata.py`, `common.py`: shared helpers.

## Entry Points

- `scripts/review.py <skill_dir> [--mode workflow|review-only] --stage all --autopilot`
  - **For real listings**: omit `--mode` entirely (defaults to `workflow`).
  - **For quality reports only**: add `--mode review-only`; review-only now writes a default Markdown report when no explicit report path is supplied.
  - Add `--pending-file <path>` when reviewing an explicit pending-review file.
  - Optional result inputs: `--semantic-review-file`, `--functional-test-file`,
    `--deep-review-file`, `--report-verification-file`.
  - If configuration detection is a false positive, use `--ack-config "confirmed: no external config needed"`; use `--force-functional` to require Stage 03 and bypass the auto config gate for a confirmed run.
- `scripts/batch.py --names <name1,name2> [--no-parallel]`
- Helper commands:
  - `scripts/review.py submit-risk --review-output-dir <dir> --from-file <verdict.json>`（推荐；避免复杂 CLI 参数解析）
  - `scripts/review.py submit-functional --review-output-dir <dir> --from-file <verdict.json>`（推荐；值里可安全包含分号）
  - `scripts/review.py submit-deep --review-output-dir <dir> --from-file <verdict.json>`（推荐；维度与证据可完整写入 JSON）
  - `scripts/review.py submit-risk --review-output-dir <dir> --status pass|blocked --summary "..."`
  - `scripts/review.py submit-functional --review-output-dir <dir> --status pass|blocked|needs_config --summary "..."`
  - `scripts/review.py submit-deep --review-output-dir <dir> --status pass|blocked --summary "..." --review-method subagent_deep_review --source-file SKILL.md --cross-check "..."`
  - `scripts/review.py submit-exemption --review-output-dir <dir> --check-id B15 --reason "false positive rationale"`
  - `scripts/review.py validate-verdict <file> --kind risk|functional|deep`

## Report Policy

- Generate Markdown reports only when explicitly requested, except `review-only` mode, which always writes a report.
- Workflow first-listing reviews may offer a report; workflow version updates skip report generation by default.
- A final report must be conclusion-oriented and Chinese-first. Do not expose raw stage JSON, handling records, AI action prompts, subagent transcripts, long evidence tables, or internal process notes.
- Before treating report issues as final, run an LLM or human verification pass over every proposed issue. The verification must confirm whether the issue is real, whether the impact is accurate, and whether the priority is appropriate. Pass it with `--report-verification-file` or store `06-report-verification.json` in the review output directory.
- Without report verification, generated Markdown is only a draft and must clearly say it is not a final report.

## AI Action Policy

- Resolve blockers and warnings through AI judgment whenever package evidence is
  sufficient.
- Do not bump package versions in reviewer. Version progression belongs to
  skill-fetcher-v2; B12 only validates or blocks stale versions.
- Escalate only for missing external information, missing required
  configuration, security/compliance acceptance, irreversible package decisions,
  platform-state ambiguity, or user-preference choices.
- When AI judges a deterministic blocker to be a false positive or an accepted
  waiver, record that decision with `submit-exemption` and rerun `--stage final`;
  do not edit the skill package merely to satisfy a mistaken local check.
- Record every pass, warning, blocker, AI verdict, skipped stage, escalation,
  and applied fix in handling records.
- Deep review evidence only needs to be substantive text (>=24 chars); do not fail a verdict solely because evidence lacks a file/line token. Non-standard dimension ids are accepted with warnings, while pass verdicts still require at least 11 dimensions.
- Reviewer never uploads or approves packages.

### Configuration Gate (needs_config)

When Stage 03 is required:

1. If credentials, account login, MCP authorization, API Key, or required local dependency is genuinely unavailable, return `needs_config` with exact setup fields.
2. Do not continue functional dialogue without required external configuration.
3. Do not treat generic words such as token consumption, snapshot, temp file, pattern, format, or command examples as configuration blockers.
4. If a valid `03-functional-dialogue-test-result.json` already exists and validates, keep it.
5. If detection is a false positive, rerun with `--ack-config "confirmed: no external config needed"` and continue to the dialogue request.
6. If Stage 03 returns `requires_ai_review`, launch/collect target-agent dialogue and submit the verdict; do not ask the user for next step.

Workflow version updates without `--force-test` skip Stage 03 before configuration checks.

## Output Layout

- Stage verdict files stay in
  `.workbuddy/skill-marketplace/review-output/<date>/<skill>/`.
- Command result JSON goes under
  `.workbuddy/skill-marketplace/runs/<date>/<skill>/<phase>/`.
- Bare `--output-file` names are routed into the current run directory.
- Absolute output paths and explicit `.workbuddy/...` paths are honored.
- Shared workflow utility directory priority:
  `SKILL_WORKFLOW_COMMON_DIR` → `SKILL_MARKETPLACE_WORKSPACE` →
  local `.workbuddy/skill-marketplace/config.json.workspace_root` →
  `.workbuddy/skill-marketplace/workflow-common` → `CODEX_HOME/skills/_workflow_common`.

## Key References

- `references/staged-review-flow.md`: canonical stage contract and gate rules.
- `references/structure-and-portability-checks.md`: block 1 details.
- `references/security-risk-checks.md`: stage 02 security risk standards.
- `references/commercial-and-legal-risk-checks.md`: commercial/legal risk standards.
- `references/functional-testing-bridge.md`: stage 03 functional validation boundary.
- `references/deep-quality-review.md`: stage 04 quality dimensions.
- `references/subagent-strategy.md`: subagent coordination.
- `references/ai-action-policy.md`: mutation and escalation boundaries.
