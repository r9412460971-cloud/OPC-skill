# Staged Review Flow

`skill-reviewer-v2` is a staged workflow. Each stage has one goal, one
previous-stage check, one output file, and one final-gate impact. Scripts collect
evidence and enforce deterministic checks; required AI/subagent verdicts must be
submitted as explicit result files.

## Modes

**Choose the mode based on intent, not habit.**

- `workflow` (**default — always use for real listings**): create stage JSON
  files and allow pending-review state updates from `05-final.json`. Only this
  mode sets `review_gate.can_upload = true` when the final status is
  `reviewed`, making the package eligible for `skill-uploader publish`. **Any
  listing that will proceed to upload/approve must use this mode.** Omit
  `--mode` entirely to use this default.
- `review-only` (**report only — never for real listings**): run the review
  without upload workflow side effects. Return the review result directly. Save
  a report only when explicitly requested. `can_upload` is always `false` in
  this mode. Skip listing-workflow-only gates: first-listing source metadata,
  pending-review sync, upload approval, and partner-report follow-up prompts.
  **Functional validation and deep quality review are still required.**
  Review-only only skips the upload/approval workflow, not the review itself —
  a quality report is incomplete without deep review when body ≥ 1 KB.
  **Use only when the goal is a quality report with no intention to list** —
  e.g. "just check quality", "generate a test report", "看看这个 skill 质量
  怎么样". Never use `review-only` for a real listing pipeline.

## Stage Checkpoints

| Stage | Goal | Previous-step check | Output | Gate impact |
| --- | --- | --- | --- | --- |
| 01 Structure | Verify package shape, frontmatter, links, size, install guidance, and portability precheck. Environment configuration guidance signals are recalled for LLM review in stage 02. | `SKILL.md` exists and parses. | `01-structure.json` | Any failed deterministic blocker contributes to `blocked`. |
| 02 Risk | Combine deterministic script/link validation, high-risk capability/obfuscation scanning, and semantic risk verdict. LLM also reviews B20 environment configuration guidance sufficiency based on recalled signals. | Stage 01 output exists; risk checks are split from deterministic results. | `02-risk.json` plus `02-risk-semantic-review.json` | Missing semantic verdict => `needs_ai_review`; script/link, high-risk capability, obfuscation, or semantic blocker => `blocked`. |
| 03 Functional | Verify advertised behavior through real dialogue scenarios. | Stage 02 has preserved any setup guidance needed for complete testing. | `03-functional-test.json` plus `03-functional-dialogue-test-result.json` | Missing result => `needs_ai_review`; missing config => `needs_config`; failed scenario => `blocked`. |
| 04 Deep | Deep quality review across 11 dimensions. Required for workflow first-listings and for `review-only` when body ≥ 1 KB. | Functional stage is passed, skipped by rule, or waiting on config/AI result. | `04-deep-review.json` plus `04-deep-quality-review-result.json` | Missing required verdict => `needs_ai_review`; blocking quality issue => `blocked`. |
| 05 Final | Assemble final status, review gate, handling records, and optional pending sync fields. | Required stage results have been consumed by rerunning `--stage final` or `--stage all`. | `05-final.json` | `review_gate.can_upload` is true only for workflow `reviewed`. |

Stage 01 and Stage 02 are mandatory for every real listing workflow, including
new listings and version updates. Stage 01 covers structure, packaging,
portability, and install guidance. Stage 02 covers script/link risk, security,
compliance, high-risk capability/obfuscation, and commercial
redirection/lead-generation risk.

Stage 03 is required for workflow new listings, for `review-only`, and for
updates when `--force-test` is set. Workflow updates skip it by default; the
stage output must make the skip explicit with `status: "skipped"`,
`skipped: true`, and `skip_reason: "version_update"`. If config detection is a
false positive, `--ack-config "confirmed: ..."` records the acknowledgement and
lets the stage produce the subagent dialogue request instead of stopping at
`needs_config`. `--force-functional` both requires Stage 03 and bypasses the auto
config gate for a confirmed run.
Stage 04 is required for workflow first-listing reviews and for `review-only`
when body ≥ 1 KB (body < 1 KB is too small for meaningful deep review).
Workflow version updates skip Stage 04 by rule and must likewise record
`status: "skipped"` with `skip_reason: "version_update"`.

## Final Gate

The final status must be:

- `reviewed`: all deterministic blockers cleared, required semantic review
  passed, required script/link risk validation passed, required functional
  validation passed or skipped by rule, required deep quality review passed.
- `needs_ai_review`: semantic risk verdict or required deep quality verdict is
  missing, or required functional dialogue testing has not been executed by a
  subagent. Autopilot must generate/collect the required verdict and submit it;
  this is not a user confirmation point.
- `needs_config`: required functional validation cannot run without user-provided
  token/API key/MCP/account/dependency configuration. Stop only for the missing
  external configuration. When detection is not applicable, rerun with
  `--ack-config` so the functional dialogue request is generated and the
  subagent test can proceed.
- `blocked`: any deterministic blocker, script/link blocker, semantic blocker,
  functional blocker, or deep review blocker remains.

Stage 02 deterministic security blockers cannot be neutralized by a generic
semantic pass. If B19/B23 reports high-strength obfuscation, LLM traffic
interception, conversation capture, self-modification, autonomous purchase, or
external reporting combinations, final status remains `blocked` until the risky
behavior is removed or unobfuscated source plus line-specific rationale proves a
false positive.

`review_gate.can_upload` is true only for `workflow` results whose final status
is `reviewed`. It is always false in `review-only`.

## Handling Records

`05-final.json` must include handling records for deterministic checks, script/link validation, semantic risk verdicts, functional/deep stages, AI actions, escalations, skipped stages, and any applied fix. User escalation is allowed only for missing external information, missing required configuration, security/compliance acceptance, irreversible package decisions, platform-state ambiguity, or user-preference choices.

## Partner Report Prompt

For first-time listings in `workflow`, after `05-final.json` is produced, offer a partner-facing Skill test report only as an optional follow-up. The report must follow
`references/partner-test-report-rules.md` and avoid internal review terminology.

## Verdict Helpers

Prefer the helper commands below instead of hand-writing result JSON. After any
helper writes a file, the helper refreshes the sibling stage and `05-final.json`.
Continue by reading `workflow_next.actions` instead of asking for the next step.

### Semantic Risk

Prefer creating `02-risk-semantic-review.json` with the helper command below
instead of hand-writing JSON:

```bash
python <skill_base_dir>/scripts/review.py submit-risk \
  --review-output-dir <review_output_dir> \
  --status pass \
  --summary "Security subagent reviewed the package, covered required risk areas, and found no reachable semantic safety blocker." \
  --reviewed-by security_subagent \
  --review-method subagent_semantic_security_review \
  --source-file SKILL.md \
  --source-file scripts/example.py \
  --risk-area credential \
  --risk-area privacy \
  --risk-area network \
  --risk-area unsafe_execution \
  --risk-area prompt_injection \
  --risk-area commercial_diversion \
  --risk-area legal \
  --risk-area configuration \
  --capability "SKILL.md and executable files were reviewed for credential handling, network calls, and unsafe execution." \
  --reachability "Risky-looking examples were classified as documentation or confirmed not reachable from production instructions."
```

For findings, repeat `--finding "category=security;severity=low;decision=warning;file=SKILL.md;line=12;text=...;rationale=..."`.
The helper validates and writes the verdict file. A pre-existing verdict can
still be passed with `--semantic-review-file` for a single target.

Schema:

```json
{
  "status": "pass",
  "reviewed_by": "security_subagent",
  "review_method": "subagent_semantic_security_review",
  "source_files_reviewed": ["SKILL.md", "scripts/example.py"],
  "risk_categories_checked": [
    "credential",
    "privacy",
    "network",
    "unsafe_execution",
    "prompt_injection",
    "commercial_diversion",
    "legal",
    "configuration"
  ],
  "capability_inventory": [
    "Concrete actual capability found or explicitly ruled out with evidence."
  ],
  "reachability_analysis": [
    "Production/install/runtime behavior was distinguished from documentation, examples, and tests."
  ],
  "findings": [
    {
      "category": "security",
      "severity": "low",
      "decision": "warning",
      "reachability": "documentation_example",
      "evidence": [{"file": "SKILL.md", "line": "optional", "text": "short excerpt"}],
      "rationale": "semantic judgment"
    }
  ],
  "summary": "short conclusion"
}
```

Use `"status": "blocked"` or any finding with `"decision": "blocker"` to block.

### Functional Dialogue

Required functional validation must be executed as real target-agent dialogue,
not inferred from static reading alone. Stage 03 emits `scenario_generation_context`
with the target `SKILL.md` path and scenario design contract; the main agent uses
already-read context or reads the file when needed, generates realistic end-user
scenarios with LLM judgement, then launches one isolated target subagent
per generated scenario. The target-subagent prompt must be production-like: one
neutral instruction `加载 <SKILL.md path> 并作为该 Skill 回答用户问题。` plus the raw
natural user utterance as `用户: <user_request>`. Prefer creating
`03-functional-dialogue-test-result.json` with the helper command below only
after all planned target subagents have completed or a blocking failure is
observed:

Stage 03 performs safe script/executable preflight before dialogue validation.
Python helpers are compile-checked, JavaScript helpers use `node --check` when
available, shell helpers use syntax checks when available, and unsupported
batch-style helpers are recorded as warnings for the dialogue/runtime test to
cover. A preflight blocker prevents functional validation from passing.

The target skill must receive only the neutral load instruction and natural
end-user request. Safety rules, path rules, API configuration, command examples,
and implementation notes are reference context only; do not mechanically copy
them into `user_request`. The reviewer may use `03-functional-test.json` and the
schema below to plan and record the test, but must not paste reviewer
instructions, JSON schema, scoring criteria, expected behavior, boundary
conditions, safety reminders, `按决策树完整回答`, `按 SKILL.md 的安全规则回答`, or
"simulate a test" wording into the target-skill conversation. Simple skills use
at least 2 target subagents/scenarios; complex multi-capability skills use 3-5.
Before carrying a target subagent's reported issue into the final verdict, verify
the claimed SKILL.md text, command, path, or behavior with direct evidence.

```bash
python <skill_base_dir>/scripts/review.py submit-functional \
  --review-output-dir <review_output_dir> \
  --status pass \
  --summary "Functional dialogue validation passed." \
  --execution-method subagent_dialogue \
  --static-analysis-only false \
  --scenario "id=T1;agent_task_id=T1;title=...;request=...;turns=user: ...|assistant: ...;intent_recognized=yes;skill_invoked=yes;artifacts=...;output_quality=pass;result=pass;evidence=..." \
  --scenario "id=T2;agent_task_id=T2;title=...;request=...;turns=user: ...|assistant: ...|user: follow-up|assistant: ...;intent_recognized=yes;skill_invoked=yes;artifacts=...;output_quality=pass;result=pass;evidence=..."
```

Schema:

```json
{
  "status": "pass",
  "reviewed_by": "subagent",
  "execution_method": "subagent_dialogue",
  "static_analysis_only": false,
  "scenarios": [
    {
      "id": "T1",
      "agent_task_id": "T1",
      "title": "short title",
      "user_request": "natural end-user request sent to the target skill",
      "target_agent_prompt": "加载 <SKILL.md path> 并作为该 Skill 回答用户问题。\n\n用户: <user_request>",
      "dialogue_turns": ["user: ...", "assistant: ...", "user: optional follow-up", "assistant: ..."],
      "intent_recognized": "yes",
      "skill_invoked": "yes",
      "artifacts_observed": ["file/url/widget/tool output observed, or empty list"],
      "output_quality": "pass",
      "result": "pass",
      "evidence": "specific observed behavior"
    }
  ],
  "summary": "short conclusion"
}
```

At least two scenarios are required. The scenario count equals the main-agent
generated scenario count: 2 for simple skills and up to 5 for complex
multi-capability skills. Each scenario must contain real user/assistant or
user/subagent dialogue turns plus observed evidence for intent recognition, skill
invocation, artifacts/tool outputs when applicable, and output quality. Static
analysis, code reading, instruction tracing, SKILL.md workflow walkthroughs,
unverified issue claims, or self-reported "not actually executed" results are
invalid and must not be submitted as `pass`. Use
`"status": "blocked"` when a core advertised workflow fails. Use
`"status": "needs_config"` when credentials, login, MCP, account access, local
tools, or OS/runtime setup are required before the dialogue scenarios can be
completed.

### Deep Quality

Prefer creating `04-deep-quality-review-result.json` for new listings with the
helper command below instead of hand-writing JSON. Submit this only after a
subagent or isolated review agent has performed the deep review:

Shortened command shape:

```bash
python <skill_base_dir>/scripts/review.py submit-deep \
  --review-output-dir <review_output_dir> \
  --status pass \
  --summary "Deep quality review passed." \
  --review-method subagent_deep_review \
  --source-file SKILL.md \
  --source-file references/example.md \
  --cross-check "context_efficiency evidence was compared against executability and maintainability." \
  --cross-check "portability evidence was compared against scripts and setup guidance." \
  --dimension "id=executability;rating=good;score=7;evidence=SKILL.md workflow section names the required command and output files.|scripts/run.py was checked for the referenced command path.;rationale=The workflow is executable but has setup assumptions.;recommendation=Clarify setup prerequisites." \
  --dimension "id=context_efficiency;rating=needs_work;score=6;evidence=SKILL.md description is 520 characters with repeated keyword phrases.|The first body section repeats the same capability list without adding execution steps.;rationale=The text spends more context on keywords than operational guidance.;recommendation=Condense repeated keywords and add concrete usage boundaries."
```

For a `pass` verdict, include all 11 required quality dimensions:
`executability`, `context_efficiency`, `fault_tolerance`, `user_experience`,
`audience_fit`, `portability`, `domain_accuracy`, `completeness_boundary`,
`consistency`, `maintainability`, and `evolvability`. Each dimension must include
`rating`, `score`, at least two concrete evidence items, `rationale`, and a
recommendation. The helper validates and writes the verdict file.

Schema:

```json
{
  "status": "pass",
  "reviewed_by": "subagent",
  "review_method": "subagent_deep_review",
  "source_files_reviewed": ["SKILL.md", "references/example.md"],
  "cross_dimension_checks": [
    "context_efficiency evidence was compared against executability and maintainability.",
    "portability evidence was compared against scripts and setup guidance."
  ],
  "dimensions": [
    {
      "id": "executability",
      "rating": "good",
      "score": 7,
      "evidence": ["specific observation with file/section/metric reference"],
      "rationale": "why the score follows from the evidence",
      "recommendation": "specific improvement, if any"
    }
  ],
  "summary": "short conclusion"
}
```

Use `"status": "blocked"` when a quality issue would make the skill misleading,
unusable, unsafe, or materially below marketplace expectations.
