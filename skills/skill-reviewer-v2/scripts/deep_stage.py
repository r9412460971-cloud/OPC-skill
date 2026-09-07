"""Deep quality review stage construction."""

from __future__ import annotations

from pathlib import Path

from common import _load_json_if_exists
from verdicts import DEEP_REVIEW_FILENAME, _normalize_deep_verdict, validate_deep_verdict


def build_deep_review_stage(review_result: dict, output_dir: Path, deep_review_file: str | Path | None = None) -> dict:
    ctx = review_result.get("deep_review_context", {})
    is_update = ctx.get("is_new_listing") is False
    # Deep review is required for new listings AND for review-only when body >= 1KB.
    # It is only skipped for version updates or when body is too small.
    required = not is_update and not ctx.get("skip_deep_review", False)
    skipped = bool(is_update or ctx.get("skip_deep_review", False))
    candidate = Path(deep_review_file) if deep_review_file else output_dir / DEEP_REVIEW_FILENAME
    result = _load_json_if_exists(candidate) if required else {}
    if required and not result:
        result = {
            "status": "missing",
            "path": str(candidate),
            "required": True,
            "reason": "deep_quality_review_required",
        }
    errors: list[str] = []
    warnings: list[str] = []
    if required and result:
        result = _normalize_deep_verdict(result)
        errors, warnings = validate_deep_verdict(result)
    if skipped:
        status = "skipped"
    elif errors:
        status = "requires_ai_review"
    elif result.get("status") in {"pass", "passed", "completed"}:
        status = "passed"
    elif result.get("status") in {"blocked", "failed"}:
        status = "blocked"
    else:
        status = "requires_ai_review"
    return {
        "stage": "deep",
        "skill_name": review_result.get("skill_name", ""),
        "required": required,
        "skipped": skipped,
        "skip_reason": "version_update" if is_update else ctx.get("skip_reason", ""),
        "dimensions": review_result.get("deep_review_prompt", {}).get("dimensions", []) if review_result.get("deep_review_prompt") else [],
        "prompt": review_result.get("deep_review_prompt"),
        "result_file": str(candidate) if required else "",
        "result": result,
        "errors": errors,
        "warnings": warnings,
        "status": status,
    }
