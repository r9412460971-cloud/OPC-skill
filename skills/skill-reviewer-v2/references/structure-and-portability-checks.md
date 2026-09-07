# Structure And Portability Checks

This is review block 1. Run it before risk, functional, or deep review.

## Deterministic Structure Checks

The script checks:

- `SKILL.md` exists and has valid YAML frontmatter.
- `name`, `description`, and `version` meet package rules.
- Body content is substantive.
- Local `references/` and `scripts/` links are valid.
- `allowed-tools` usage is explained when present.
- Install/setup guidance exists when tools, MCP, API keys, scripts, or external
  dependencies are required.
- **Environment configuration guidance** exists when the skill depends on MCP
  services, API endpoints, OAuth/token authentication, or external accounts.
  A bare declaration in the `compatibility` frontmatter field does NOT satisfy
  this check — the skill body must contain a dedicated section explaining how
  to obtain credentials and how to enable the service in the runtime
  environment (e.g. which MCP connector to trust, where to get an API key,
  what account permissions are needed). When guidance is missing, B20 emits a
  blocker-level finding (not just a warning).
- Package size stays within marketplace limits.
- **No changelog / release notes in SKILL.md body.** SKILL.md is loaded into
  context on every invocation; changelog entries are pure cost with zero
  execution value. Version history belongs in git commits, platform release
  notes, or a separate `CHANGELOG.md` — never in the skill body. When
  detected, B21 emits a blocker-level finding.

Listing workflow metadata, such as first-listing source channel and source
locator fields, is outside pure package structure in `review-only` mode. It is
checked only by the `workflow` / upload-review path.

## P01 macOS/Windows Portability Precheck

P01 is a warning-level deterministic precheck. It scans text files and scripts
for obvious portability concerns:

- only `.sh` entrypoints without Windows alternatives;
- only `.ps1`, `.bat`, or `.cmd` entrypoints without macOS/Linux alternatives;
- hardcoded Windows paths such as `C:\...`;
- hardcoded Unix/macOS paths such as `/Users/...`, `/home/...`, `/tmp/...`;
- platform-specific commands such as `open`, `xdg-open`, `cmd /c`, or
  `powershell` without documented alternatives.

P01 does not replace semantic portability review. Deep quality review must still
judge whether the package is realistically usable on Windows and macOS.

## Handling Boundary

Portability and structure warnings should be resolved by AI judgment when the
package evidence is sufficient. Escalate only when external information is
missing or a real issue needs an owner decision. High-confidence tiny mechanical fixes may be applied and must be recorded; otherwise record the AI verdict or escalation.
