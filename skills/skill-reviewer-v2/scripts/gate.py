"""Final gate and handling-record construction."""

from __future__ import annotations

from common import _get_skill_version
from log_util import now_iso


def build_handling_records(
    review_result: dict,
    risk_stage: dict | None = None,
    functional_stage: dict | None = None,
    deep_stage: dict | None = None,
) -> list[dict]:
    """Build a compact audit trail for every review decision and escalation."""
    records: list[dict] = []
    for check in review_result.get("checks", []) or []:
        check_id = check.get("id", "")
        passed = check.get("pass", True)
        warning = bool(check.get("warning"))
        if not passed:
            outcome = "blocker"
            handling = "blocked_with_recorded_evidence"
        elif warning:
            outcome = "warning"
            handling = "recorded_for_ai_assessment"
        else:
            outcome = "pass"
            handling = "accepted"
        records.append({
            "type": "deterministic_check",
            "id": check_id,
            "outcome": outcome,
            "handling": handling,
            "requires_user_confirmation": False,
            "message": check.get("msg", ""),
        })

    risk_stage = risk_stage or {}
    semantic = risk_stage.get("semantic_review") or {}
    if semantic:
        semantic_status = semantic.get("status", "unknown")
        records.append({
            "type": "semantic_risk_review",
            "outcome": semantic_status,
            "handling": "requires_ai_verdict" if semantic_status in {"missing", "invalid"} else "ai_verdict_recorded",
            "requires_user_confirmation": False,
            "path": semantic.get("path") or risk_stage.get("semantic_review_file", ""),
            "summary": semantic.get("summary", ""),
        })

    script_link = risk_stage.get("script_link_validation") or {}
    if script_link:
        records.append({
            "type": "script_link_validation",
            "outcome": script_link.get("status", "unknown"),
            "handling": "blocked_with_recorded_evidence" if script_link.get("status") == "blocked" else "recorded",
            "requires_user_confirmation": False,
            "summary": script_link.get("summary", ""),
        })

    functional_stage = functional_stage or {}
    if functional_stage:
        rec = functional_stage.get("recommendation", functional_stage.get("overall", "unknown"))
        outcome = functional_stage.get("status", rec) if functional_stage.get("skipped") else rec
        if functional_stage.get("skipped"):
            handling = "skipped_by_rule"
        elif rec == "requires_ai_review" and functional_stage.get("required"):
            handling = "requires_subagent_dialogue_test"
        elif rec == "needs_config" and functional_stage.get("required"):
            handling = "requires_external_configuration"
        else:
            handling = "recorded"
        records.append({
            "type": "functional_validation",
            "outcome": outcome,
            "handling": handling,
            "requires_user_confirmation": bool(rec == "needs_config" and functional_stage.get("required")),
            "instructions": functional_stage.get("needs_config_instructions", []),
            "result_file": functional_stage.get("result_file", ""),
            "skip_reason": functional_stage.get("skip_reason", ""),
        })

    deep_stage = deep_stage or {}
    if deep_stage:
        deep_status = deep_stage.get("status", "unknown")
        records.append({
            "type": "deep_quality_review",
            "outcome": deep_status,
            "handling": "requires_ai_verdict" if deep_status == "requires_ai_review" else "recorded",
            "requires_user_confirmation": False,
            "skip_reason": deep_stage.get("skip_reason", ""),
        })

    for action in review_result.get("ai_actions", []) or []:
        if not isinstance(action, dict):
            continue
        records.append({
            "type": "ai_action",
            "field": action.get("field", ""),
            "action_type": action.get("action_type", ""),
            "outcome": "pending_ai_resolution",
            "handling": "ai_should_resolve_without_user_unless_evidence_is_insufficient_or_blocking",
            "requires_user_confirmation": False,
            "priority": action.get("priority", ""),
        })

    for exemption in review_result.get("review_exemptions", []) or []:
        if not isinstance(exemption, dict):
            continue
        records.append({
            "type": "review_exemption",
            "id": exemption.get("check_id", ""),
            "outcome": exemption.get("decision", "false_positive"),
            "handling": "removed_from_blocking_checks_with_recorded_rationale",
            "requires_user_confirmation": False,
            "reason": exemption.get("reason", ""),
            "reviewed_by": exemption.get("reviewed_by", ""),
        })

    return records


def build_review_gate(review_result: dict, functional_stage: dict | None = None, deep_stage: dict | None = None) -> dict:
    functional_stage = functional_stage or {}
    deep_stage = deep_stage or {}
    risk_stage = review_result.get("risk_stage", {}) or {}
    checks = review_result.get("checks", [])
    blocking_checks = [c.get("id", "") for c in checks if not c.get("pass", True)]
    warning_checks = [c.get("id", "") for c in checks if c.get("warning")]
    functional_rec = functional_stage.get("recommendation", functional_stage.get("overall", "skip"))
    functional_block = functional_rec in {"needs_config", "blocked"} and functional_stage.get("required")
    functional_ai_required = functional_rec == "requires_ai_review" and functional_stage.get("required")
    risk_status = risk_stage.get("status", "unknown")
    deep_status = deep_stage.get("status", "unknown")
    risk_ai_required = risk_status == "requires_ai_review"
    deep_ai_required = deep_status == "requires_ai_review"
    risk_block = risk_status == "blocked"
    deep_block = deep_status == "blocked"
    if risk_ai_required or deep_ai_required or functional_ai_required:
        status = "needs_ai_review"
    elif functional_rec == "needs_config" and functional_stage.get("required"):
        status = "needs_config"
    elif not blocking_checks and not functional_block and not risk_block and not deep_block:
        status = "pass"
    else:
        status = "blocked"
    extra_blockers = []
    if functional_block:
        extra_blockers.append("functional")
    if functional_ai_required:
        extra_blockers.append("functional_dialogue_test_required")
    if risk_block:
        script_link_status = ((risk_stage.get("script_link_validation") or {}).get("status") or "")
        extra_blockers.append("script_link_risk" if script_link_status == "blocked" else "semantic_risk")
    if deep_block:
        extra_blockers.append("deep_review")
    if risk_ai_required:
        extra_blockers.append("semantic_risk_review_required")
    if deep_ai_required:
        extra_blockers.append("deep_quality_review_required")
    fm = review_result.get("frontmatter", {}) if isinstance(review_result.get("frontmatter"), dict) else {}
    is_workflow = review_result.get("mode", "workflow") == "workflow"
    return {
        "status": status,
        "skill_name": review_result.get("skill_name", ""),
        "version": _get_skill_version(fm)[0],
        "blocking_checks": blocking_checks + extra_blockers,
        "warning_checks": warning_checks,
        "blocker_count": len(blocking_checks) + len(extra_blockers),
        "warning_count": len(warning_checks),
        "functional": functional_rec,
        "risk": risk_status,
        "deep_review": deep_stage.get("status", "unknown"),
        "needs_config_instructions": functional_stage.get("needs_config_instructions", [])
            if functional_rec == "needs_config" and functional_stage.get("required") else [],
        "can_upload": bool(is_workflow and status == "pass"),
        "checked_at": now_iso(),
    }


def _stage_summaries(structure_stage: dict, risk_stage: dict, functional_stage: dict, deep_stage: dict, review_gate: dict) -> dict:
    functional_result = functional_stage.get("result") if isinstance(functional_stage.get("result"), dict) else {}
    functional_scenarios = functional_stage.get("scenarios") or functional_result.get("scenarios") or []
    deep_result = deep_stage.get("result") if isinstance(deep_stage.get("result"), dict) else {}
    deep_dimensions = deep_result.get("dimensions") if isinstance(deep_result, dict) else []
    scores = []
    for dim in deep_dimensions or []:
        if not isinstance(dim, dict):
            continue
        score = dim.get("score")
        if isinstance(score, (int, float)):
            scores.append(float(score))
    deep_avg = round(sum(scores) / len(scores), 1) if scores else None
    structure_checks = structure_stage.get("checks") or []
    return {
        "structure": {
            "status": structure_stage.get("status"),
            "check_count": len(structure_checks),
            "warnings": [c.get("id", "") for c in structure_checks if isinstance(c, dict) and c.get("warning")],
        },
        "risk": {
            "status": risk_stage.get("status"),
            "summary": ((risk_stage.get("semantic_review") or {}).get("summary") or (risk_stage.get("script_link_validation") or {}).get("summary") or ""),
        },
        "functional": {
            "status": functional_stage.get("status") if functional_stage.get("skipped") else functional_stage.get("recommendation", functional_stage.get("overall")),
            "scenario_count": len(functional_scenarios) if isinstance(functional_scenarios, list) else 0,
            "summary": functional_stage.get("summary") or functional_result.get("summary", ""),
        },
        "deep": {
            "status": deep_stage.get("status"),
            "average_score": deep_avg,
            "dimension_count": len(deep_dimensions or []) if isinstance(deep_dimensions, list) else 0,
            "weak_dimensions": [d.get("id", "") for d in deep_dimensions or [] if isinstance(d, dict) and str(d.get("rating") or "").lower() in {"needs_work", "blocked", "poor"}],
        },
        "final": {
            "status": review_gate.get("status"),
            "can_upload": review_gate.get("can_upload"),
            "blocker_count": review_gate.get("blocker_count"),
            "warning_count": review_gate.get("warning_count"),
        },
    }



def build_final_stage(review_result: dict, structure_stage: dict, risk_stage: dict, functional_stage: dict, deep_stage: dict) -> dict:
    functional_rec = functional_stage.get("recommendation", "skip")
    functional_block = functional_rec in {"needs_config", "blocked"} and functional_stage.get("required")
    functional_ai_required = functional_rec == "requires_ai_review" and functional_stage.get("required")
    blockers = review_result.get("blocker_count", 0)
    if risk_stage.get("status") == "requires_ai_review" or deep_stage.get("status") == "requires_ai_review" or functional_ai_required:
        final_status = "needs_ai_review"
    elif functional_rec == "needs_config" and functional_stage.get("required"):
        final_status = "needs_config"
    elif blockers == 0 and not functional_block and risk_stage.get("status") != "blocked" and deep_stage.get("status") != "blocked":
        final_status = "reviewed"
    else:
        final_status = "blocked"
    review_result["risk_stage"] = risk_stage
    review_gate = build_review_gate(review_result, functional_stage, deep_stage)
    handling_records = build_handling_records(review_result, risk_stage, functional_stage, deep_stage)
    is_workflow = review_result.get("mode", "workflow") == "workflow"
    is_new_listing = is_workflow and review_result.get("deep_review_context", {}).get("is_new_listing") is not False
    return {
        "stage": "final",
        "skill_name": review_result.get("skill_name", ""),
        "status": final_status,
        "workflow_state": final_status,
        "review_gate": review_gate,
        "needs_config_instructions": functional_stage.get("needs_config_instructions", [])
            if final_status == "needs_config" else [],
        "review_status": review_result.get("status"),
        "blocker_count": blockers,
        "warning_count": review_result.get("warning_count", 0),
        "ai_actions": review_result.get("ai_actions", []),
        "handling_records": handling_records,
        "handling_record_count": len(handling_records),
        "stage_status": {
            "structure": structure_stage.get("status"),
            "risk": risk_stage.get("status"),
            "functional": functional_stage.get("status") if functional_stage.get("skipped")
                else functional_stage.get("recommendation", functional_stage.get("overall")),
            "deep": deep_stage.get("status"),
        },
        "stage_summaries": _stage_summaries(structure_stage, risk_stage, functional_stage, deep_stage, review_gate),
        "frontmatter": review_result.get("frontmatter", {}),
        "partner_report_offer": {
            "should_ask_user": is_new_listing,
            "message": "首次上架审查已完成。是否需要生成合作方 Skill 测试报告？",
            "suggested_cli": "--save-partner-report <path>",
        },
        "reviewed_version": review_gate.get("version", ""),
        "completed_at": now_iso(),
    }
