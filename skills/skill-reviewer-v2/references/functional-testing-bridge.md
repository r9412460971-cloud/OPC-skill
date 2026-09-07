# Functional Testing Bridge

This is review block 3.

## Rule

- In `workflow`, new listings require functional validation.
- Version updates skip functional validation by default.
- `--force-test` requires functional validation even for updates.
- In `review-only`, functional validation is required by default.

When a workflow version update skips this stage, `03-functional-test.json` must
still be written as an explicit skip record with `required: false`,
`test_executed: false`, `status: "skipped"`, `skipped: true`, and
`skip_reason: "version_update"`.

Functional validation is not a script-only smoke test. It must verify that the
skill can perform representative user workflows that match its description.
Static instruction tracing alone cannot pass this stage.

Before dialogue validation, Stage 03 also performs a safe script/executable
preflight for package code under `scripts/` and root-level executable helpers.
This preflight checks parse/compile readiness only; it must not execute package
business logic. A parse/compile blocker prevents functional validation from
passing because the advertised workflow cannot be trusted to run.

## Bridge

`skill-reviewer-v2` owns the functional validation protocol. `review.py` writes
`03-functional-test.json` as the stage envelope. The envelope gives the reviewer
the target `SKILL.md` path, package path, description, configuration status, and
script preflight result. The reviewer or isolated test agent then opens the
target skill and observes real target-skill responses before writing
`03-functional-dialogue-test-result.json`. External `skill-tester-v2` may be
present as an optional compatibility source, but it is not required and cannot
replace observed target-skill dialogue output.

## Scenario Execution

Required functional validation must:

- use `scenario_generation_context` as the scenario-design contract; it contains
  the target `SKILL.md` path, planned scenario count, required scenario types,
  and reference-only constraints, but does not inline the full SKILL.md body;
- generate realistic end-user scenarios with main-agent LLM judgement before
  launching target subagents; do not mechanically turn frontmatter.description,
  policy rules, path rules, API configuration, command examples, or implementation
  notes into `user_request`;
- use safety/workflow constraints as reference context only, converting them into
  natural edge-case user requests when validation requires it;
- launch one isolated target subagent per generated scenario; simple skills use
  at least two scenarios, while complex multi-capability skills use 3-5;
- send only a production-like prompt to the target subagent:
  `加载 <SKILL.md path> 并作为该 Skill 回答用户问题。` followed by the generated
  natural user request. Do not include anything else;
- never paste reviewer instructions, scoring criteria, JSON schema, expected
  behavior, boundary conditions, quality hints, safety reminders, decision-tree
  instructions, `按 SKILL.md 的安全规则回答`, `按决策树完整回答`, `不要省略`,
  "You are functional testing the skill at SKILL.md path: ...", "trace through
  SKILL.md", or "simulate test scenario" wording into the target-skill
  conversation;
- reject a functional pass if the target-subagent prompt contains reviewer
  scaffolding that would help the Skill answer better than a real user prompt;
- record the exact target-subagent prompt, actual user/subagent dialogue turns,
  and observed response, including a natural follow-up turn when clarification or
  iterative refinement is part of the workflow;
- record whether the intent was recognized, whether skill behavior/tooling was
  invoked, what artifacts or tool outputs were observed, and whether output
  quality is acceptable;
- verify every subagent-reported issue against SKILL.md/source/runtime evidence
  before treating it as a finding;
- submit the result with `scripts/review.py submit-functional`.

The main reviewer must not submit `pass` from static code analysis, instruction
tracing, a SKILL.md workflow walkthrough, an unfinished local command, or
unverified subagent issue claims. If generated-scenario target subagents were not
actually launched and tracked, keep Stage 03 at `requires_ai_review` instead of
fabricating a result.

The result must state:

- whether the test was required;
- whether it was executed;
- `execution_method`: `subagent_dialogue` or `isolated_test_agent`;
- `static_analysis_only`: `false`;
- the user workflows tested;
- intent recognition and skill invocation outcome;
- observed tool/artifact/output evidence;
- output quality result;
- configuration used or missing;
- observed result;
- `recommendation`: `pass`, `blocked`, `needs_config`, `requires_ai_review`, or
  `skip`.

Missing `03-functional-dialogue-test-result.json` for a required functional
stage returns `requires_ai_review` and blocks the final gate as
`needs_ai_review`.

The canonical result schema and helper command live in
`references/staged-review-flow.md`.

## Missing Configuration

If token, API key, MCP server, login, account permission, or dependency setup is
required and unavailable, return `needs_config` with exact instructions for the
user. Stop only for that missing external configuration. If auto-detection is a
false positive, rerun with `--ack-config "confirmed: no external config needed"`;
the stage must then return `requires_ai_review` with a `functional_test_request`
so real subagent dialogue validation can run. This applies in both `workflow`
and `review-only` modes.

In `workflow`, do not mark the package reviewed until configuration is provided,
confirmed unnecessary, or the required dialogue verdict is submitted.

When configuration is discovered during semantic risk review, write the setup
guidance into stage 02. The workflow escalates only if the required external
configuration is still unavailable when functional validation runs. Static instruction
tracing is not enough for a new listing whose advertised behavior depends on
that configuration. If the required external setup is unavailable by stage 03,
functional testing returns `needs_config` with the required fields.

## Blocking

Block when the core advertised workflow cannot be exercised, produces fabricated
success, skips required tool calls, or contradicts the skill instructions.
