# Subagent Strategy

Batch review of two or more skills should parallelize semantic review work.

## What Can Run In Parallel

- Semantic risk review for every reviewed skill.
- Dedicated security false-positive adjudication for B19/B23 findings when a
  skill is documentation-heavy or deterministic evidence is noisy.
- Required functional dialogue validation for new listings, review-only runs,
  and forced update tests.
- Required deep quality review for new listings.
- Context-heavy false-positive adjudication when the main agent needs help.

Deterministic script stages can also run concurrently through `scripts/batch.py`,
but script concurrency is not a substitute for LLM/subagent semantic review.

## Batch Flow

1. Run `scripts/batch.py` or per-skill `scripts/review.py` to produce stage
   directories and semantic review requests.
2. For each skill, dispatch a security subagent for the semantic risk decision,
   then have the main agent quality-gate the result and write it with
   `scripts/review.py submit-risk`.
   If B19/B23 includes high-risk or noisy security findings, prefer a dedicated
   security subagent whose only job is to classify each finding as reachable
   production behavior, documentation/example context, or confirmed blocker.
3. For each skill with required functional validation, dispatch a subagent to
   open the target skill from the `SKILL.md` path and description in
   `03-functional-test.json`, create at least two natural end-user requests,
   observe the target-skill responses, then have the main agent write the
   result with `scripts/review.py submit-functional --execution-method
   subagent_dialogue --static-analysis-only false`.
4. For each new listing requiring deep review, dispatch a subagent for
   the deep quality decision, then have the main agent write it with
   `scripts/review.py submit-deep --review-method subagent_deep_review
   --source-file SKILL.md --cross-check "..."`.
5. Validate each verdict with `scripts/review.py validate-verdict` if it was
   supplied as an existing file.
6. Rerun the final gate so `05-final.json` reflects the collected verdicts.

If subagent capability is unavailable, the main agent may perform semantic risk
review itself when the workflow allows it. Required functional dialogue
validation and required deep quality review must still have a subagent or
equivalent isolated-agent result; otherwise keep the stage at
`requires_ai_review`. Do not mark a skill `reviewed` because subagents were
unavailable.

## Prompt Requirements

Each subagent gets:

- skill name and package path;
- `01-structure.json` and `02-risk.json`;
- the semantic review request from `02-risk.json`;
- B19/B23 finding details, including `capability_scan`, blocker/warning lists,
  and file/line evidence when present;
- `03-functional-test.json` when present, including the generated
  `functional_test_request`, target `SKILL.md` path, description,
  configuration status, and script preflight result;
- `04-deep-review.json` when deep review is required;
- required output file path and schema.

The subagent should return the decision fields plus a short summary. The main
agent should prefer the submit helpers over manual JSON file editing, then rerun
the gate.

For required functional validation, the subagent result must include actual
dialogue turns and observed evidence from natural end-user requests sent to the
target skill. The reviewer JSON schema, scoring criteria, and "simulate a test"
wording must never be pasted into the target-skill conversation. A main-agent
static analysis summary, unfinished command output, or admission that no
subagent was used is not a functional result and must leave Stage 03 at
`requires_ai_review`.

For required deep review, the subagent result must include all 11 dimensions,
per-dimension scores, concrete evidence, rationales, recommendations, reviewed
source files, and cross-dimension checks. A generic scorecard or main-agent
summary is not a deep review result and must leave Stage 04 at
`requires_ai_review`.

Security subagents must explicitly answer whether flagged code is reachable by
normal skill execution. Documentation snippets, test fixtures, placeholders, and
"bad example" sections should not become blockers unless the same behavior is
also present in executable package logic or user-facing instructions that direct
the agent to run it.

The main agent must reject semantic risk results that are only a generic pass,
only repeat deterministic script findings, or omit reviewed files, covered risk
areas, capability inventory, reachability analysis, concrete evidence, and
rationale. If the semantic result is shallow, leave Stage 02 at
`requires_ai_review` and request a deeper security subagent verdict.
