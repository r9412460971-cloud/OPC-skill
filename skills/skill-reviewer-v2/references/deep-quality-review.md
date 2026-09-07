# Deep Quality Review

This is review block 4. It is subagent/isolated-agent semantic review and is required when the
skill body contains substantive content (body ≥ 1 KB).

## Required When

Run deep quality review when:

- mode is `workflow` and `deep_review_context.is_new_listing` is `true`; or
- listing status cannot be determined and `skip_deep_review` is not true; or
- mode is `review-only` and body ≥ 1 KB.

Skip when:

- `deep_review_context.is_new_listing` is `false` (version update in workflow); or
- `skip_deep_review` is true because the body is smaller than 1 KB.

**Important**: `review-only` mode does NOT skip deep quality review by default.
Review-only only skips the upload/approval workflow, not the review itself.
A quality report is incomplete without deep review for any skill with
substantive content.

## Dimensions

Review all 11 dimensions:

1. Executability
2. Context efficiency
3. Fault tolerance and fallback
4. User experience
5. Audience fit
6. Portability
7. Domain accuracy
8. Completeness and boundary clarity
9. Consistency
10. Maintainability
11. Evolvability

## Method

The deep-review subagent must read `SKILL.md` and relevant references/scripts,
then simulate real use:

- happy path on Windows and macOS when applicable;
- at least two likely failure paths;
- repeated similar user requests;
- tool/API/configuration missing cases;
- boundary cases where the description might overpromise.

Judge with concrete evidence, not generic prose. Each dimension must include:

- `score`: integer 1-10, aligned to `rating`;
- at least two concrete evidence items with file, section, metric, line,
  command, field, or example references;
- a rationale explaining why the score follows from the evidence;
- an actionable recommendation, especially when the score is below strong pass;
- cross-dimension implications where relevant, e.g. context inefficiency
  affecting executability or maintainability.

A deep review result can block when quality issues make the skill misleading,
unusable, unsafe, or materially below marketplace expectations. A quick
main-agent summary, generic 11-row scorecard, or inflated score without concrete
evidence is invalid and must leave Stage 04 at `requires_ai_review`.

## Output

Write `04-deep-quality-review-result.json` using the schema in
`staged-review-flow.md`. Without this file for a required review, final
status is `needs_ai_review`. The result must include `reviewed_by` as
`subagent`, `deep_review_subagent`, or `isolated_review_agent`; `review_method`
as `subagent_deep_review` or `isolated_review_agent`; `source_files_reviewed`
including `SKILL.md`; all 11 dimensions; and at least two
`cross_dimension_checks` for a pass verdict.
