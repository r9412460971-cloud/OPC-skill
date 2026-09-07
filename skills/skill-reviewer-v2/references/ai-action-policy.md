# AI Action Policy

AI resolves blockers and warnings itself whenever package evidence is sufficient.
User escalation is reserved for cases where external information is missing,
required configuration is unavailable, or the AI verdict identifies a real issue
that needs an owner decision.

Review output records every decision. Safe mechanical fixes may run by default
when the reviewer has high confidence, including false-positive classification,
strict semver metadata repairs, frontmatter ordering, and obvious YAML syntax
cleanup. Version bumping is explicitly excluded: version progression must be
resolved by skill-fetcher-v2 before pending-review, and reviewer B12 only
validates or blocks. These edits must stay tiny, deterministic, and fully
recorded. Semantic content, external links, dependency behavior,
security-sensitive instructions, and business/legal positioning are handled
through verdicts and findings, not silent edits.

Every pass, warning, blocker, AI verdict, escalation, skipped stage, and applied
fix must be captured in the review output handling records.
