# Commercial And Legal Risk Checks

This is part of review block 2. Script keyword matches are only prefilter
signals. The final decision must be a semantic LLM judgment.

## Commercial Diversion

Flag and judge:

- private groups, personal social accounts, payment prompts, praise farming, or
  app/store redirects that are not required for the skill to work;
- external links that move users away from the platform for marketing rather
  than functional setup;
- affiliate, lead-generation, or vendor lock-in language hidden inside usage
  instructions.

Functional links to official docs, API-key consoles, required dependency
downloads, OAuth pages, or product consoles are acceptable when narrowly scoped.

## Legal And Compliance

Flag and judge:

- unauthorized scraping or bulk copying;
- bypassing login, paywalls, rate limits, terms, or platform rules;
- copyright-heavy reproduction or dataset extraction without boundaries;
- high-risk medical, legal, financial, employment, or regulatory advice without
  clear limits and verification instructions;
- privacy-sensitive processing without consent, scope, retention, or deletion
  boundaries.

## Output

Include commercial/legal findings in `02-risk-semantic-review.json`. A blocker
finding blocks the final gate.
