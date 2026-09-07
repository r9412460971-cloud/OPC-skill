#!/usr/bin/env python3
"""CLI and workflow router for skill-reviewer-v2."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

from common import _split_checks, _write_stage_json, parse_frontmatter, _get_skill_version, _load_json_if_exists
from deep_stage import build_deep_review_stage
from deterministic_checks import *  # Backward-compatible exports for tests and batch tooling.
from deterministic_checks import RISK_CHECK_IDS, STRUCTURE_CHECK_IDS, run_review
from functional_stage import run_functional_test_stage
from gate import build_final_stage, build_handling_records, build_review_gate
from log_util import get_review_output_dir, load_pending_review, now_iso, update_pending_status, write_output_file
from metadata import _is_new_upload, _load_source_metadata
from reports import generate_partner_test_report, generate_report
from risk_stage import build_risk_stage
from verdicts import (
    DEEP_REVIEW_FILENAME,
    FUNCTIONAL_DIALOGUE_RESULT_FILENAME,
    REVIEW_AUX_COMMANDS,
    REVIEW_EXEMPTIONS_FILENAME,
    SEMANTIC_REVIEW_FILENAME,
    run_review_aux_command,
)


def _load_review_exemptions(output_dir: Path) -> list[dict]:
    data = _load_json_if_exists(output_dir / REVIEW_EXEMPTIONS_FILENAME)
    exemptions = data.get("exemptions") if isinstance(data, dict) else []
    return [item for item in exemptions or [] if isinstance(item, dict) and item.get("check_id")]


def _apply_review_exemptions(review_result: dict, exemptions: list[dict]) -> dict:
    if not exemptions:
        return review_result
    by_id: dict[str, dict] = {}
    for item in exemptions:
        check_id = str(item.get("check_id") or "").strip()
        if check_id:
            by_id[check_id] = item
    if not by_id:
        return review_result

    checks = []
    applied = []
    for check in review_result.get("checks", []) or []:
        if not isinstance(check, dict):
            checks.append(check)
            continue
        check_id = str(check.get("id") or "")
        exemption = by_id.get(check_id)
        if exemption:
            check = dict(check)
            original_pass = check.get("pass", True)
            if not check.get("pass", True):
                applied.append({
                    "check_id": check_id,
                    "from": "blocker",
                    "to": "warning",
                    "reason": exemption.get("reason", ""),
                    "decision": exemption.get("decision", "false_positive"),
                })
            check["pass"] = True
            check["warning"] = True
            check["false_positive"] = exemption.get("decision") == "false_positive"
            check["exemption"] = exemption
            msg = check.get("msg", "")
            reason = exemption.get("reason", "")
            if reason and "exempted:" not in msg:
                check["msg"] = f"{msg} (exempted: {reason})"
            details = check.get("details")
            if not original_pass and isinstance(details, dict) and details.get("status") == "blocked":
                details = dict(details)
                details["original_status"] = details.get("status")
                details["status"] = "passed"
                details["exemption"] = exemption
                summary = str(details.get("summary") or "")
                if reason and "exempted:" not in summary:
                    details["summary"] = f"{summary} (exempted: {reason})" if summary else f"exempted: {reason}"
                check["details"] = details
        checks.append(check)

    review_result = dict(review_result)
    review_result["checks"] = checks
    review_result["review_exemptions"] = exemptions
    review_result["applied_exemptions"] = applied
    blockers = [c for c in checks if isinstance(c, dict) and not c.get("pass", True)]
    warnings = [c for c in checks if isinstance(c, dict) and c.get("warning")]
    review_result["blocker_count"] = len(blockers)
    review_result["warning_count"] = len(warnings)
    review_result["status"] = "passed" if not blockers else "blocked"
    return review_result


def run_staged_review(
    skill_dir: Path,
    skill_name: str = "",
    *,
    mode: str = "workflow",
    stage: str = "all",
    output_dir: str | Path | None = None,
    date: str | None = None,
    force_test: bool = False,
    force_functional: bool = False,
    config_ack: str = "",
    semantic_review_file: str | Path | None = None,
    functional_test_file: str | Path | None = None,
    deep_review_file: str | Path | None = None,
    autopilot: bool = False,
) -> dict:
    """Run deterministic review, staged AI requests, and final gate assembly."""
    base_result = run_review(skill_dir, skill_name, mode=mode)
    skill_name = base_result.get("skill_name") or skill_name or skill_dir.name
    out_dir = Path(output_dir) if output_dir else get_review_output_dir(skill_name, date)
    out_dir.mkdir(parents=True, exist_ok=True)
    base_result = _apply_review_exemptions(base_result, _load_review_exemptions(out_dir))

    checks_structure = _split_checks(base_result, STRUCTURE_CHECK_IDS)
    checks_risk = _split_checks(base_result, RISK_CHECK_IDS)

    structure_stage = {
        "stage": "structure",
        "skill_name": skill_name,
        "status": "passed" if all(c.get("pass", True) for c in checks_structure) else "blocked",
        "checks": checks_structure,
        "frontmatter": base_result.get("frontmatter", {}),
        "generated_at": now_iso(),
    }
    risk_stage = build_risk_stage(
        skill_dir,
        skill_name,
        base_result,
        checks_risk,
        out_dir,
        semantic_review_file=semantic_review_file,
    )
    base_result["risk_stage"] = risk_stage
    functional_stage = run_functional_test_stage(
        skill_dir,
        skill_name,
        base_result,
        out_dir,
        force_test=force_test,
        force_functional=force_functional,
        config_ack=config_ack,
        functional_test_file=functional_test_file,
    )
    deep_stage = build_deep_review_stage(base_result, out_dir, deep_review_file=deep_review_file)
    final_stage = build_final_stage(base_result, structure_stage, risk_stage, functional_stage, deep_stage)

    selected = {"structure", "risk", "functional", "deep", "final"} if stage == "all" else {stage}
    paths = {}
    if "structure" in selected:
        paths["structure"] = _write_stage_json(out_dir, "01-structure.json", structure_stage)
    if "risk" in selected:
        paths["risk"] = _write_stage_json(out_dir, "02-risk.json", risk_stage)
    if "functional" in selected:
        paths["functional"] = _write_stage_json(out_dir, "03-functional-test.json", functional_stage)
    if "deep" in selected:
        paths["deep"] = _write_stage_json(out_dir, "04-deep-review.json", deep_stage)
    if "final" in selected:
        paths["final"] = _write_stage_json(out_dir, "05-final.json", final_stage)

    base_result["mode"] = mode
    base_result["stage"] = stage
    base_result["review_output_dir"] = str(out_dir)
    base_result["stage_paths"] = paths
    base_result["final_status"] = final_stage["status"]
    base_result["review_gate"] = final_stage["review_gate"]
    base_result["reviewed_version"] = final_stage.get("reviewed_version", "")
    base_result["functional_test"] = functional_stage
    base_result["risk_stage"] = risk_stage
    base_result["deep_stage"] = deep_stage
    base_result["handling_records"] = final_stage.get("handling_records", [])
    base_result["handling_record_count"] = final_stage.get("handling_record_count", 0)
    if autopilot:
        base_result["workflow_next"] = build_autopilot_workflow(skill_dir, base_result)
    return base_result


def _quote_cmd_path(value: str | Path) -> str:
    return '"' + str(value).replace('"', '\\"') + '"'


def _workflow_action_submit_command(kind: str, out_dir: Path, target_file: Path) -> str:
    script = Path(__file__).resolve()
    command = {
        "risk": "submit-risk",
        "functional": "submit-functional",
        "deep": "submit-deep",
    }[kind]
    return f"python {_quote_cmd_path(script)} {command} --review-output-dir {_quote_cmd_path(out_dir)} --from-file {_quote_cmd_path(target_file)}"


def build_autopilot_workflow(skill_dir: Path, review_result: dict) -> dict:
    out_dir = Path(review_result.get("review_output_dir") or ".").resolve()
    risk_stage = review_result.get("risk_stage") or {}
    functional_stage = review_result.get("functional_test") or {}
    deep_stage = review_result.get("deep_stage") or {}
    final_status = review_result.get("final_status") or ""
    actions = []

    semantic = risk_stage.get("semantic_review") or {}
    if risk_stage.get("status") == "requires_ai_review" or semantic.get("status") in {"missing", "invalid"}:
        target = out_dir / "02-risk-semantic-review.json"
        actions.append({
            "id": "risk_semantic_verdict",
            "type": "agent_verdict",
            "input_file": str(out_dir / "02-risk.json"),
            "write_file": str(target),
            "submit_command": _workflow_action_submit_command("risk", out_dir, target),
        })

    functional_rec = functional_stage.get("recommendation", functional_stage.get("overall", ""))
    if functional_rec == "requires_ai_review" and functional_stage.get("required"):
        target = out_dir / "03-functional-dialogue-test-result.json"
        actions.append({
            "id": "functional_dialogue_verdict",
            "type": "agent_verdict",
            "input_file": str(out_dir / "03-functional-test.json"),
            "write_file": str(target),
            "submit_command": _workflow_action_submit_command("functional", out_dir, target),
        })

    if deep_stage.get("status") == "requires_ai_review":
        target = out_dir / "04-deep-quality-review-result.json"
        actions.append({
            "id": "deep_quality_verdict",
            "type": "agent_verdict",
            "input_file": str(out_dir / "04-deep-review.json"),
            "write_file": str(target),
            "submit_command": _workflow_action_submit_command("deep", out_dir, target),
        })

    if final_status == "reviewed":
        actions.append({
            "id": "continue_upload_dry_run",
            "type": "next_phase",
            "command": f"python {_quote_cmd_path('C:/Users/Administrator/.workbuddy/skills/skill-uploader/scripts/upload.py')} publish {_quote_cmd_path(skill_dir.resolve())} --dry-run",
        })
    elif final_status == "needs_config":
        actions.append({
            "id": "external_config_required",
            "type": "ask_user",
            "instructions": functional_stage.get("needs_config_instructions", []),
        })
    elif final_status == "blocked" and not actions:
        actions.append({
            "id": "blocked_review_gate",
            "type": "stop",
            "input_file": str(out_dir / "05-final.json"),
        })

    return {
        "mode": "autopilot",
        "phase": "review",
        "status": final_status,
        "ask_user_now": any(action.get("type") == "ask_user" for action in actions),
        "actions": actions,
    }


def update_pending_from_workflow(skill_dir: Path, review_result: dict, date: str = "", pending_file: str = "") -> dict:
    """Write the final workflow gate back to pending-review using cache_path identity."""
    skill_name = review_result.get("skill_name") or skill_dir.name
    final_status = review_result.get("final_status") or review_result.get("status")
    stage_paths = review_result.get("stage_paths") or {}
    if final_status not in {"reviewed", "blocked", "needs_config", "needs_ai_review"}:
        return {"status": "skipped", "reason": f"final status {final_status!r} is not a workflow queue status", "skill_name": skill_name}
    if not stage_paths.get("final"):
        return {"status": "skipped", "reason": "final stage path missing", "skill_name": skill_name}

    extra_fields = {
        "review_output_dir": review_result.get("review_output_dir", ""),
        "final_review_path": stage_paths.get("final", ""),
        "review_gate": review_result.get("review_gate", {}),
        "reviewed_version": review_result.get("reviewed_version", ""),
        "handling_record_count": review_result.get("handling_record_count", 0),
        "workflow_state": final_status,
        "reviewed_at": now_iso(),
    }
    if final_status == "reviewed":
        extra_fields.update({
            "block_reason": "",
            "block_reasons": [],
            "confirmation_question": "",
            "requires_user_confirmation": False,
            "needs_confirm_files": [],
            "last_status_update_error": "",
        })
    effective_date = date or None
    if not effective_date and not pending_file:
        try:
            data = load_pending_review(all_dates=True)
            skill_dir_resolved = str(skill_dir.resolve()).lower()
            for item in data.get("items", []):
                paths = [
                    item.get("cache_path", ""),
                    item.get("processed_cache_path", ""),
                    item.get("skill_dir", ""),
                    item.get("source_cache_path", ""),
                ]
                if (item.get("skill_name") or item.get("name")) == skill_name and any(p and str(Path(p).expanduser().resolve()).lower() == skill_dir_resolved for p in paths):
                    effective_date = item.get("_pending_date") or item.get("pending_date") or None
                    break
        except Exception:
            effective_date = None

    updated = update_pending_status(
        skill_name,
        final_status,
        extra_fields=extra_fields,
        date=effective_date,
        explicit_path=pending_file or None,
        match_fields={"cache_path": str(skill_dir)},
    )
    return {
        "status": "updated" if updated else "not_updated",
        "skill_name": skill_name,
        "new_status": final_status,
        "match": {"cache_path": str(skill_dir)},
        "pending_date": effective_date or "",
        "final_review_path": stage_paths.get("final", ""),
    }


def main() -> None:
    import argparse

    if len(sys.argv) > 1 and sys.argv[1] in REVIEW_AUX_COMMANDS:
        sys.exit(run_review_aux_command(sys.argv[1:]))

    parser = argparse.ArgumentParser(description="Skill Reviewer v2 (Platform Mode)")
    parser.add_argument("skill_dir", help="Skill ????")
    parser.add_argument("--skill-name", default="", help="Skill ?????? SKILL.md ???")
    parser.add_argument("--mode", choices=["workflow", "review-only"], default="workflow", help="????")
    parser.add_argument("--stage", choices=["structure", "risk", "functional", "deep", "final", "all"], default="all", help="?????????")
    parser.add_argument("--date", default="", help="review-output ?????????")
    parser.add_argument("--pending-file", help="?? pending-review ?????workflow final/all ?? cache_path ?????")
    parser.add_argument("--review-output-dir", help="??? JSON ????")
    parser.add_argument("--force-test", action="store_true", help="Require Stage 03 functional testing for workflow version updates")
    parser.add_argument("--force-functional", action="store_true", help="Require Stage 03 and bypass the auto config gate after reviewer confirmation")
    parser.add_argument("--ack-config", default="", help="Reviewer/user acknowledgement that detected config is not required for this functional test run")
    parser.add_argument("--semantic-review-file", help="LLM/subagent semantic risk verdict JSON")
    parser.add_argument("--functional-test-file", help="Subagent functional dialogue test result JSON")
    parser.add_argument("--deep-review-file", help="LLM/subagent deep quality review result JSON")
    parser.add_argument("--autopilot", action="store_true", help="Output strict workflow_next actions for automatic continuation")
    parser.add_argument("--report-verification-file", help="LLM/human verified report issue JSON; required for final-quality report conclusions")
    parser.add_argument("--output-file", help="??????")
    parser.add_argument("--output-mode", choices=["quiet", "summary", "verbose"], default="", help="?????????")
    parser.add_argument("--save-report", help="???????????")
    parser.add_argument("--save-partner-report", help="???????????")

    args = parser.parse_args()
    skill_dir = Path(args.skill_dir)
    if not skill_dir.is_dir():
        print(f"ERROR: ?????: {skill_dir}", file=sys.stderr)
        sys.exit(1)

    data = run_staged_review(
        skill_dir,
        args.skill_name,
        mode=args.mode,
        stage=args.stage,
        output_dir=args.review_output_dir,
        date=args.date or None,
        force_test=args.force_test,
        force_functional=args.force_functional,
        config_ack=args.ack_config,
        semantic_review_file=args.semantic_review_file,
        functional_test_file=args.functional_test_file,
        deep_review_file=args.deep_review_file,
        autopilot=args.autopilot,
    )

    if args.report_verification_file:
        try:
            data["report_verification"] = json.loads(Path(args.report_verification_file).read_text(encoding="utf-8-sig"))
        except Exception as exc:
            print(f"ERROR: failed to load report verification file: {exc}", file=sys.stderr)
            sys.exit(1)

    save_report_path = args.save_report
    if args.mode == "review-only" and not save_report_path and not args.save_partner_report:
        save_report_path = str(Path(data.get("review_output_dir") or ".") / f"{data['skill_name']}-review-report.md")
    if save_report_path:
        report = generate_report(data)
        Path(save_report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(save_report_path).write_text(report, encoding="utf-8")
        data["saved_report_path"] = save_report_path
    if args.save_partner_report:
        report = generate_partner_test_report(data)
        Path(args.save_partner_report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save_partner_report).write_text(report, encoding="utf-8")

    pending_update = {}
    if args.mode == "workflow" and args.stage in {"all", "final"}:
        pending_update = update_pending_from_workflow(skill_dir, data, args.date or "", args.pending_file or "")
        data["pending_update"] = pending_update

    output_data = data
    final_path = (data.get("stage_paths") or {}).get("final")
    if args.mode == "workflow" and args.stage in {"all", "final"} and final_path:
        try:
            output_data = json.loads(Path(final_path).read_text(encoding="utf-8-sig"))
        except Exception:
            output_data = data
        if pending_update:
            output_data["pending_update"] = pending_update
        if args.autopilot and data.get("workflow_next"):
            output_data["workflow_next"] = data["workflow_next"]
    write_output_file(
        args.output_file,
        output_data,
        f"{data['skill_name']}: {data.get('final_status', data['status'])} ({data['blocker_count']} blockers, {data['warning_count']} warnings)",
        output_mode=args.output_mode or None,
    )


if __name__ == "__main__":
    main()
