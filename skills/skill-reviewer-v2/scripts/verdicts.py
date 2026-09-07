"""Verdict schemas, validators, and submit helper commands."""

from __future__ import annotations

import json
import re
from pathlib import Path

from common import _load_json_if_exists
from gate import build_final_stage
from log_util import now_iso, write_output_file


SEMANTIC_REVIEW_FILENAME = "02-risk-semantic-review.json"
FUNCTIONAL_DIALOGUE_RESULT_FILENAME = "03-functional-dialogue-test-result.json"
DEEP_REVIEW_FILENAME = "04-deep-quality-review-result.json"
REVIEW_EXEMPTIONS_FILENAME = "review-exemptions.json"

REVIEW_AUX_COMMANDS = {"submit-risk", "submit-functional", "submit-deep", "submit-exemption", "validate-verdict", "schema"}
SEMANTIC_CATEGORIES = {
    "security",
    "credential",
    "network",
    "unsafe_execution",
    "commercial_diversion",
    "config_guidance",
    "legal",
    "privacy",
    "prompt_injection",
    "other",
}
SEMANTIC_SEVERITIES = {"none", "low", "medium", "high", "critical"}
SEMANTIC_DECISIONS = {"pass", "warning", "blocker"}
SEMANTIC_REVIEWERS = {"subagent", "security_subagent", "isolated_security_agent"}
SEMANTIC_REVIEW_METHODS = {"subagent_semantic_security_review", "isolated_security_review"}
SEMANTIC_REQUIRED_RISK_AREAS = {
    "credential",
    "privacy",
    "network",
    "unsafe_execution",
    "prompt_injection",
    "commercial_diversion",
    "legal",
    "configuration",
}
SEMANTIC_REACHABILITY = {"production", "install_runtime", "documentation_example", "test_fixture", "not_reachable", "unknown"}
SEMANTIC_CATEGORY_ALIASES = {
    "configuration": "config_guidance",
    "config": "config_guidance",
}
SEMANTIC_SHALLOW_PATTERNS = [
    r"\bno obvious\b",
    r"\blooks fine\b",
    r"\bseems safe\b",
    r"\bquick (check|look)\b",
    r"\bkeyword\b.*\bonly\b",
    r"\bnot deeply reviewed\b",
]
QUALITY_RATINGS = {"excellent", "good", "needs_work", "blocked"}
DEEP_REVIEW_METHODS = {"subagent_deep_review", "isolated_review_agent"}
DEEP_REVIEWERS = {"subagent", "deep_review_subagent", "isolated_review_agent"}
QUALITY_DIMENSION_IDS = {
    "executability",
    "context_efficiency",
    "fault_tolerance",
    "user_experience",
    "audience_fit",
    "portability",
    "domain_accuracy",
    "completeness_boundary",
    "consistency",
    "maintainability",
    "evolvability",
}
FUNCTIONAL_EXECUTION_METHODS = {"subagent_dialogue", "isolated_test_agent"}
FUNCTIONAL_INTENT_RESULTS = {"yes", "partial", "no"}
FUNCTIONAL_SKILL_INVOCATION_RESULTS = {"yes", "partial", "no", "not_observable"}
FUNCTIONAL_OUTPUT_QUALITY_RESULTS = {"pass", "warn", "blocked"}
FUNCTIONAL_STATIC_ANALYSIS_PATTERNS = [
    r"\bstatic analysis\b",
    r"\bcode review\b",
    r"\bstatic reading\b",
    r"\binstruction tracing\b",
    r"\bdid not (actually )?(run|execute)\b",
    r"\bwithout (a )?subagent\b",
    r"\bno subagent\b",
    r"静态分析",
    r"代码分析",
    r"静态阅读",
    r"未实际",
    r"没有实际",
    r"未真正",
    r"没有真正",
    r"未调用\s*subagent",
    r"没有调用\s*subagent",
    r"没有用\s*subagent",
]
FUNCTIONAL_TRACE_WALKTHROUGH_PATTERNS = [
    r"\btrace through\b.*\bSKILL\.md\b",
    r"\bwalk(?:ing)? through\b.*\bSKILL\.md\b",
    r"\bworkflow walkthrough\b",
    r"\btrace.*workflow\b",
    r"\binstruction walkthrough\b",
    r"追踪.*SKILL\.md",
    r"走查.*SKILL\.md",
    r"按.*SKILL\.md.*流程",
    r"流程.*走查",
    r"指令.*走查",
]
FUNCTIONAL_HARNESS_PROMPT_PATTERNS = [
    r"按以下.*JSON.*格式.*功能测试",
    r"精确的\s*JSON\s*格式",
    r"structured functional test result",
    r"functional test result",
    r"simulate\s+\d+\s+real.*dialogue",
    r"simulate.*test scenario",
    r"模拟\s*\d+\s*个真实.*对话场景",
    r"模拟.*测试场景",
    r"生成结构化.*功能测试结果",
    r"输出.*测试报告",
    r"按.*安全规则.*回答",
    r"严格遵守.*安全护栏",
    r"按.*决策树.*回答",
    r"不要省略",
    r"reviewer json schema",
    r"output_schema",
]
FUNCTIONAL_SCENARIO_SCHEMA = {
    "scenario": "repeat --scenario for at least two realistic dialogue cases",
    "execution_method": "required top-level field: subagent_dialogue|isolated_test_agent",
    "static_analysis_only": "must be false; static analysis alone cannot pass",
    "fields": {
        "id": "stable short id, e.g. T1",
        "agent_task_id": "optional generated target task id used for launch tracking",
        "title": "short scenario title",
        "request": "natural end-user request that triggers the skill; do not include reviewer JSON/test instructions",
        "target_agent_prompt": "exact prompt sent to the target subagent; must be a neutral Skill load instruction plus raw user request only",
        "turns": "pipe-separated observed dialogue, e.g. user: ...|assistant: ...|user: follow-up|assistant: ...",
        "intent_recognized": "yes|partial|no",
        "skill_invoked": "yes|partial|no|not_observable",
        "artifacts": "optional pipe-separated observed files/URLs/widgets/tool outputs",
        "output_quality": "pass|warn|blocked",
        "result": "pass|warn|blocked|needs_config",
        "evidence": "what was actually exercised or observed",
    },
    "example": "id=T1;title=happy path;request=...;turns=user: ...|assistant: ...;intent_recognized=yes;skill_invoked=yes;output_quality=pass;result=pass;evidence=...",
}


def expected_verdict_schema(kind: str) -> dict:
    """Return the operator-facing schema consumed by submit/validate commands."""
    if kind == "risk":
        return {
            "kind": "risk",
            "target_file": SEMANTIC_REVIEW_FILENAME,
            "required_top_level_fields": {
                "status": "pass|blocked",
                "reviewed_by": sorted(SEMANTIC_REVIEWERS),
                "review_method": sorted(SEMANTIC_REVIEW_METHODS),
                "source_files_reviewed": "list[str], must include SKILL.md",
                "risk_categories_checked": sorted(SEMANTIC_REQUIRED_RISK_AREAS),
                "capability_inventory": "list[str], each item >= 16 chars",
                "reachability_analysis": "list[str], each item >= 24 chars",
                "findings": "list[finding]",
                "summary": "concrete conclusion; pass summary >= 30 chars",
            },
            "finding_fields": {
                "category": sorted(SEMANTIC_CATEGORIES),
                "severity": sorted(SEMANTIC_SEVERITIES),
                "decision": sorted(SEMANTIC_DECISIONS),
                "reachability": sorted(SEMANTIC_REACHABILITY),
                "evidence": "list[{file: str, line?: int|str, text: str}], required for warning/blocker",
                "rationale": "required for warning/blocker",
            },
            "notes": [
                "Use category=config_guidance for configuration guidance findings; do not use configuration as findings[].category.",
                "risk_categories_checked must include configuration as a checked area.",
            ],
        }
    if kind == "functional":
        return {
            "kind": "functional",
            "target_file": FUNCTIONAL_DIALOGUE_RESULT_FILENAME,
            "required_top_level_fields": {
                "status": "pass|blocked|needs_config",
                "reviewed_by": "subagent",
                "execution_method": sorted(FUNCTIONAL_EXECUTION_METHODS),
                "static_analysis_only": False,
                "scenarios": "list[scenario], at least two typical dialogue scenarios",
                "summary": "recommended concrete summary",
            },
            "scenario_schema": FUNCTIONAL_SCENARIO_SCHEMA,
            "scenario_fields": {
                "user_request": "natural user request only; no reviewer/test schema instructions",
                "target_agent_prompt": "required for pass/warn/blocked; exact prompt sent to target subagent, must not contain reviewer scaffolding",
                "dialogue_turns": "list[str] with both user and assistant/subagent turns",
                "intent_recognized": sorted(FUNCTIONAL_INTENT_RESULTS),
                "skill_invoked": sorted(FUNCTIONAL_SKILL_INVOCATION_RESULTS),
                "artifacts_observed": "list[str]",
                "output_quality": sorted(FUNCTIONAL_OUTPUT_QUALITY_RESULTS),
                "result": "pass|warn|blocked|needs_config",
                "evidence": "required for pass/warn/blocked",
            },
        }
    if kind == "deep":
        return {
            "kind": "deep",
            "target_file": DEEP_REVIEW_FILENAME,
            "required_top_level_fields": {
                "status": "pass|blocked",
                "reviewed_by": sorted(DEEP_REVIEWERS),
                "review_method": sorted(DEEP_REVIEW_METHODS),
                "source_files_reviewed": "list[str], must include SKILL.md",
                "cross_dimension_checks": "list[str], pass requires at least two items",
                "dimensions": f"list[dimension], pass requires all {len(QUALITY_DIMENSION_IDS)} standard dimensions",
                "summary": "recommended concrete summary",
            },
            "dimension_fields": {
                "id": sorted(QUALITY_DIMENSION_IDS),
                "rating": sorted(QUALITY_RATINGS),
                "score": "int 1-10; excellent=9-10, good=7-8, needs_work=4-6, blocked=1-3",
                "evidence": "list[str], pass requires at least two concrete observations per dimension",
                "rationale": "required for pass",
                "recommendation": "required for needs_work/blocked; recommended otherwise",
            },
        }
    raise ValueError(f"unknown verdict kind: {kind}")


def _parse_semicolon_kv(raw: str) -> dict:
    """Parse key=value;key=value blobs so agents do not have to hand-write JSON."""
    data = {}
    for part in (raw or "").split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            data.setdefault("_errors", []).append(f"missing '=' in segment: {part}")
            continue
        key, value = part.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def _coerce_line(value: str):
    value = str(value or "").strip()
    if not value:
        return ""
    return int(value) if value.isdigit() else value


def _finding_from_kv(data: dict) -> dict:
    evidence = []
    file_value = data.get("file") or data.get("evidence_file") or ""
    text_value = data.get("text") or data.get("evidence_text") or ""
    line_value = data.get("line") or data.get("evidence_line") or ""
    if file_value or text_value or line_value:
        ev = {"file": file_value or "unknown", "text": text_value}
        if line_value:
            ev["line"] = _coerce_line(line_value)
        evidence.append(ev)
    category = str(data.get("category") or "other").strip().lower()
    finding = {
        "category": SEMANTIC_CATEGORY_ALIASES.get(category, category),
        "severity": data.get("severity") or ("high" if data.get("decision") == "blocker" else "low"),
        "decision": data.get("decision") or "warning",
        "evidence": evidence,
        "rationale": data.get("rationale") or data.get("reason") or "",
    }
    return finding


def _dimension_from_kv(data: dict) -> dict:
    evidence = data.get("evidence") or ""
    evidence_items = [x.strip() for x in re.split(r"\s*\|\s*", evidence) if x.strip()]
    return {
        "id": data.get("id") or data.get("dimension") or "",
        "rating": data.get("rating") or "good",
        "score": data.get("score") or "",
        "evidence": evidence_items,
        "recommendation": data.get("recommendation") or "",
        "rationale": data.get("rationale") or data.get("finding") or "",
    }


def _scenario_from_kv(data: dict) -> dict:
    turns = data.get("turns") or data.get("dialogue") or ""
    if isinstance(turns, str):
        turn_items = [x.strip() for x in re.split(r"\s*\|\s*", turns) if x.strip()]
    else:
        turn_items = []
    artifacts = data.get("artifacts") or data.get("artifacts_observed") or ""
    if isinstance(artifacts, str):
        artifact_items = [x.strip() for x in re.split(r"\s*\|\s*", artifacts) if x.strip()]
    elif isinstance(artifacts, list):
        artifact_items = artifacts
    else:
        artifact_items = []
    return {
        "id": data.get("id") or "",
        "agent_task_id": data.get("agent_task_id") or data.get("task_id") or data.get("agent_task") or "",
        "title": data.get("title") or data.get("description") or "",
        "user_request": data.get("request") or data.get("user_request") or "",
        "target_agent_prompt": data.get("target_agent_prompt") or data.get("prompt") or "",
        "dialogue_turns": turn_items,
        "intent_recognized": data.get("intent_recognized") or data.get("intent") or "",
        "skill_invoked": data.get("skill_invoked") or data.get("invoked") or "",
        "artifacts_observed": artifact_items,
        "output_quality": data.get("output_quality") or data.get("quality") or "",
        "result": data.get("result") or "pass",
        "evidence": data.get("evidence") or "",
        "notes": data.get("notes") or data.get("summary") or "",
    }


def _normalize_semantic_verdict(verdict: dict) -> dict:
    verdict = dict(verdict or {})
    verdict["status"] = verdict.get("status") or "pass"
    verdict["reviewed_by"] = verdict.get("reviewed_by") or ""
    verdict["review_method"] = verdict.get("review_method") or ""
    verdict["source_files_reviewed"] = verdict.get("source_files_reviewed") if isinstance(verdict.get("source_files_reviewed"), list) else []
    verdict["risk_categories_checked"] = verdict.get("risk_categories_checked") if isinstance(verdict.get("risk_categories_checked"), list) else []
    verdict["capability_inventory"] = verdict.get("capability_inventory") if isinstance(verdict.get("capability_inventory"), list) else []
    verdict["reachability_analysis"] = verdict.get("reachability_analysis") if isinstance(verdict.get("reachability_analysis"), list) else []
    verdict["findings"] = verdict.get("findings") if isinstance(verdict.get("findings"), list) else []
    for finding in verdict["findings"]:
        if not isinstance(finding, dict):
            continue
        category = str(finding.get("category") or "").strip().lower()
        if category in SEMANTIC_CATEGORY_ALIASES:
            finding["category"] = SEMANTIC_CATEGORY_ALIASES[category]
            finding.setdefault("normalization_notes", []).append(f"category alias {category} normalized to {finding['category']}")
        if finding.get("decision") == "blocker":
            verdict["status"] = "blocked"
            break
    verdict.setdefault("summary", "")
    verdict.setdefault("generated_at", now_iso())
    return verdict


def _normalize_functional_verdict(verdict: dict) -> dict:
    verdict = dict(verdict or {})
    verdict["status"] = verdict.get("status") or verdict.get("recommendation") or "pass"
    if verdict["status"] == "proceed":
        verdict["status"] = "pass"
    if verdict["status"] == "failed":
        verdict["status"] = "blocked"
    verdict["reviewed_by"] = verdict.get("reviewed_by") or "subagent"
    if "static_analysis_only" in verdict:
        verdict["static_analysis_only"] = str(verdict.get("static_analysis_only")).strip().lower() in {"1", "true", "yes"}
    scenarios = verdict.get("scenarios")
    verdict["scenarios"] = scenarios if isinstance(scenarios, list) else []
    for scenario in verdict["scenarios"]:
        if isinstance(scenario, dict) and scenario.get("result") in {"fail", "failed", "blocked"}:
            verdict["status"] = "blocked"
            break
    verdict.setdefault("summary", "")
    verdict.setdefault("generated_at", now_iso())
    return verdict


def _contains_static_analysis_disclaimer(*values: object) -> bool:
    text = "\n".join(str(value or "") for value in values)
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in FUNCTIONAL_STATIC_ANALYSIS_PATTERNS)


def _contains_harness_prompt_leak(*values: object) -> bool:
    text = "\n".join(str(value or "") for value in values)
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in FUNCTIONAL_HARNESS_PROMPT_PATTERNS)


def _contains_trace_walkthrough(*values: object) -> bool:
    text = "\n".join(str(value or "") for value in values)
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in FUNCTIONAL_TRACE_WALKTHROUGH_PATTERNS)


def validate_functional_verdict(verdict: dict) -> tuple[list[str], list[str]]:
    errors = []
    warnings = []
    status = verdict.get("status")
    if status not in {"pass", "blocked", "needs_config"}:
        errors.append("status must be pass, blocked, or needs_config")
    if verdict.get("reviewed_by") != "subagent":
        errors.append("reviewed_by must be subagent")
    if status in {"pass", "blocked"}:
        if verdict.get("execution_method") not in FUNCTIONAL_EXECUTION_METHODS:
            errors.append("execution_method must be subagent_dialogue or isolated_test_agent for executed functional validation")
        if verdict.get("static_analysis_only") is not False:
            errors.append("static_analysis_only must be false for executed functional validation")
        method_text = (verdict.get("summary"), verdict.get("notes"), verdict.get("reason"))
        if status == "pass" and _contains_static_analysis_disclaimer(*method_text):
            errors.append("functional validation cannot pass from static analysis or a non-subagent review; rerun with a subagent or isolated test agent")
        if status == "pass" and _contains_trace_walkthrough(*method_text):
            errors.append("functional validation cannot pass from a SKILL.md workflow walkthrough; rerun real user-to-target-skill dialogue")
    scenarios = verdict.get("scenarios")
    if not isinstance(scenarios, list):
        errors.append("scenarios must be a list")
        return errors, warnings
    if len(scenarios) < 2:
        errors.append("functional validation must include at least two typical dialogue scenarios")
    has_blocked = False
    for idx, scenario in enumerate(scenarios, 1):
        if not isinstance(scenario, dict):
            errors.append(f"scenarios[{idx}] must be an object")
            continue
        result = scenario.get("result")
        if result not in {"pass", "warn", "blocked", "needs_config"}:
            errors.append(f"scenarios[{idx}].result must be pass, warn, blocked, or needs_config")
        if result == "blocked":
            has_blocked = True
        user_request = str(scenario.get("user_request") or "").strip()
        if not user_request:
            errors.append(f"scenarios[{idx}].user_request is required")
        elif _contains_harness_prompt_leak(user_request):
            errors.append(f"scenarios[{idx}].user_request contains reviewer/test-harness instructions; send only a natural end-user request to the target skill")
        target_prompt = str(scenario.get("target_agent_prompt") or "").strip()
        if result in {"pass", "warn", "blocked"}:
            if not target_prompt:
                errors.append(f"scenarios[{idx}].target_agent_prompt is required and must record the exact prompt sent to the target subagent")
            elif _contains_harness_prompt_leak(target_prompt):
                errors.append(f"scenarios[{idx}].target_agent_prompt contains reviewer scaffolding; target prompt must be production-like")
            elif not target_prompt.startswith("加载 ") or "用户:" not in target_prompt:
                errors.append(f"scenarios[{idx}].target_agent_prompt must use the production-like template: 加载 <SKILL.md path> 并作为该 Skill 回答用户问题。\\n\\n用户: <raw user_request>")
            elif user_request and user_request not in target_prompt:
                errors.append(f"scenarios[{idx}].target_agent_prompt must include the raw user_request exactly")
        turns = scenario.get("dialogue_turns")
        if not isinstance(turns, list) or not turns:
            errors.append(f"scenarios[{idx}].dialogue_turns must contain the observed user/subagent dialogue")
        elif result in {"pass", "warn", "blocked"}:
            joined_turns = "\n".join(str(turn or "") for turn in turns)
            has_user = re.search(r"\buser\s*:", joined_turns, re.IGNORECASE)
            has_agent = re.search(r"\b(assistant|subagent|agent)\s*:", joined_turns, re.IGNORECASE)
            if not has_user or not has_agent:
                errors.append(f"scenarios[{idx}].dialogue_turns must include both user and assistant/subagent turns")
            if _contains_harness_prompt_leak(joined_turns):
                errors.append(f"scenarios[{idx}].dialogue_turns include reviewer/test-harness instructions instead of natural target-skill interaction")
        if result in {"pass", "warn", "blocked"}:
            intent = scenario.get("intent_recognized")
            invoked = scenario.get("skill_invoked")
            quality = scenario.get("output_quality")
            if intent not in FUNCTIONAL_INTENT_RESULTS:
                errors.append(f"scenarios[{idx}].intent_recognized must be yes, partial, or no")
            if invoked not in FUNCTIONAL_SKILL_INVOCATION_RESULTS:
                errors.append(f"scenarios[{idx}].skill_invoked must be yes, partial, no, or not_observable")
            if quality not in FUNCTIONAL_OUTPUT_QUALITY_RESULTS:
                errors.append(f"scenarios[{idx}].output_quality must be pass, warn, or blocked")
            if result == "pass" and intent != "yes":
                errors.append(f"scenarios[{idx}] cannot pass unless intent_recognized is yes")
            if result == "pass" and invoked not in {"yes", "not_observable"}:
                errors.append(f"scenarios[{idx}] cannot pass unless skill_invoked is yes or not_observable")
            if result == "pass" and quality != "pass":
                errors.append(f"scenarios[{idx}] cannot pass unless output_quality is pass")
        if not isinstance(scenario.get("artifacts_observed", []), list):
            errors.append(f"scenarios[{idx}].artifacts_observed must be a list when provided")
        if not str(scenario.get("evidence") or "").strip() and result in {"pass", "warn", "blocked"}:
            errors.append(f"scenarios[{idx}].evidence is required")
        observation_values = [scenario.get("evidence"), scenario.get("notes"), *(turns if isinstance(turns, list) else [])]
        if result in {"pass", "warn"} and _contains_static_analysis_disclaimer(*observation_values):
            errors.append(f"scenarios[{idx}] appears to be based on static analysis or missing subagent execution")
        if result in {"pass", "warn"} and _contains_trace_walkthrough(*observation_values):
            errors.append(f"scenarios[{idx}] appears to be a SKILL.md workflow walkthrough instead of real target-skill dialogue")
    if has_blocked and status != "blocked":
        errors.append("status must be blocked when any scenario result is blocked")
    if status == "pass" and not str(verdict.get("summary") or "").strip():
        warnings.append("summary is recommended for pass verdicts")
    return errors, warnings


def validate_semantic_verdict(verdict: dict) -> tuple[list[str], list[str]]:
    errors = []
    warnings = []
    status = verdict.get("status")
    if status not in {"pass", "blocked"}:
        errors.append("status must be pass or blocked")
    if verdict.get("reviewed_by") not in SEMANTIC_REVIEWERS:
        errors.append(f"reviewed_by must be one of {sorted(SEMANTIC_REVIEWERS)}")
    if verdict.get("review_method") not in SEMANTIC_REVIEW_METHODS:
        errors.append(f"review_method must be one of {sorted(SEMANTIC_REVIEW_METHODS)}")
    source_files = verdict.get("source_files_reviewed")
    if not isinstance(source_files, list) or not source_files:
        errors.append("source_files_reviewed must list files read by the security subagent")
    elif not any("SKILL.md" in str(item) for item in source_files):
        errors.append("source_files_reviewed must include SKILL.md")
    checked = {
        str(item).strip().lower()
        for item in verdict.get("risk_categories_checked", []) or []
        if str(item).strip()
    }
    missing = sorted(SEMANTIC_REQUIRED_RISK_AREAS - checked)
    if missing:
        errors.append(f"risk_categories_checked is missing required areas: {missing}")
    inventory = verdict.get("capability_inventory")
    if not isinstance(inventory, list) or not inventory:
        errors.append("capability_inventory must summarize actual capabilities found or explicitly ruled out")
    elif not all(len(str(item).strip()) >= 16 for item in inventory):
        errors.append("capability_inventory entries must be concrete, not one-word labels")
    reachability = verdict.get("reachability_analysis")
    if not isinstance(reachability, list) or not reachability:
        errors.append("reachability_analysis must describe production vs documentation/example reachability")
    elif not all(len(str(item).strip()) >= 24 for item in reachability):
        errors.append("reachability_analysis entries must be concrete enough for main-agent review")
    if not isinstance(verdict.get("findings"), list):
        errors.append("findings must be a list")
        return errors, warnings
    has_blocker = False
    for idx, finding in enumerate(verdict.get("findings") or [], 1):
        if not isinstance(finding, dict):
            errors.append(f"findings[{idx}] must be an object")
            continue
        if finding.get("category") not in SEMANTIC_CATEGORIES:
            errors.append(f"findings[{idx}].category must be one of {sorted(SEMANTIC_CATEGORIES)}")
        if finding.get("severity") not in SEMANTIC_SEVERITIES:
            errors.append(f"findings[{idx}].severity must be one of {sorted(SEMANTIC_SEVERITIES)}")
        decision = finding.get("decision")
        if decision not in SEMANTIC_DECISIONS:
            errors.append(f"findings[{idx}].decision must be one of {sorted(SEMANTIC_DECISIONS)}")
        if decision == "blocker":
            has_blocker = True
        evidence = finding.get("evidence")
        if evidence is None:
            finding["evidence"] = []
        elif not isinstance(evidence, list):
            errors.append(f"findings[{idx}].evidence must be a list")
        if decision in {"warning", "blocker"}:
            if not str(finding.get("rationale") or "").strip():
                errors.append(f"findings[{idx}].rationale is required for warning/blocker decisions")
            if finding.get("reachability") not in SEMANTIC_REACHABILITY:
                errors.append(f"findings[{idx}].reachability must be one of {sorted(SEMANTIC_REACHABILITY)}")
            if not evidence:
                errors.append(f"findings[{idx}].evidence is required for warning/blocker decisions")
            elif isinstance(evidence, list):
                for ev_idx, ev in enumerate(evidence, 1):
                    if not isinstance(ev, dict):
                        errors.append(f"findings[{idx}].evidence[{ev_idx}] must be an object")
                        continue
                    if not str(ev.get("file") or "").strip():
                        errors.append(f"findings[{idx}].evidence[{ev_idx}].file is required")
                    if not str(ev.get("text") or "").strip():
                        errors.append(f"findings[{idx}].evidence[{ev_idx}].text is required")
    if has_blocker and status != "blocked":
        errors.append("status must be blocked when any finding decision is blocker")
    if status == "blocked" and not has_blocker:
        warnings.append("status is blocked but no blocker finding is present")
    summary = str(verdict.get("summary") or "").strip()
    if status == "pass" and len(summary) < 30:
        errors.append("pass verdict summary must be a concrete security conclusion, not a short generic phrase")
    for pattern in SEMANTIC_SHALLOW_PATTERNS:
        if re.search(pattern, summary, re.IGNORECASE):
            errors.append("summary appears shallow; provide strict semantic security reasoning")
            break
    return errors, warnings


def _normalize_deep_verdict(verdict: dict) -> dict:
    verdict = dict(verdict or {})
    verdict["status"] = verdict.get("status") or "pass"
    verdict["reviewed_by"] = verdict.get("reviewed_by") or ""
    source_files = verdict.get("source_files_reviewed")
    verdict["source_files_reviewed"] = source_files if isinstance(source_files, list) else []
    cross_checks = verdict.get("cross_dimension_checks")
    verdict["cross_dimension_checks"] = cross_checks if isinstance(cross_checks, list) else []
    verdict["dimensions"] = verdict.get("dimensions") if isinstance(verdict.get("dimensions"), list) else []
    for dim in verdict["dimensions"]:
        if not isinstance(dim, dict):
            continue
        if str(dim.get("score") or "").strip().isdigit():
            dim["score"] = int(str(dim.get("score")).strip())
        if dim.get("rating") == "blocked":
            verdict["status"] = "blocked"
    verdict.setdefault("summary", "")
    verdict.setdefault("generated_at", now_iso())
    return verdict


def _is_concrete_deep_evidence(value: object) -> bool:
    text = str(value or "").strip()
    return len(text) >= 24


def validate_deep_verdict(verdict: dict) -> tuple[list[str], list[str]]:
    errors = []
    warnings = []
    status = verdict.get("status")
    if status not in {"pass", "blocked"}:
        errors.append("status must be pass or blocked")
    if verdict.get("reviewed_by") not in DEEP_REVIEWERS:
        errors.append(f"reviewed_by must be one of {sorted(DEEP_REVIEWERS)}")
    if verdict.get("review_method") not in DEEP_REVIEW_METHODS:
        errors.append(f"review_method must be one of {sorted(DEEP_REVIEW_METHODS)}")
    source_files = verdict.get("source_files_reviewed")
    if not isinstance(source_files, list) or not source_files:
        errors.append("source_files_reviewed must list the files/sections read for deep review")
    elif not any("SKILL.md" in str(item) for item in source_files):
        errors.append("source_files_reviewed must include SKILL.md")
    cross_checks = verdict.get("cross_dimension_checks")
    if status == "pass" and (not isinstance(cross_checks, list) or len([x for x in cross_checks if str(x).strip()]) < 2):
        errors.append("pass verdict must include at least two cross_dimension_checks")
    dimensions = verdict.get("dimensions")
    if not isinstance(dimensions, list):
        errors.append("dimensions must be a list")
        return errors, warnings
    seen = set()
    has_blocked_dimension = False
    for idx, dim in enumerate(dimensions, 1):
        if not isinstance(dim, dict):
            errors.append(f"dimensions[{idx}] must be an object")
            continue
        dim_id = str(dim.get("id") or "").strip()
        dim_key = re.sub(r"[^a-z0-9]+", "_", dim_id.lower()).strip("_")
        if not dim_id:
            errors.append(f"dimensions[{idx}].id is required")
        elif dim_key in seen:
            errors.append(f"duplicate dimension id: {dim_id}")
        else:
            seen.add(dim_key)
            if dim_key not in QUALITY_DIMENSION_IDS:
                warnings.append(f"dimensions[{idx}].id is non-standard but accepted: {dim_id}")
        rating = dim.get("rating")
        if rating not in QUALITY_RATINGS:
            errors.append(f"dimensions[{idx}].rating must be one of {sorted(QUALITY_RATINGS)}")
        if rating == "blocked":
            has_blocked_dimension = True
        score = dim.get("score")
        if not isinstance(score, int) or score < 1 or score > 10:
            errors.append(f"dimensions[{idx}].score must be an integer from 1 to 10")
        elif rating == "excellent" and score < 9:
            errors.append(f"dimensions[{idx}].score must be 9-10 for rating=excellent")
        elif rating == "good" and not (7 <= score <= 8):
            errors.append(f"dimensions[{idx}].score must be 7-8 for rating=good")
        elif rating == "needs_work" and not (4 <= score <= 6):
            errors.append(f"dimensions[{idx}].score must be 4-6 for rating=needs_work")
        elif rating == "blocked" and score > 3:
            errors.append(f"dimensions[{idx}].score must be 1-3 for rating=blocked")
        evidence = dim.get("evidence")
        if evidence is None:
            dim["evidence"] = []
        elif not isinstance(evidence, list):
            errors.append(f"dimensions[{idx}].evidence must be a list")
        elif status == "pass":
            concrete = [item for item in evidence if _is_concrete_deep_evidence(item)]
            if len(concrete) < 2:
                errors.append(f"dimensions[{idx}].evidence must include at least two concrete observations with file/section/metric references")
        if status == "pass" and not str(dim.get("rationale") or "").strip():
            errors.append(f"dimensions[{idx}].rationale is required")
        if rating in {"needs_work", "blocked"} and not str(dim.get("recommendation") or "").strip():
            errors.append(f"dimensions[{idx}].recommendation is required for needs_work/blocked ratings")
        if status == "pass" and rating in {"excellent", "good"} and not str(dim.get("recommendation") or "").strip():
            warnings.append(f"dimensions[{idx}].recommendation is recommended even for passing ratings")
    if status == "blocked" and not has_blocked_dimension:
        warnings.append("status is blocked but no dimension has rating=blocked")
    if status == "pass":
        if len(seen) < len(QUALITY_DIMENSION_IDS):
            errors.append(f"pass verdict must include at least {len(QUALITY_DIMENSION_IDS)} quality dimensions; got {len(seen)}")
        missing = sorted(QUALITY_DIMENSION_IDS - seen)
        if missing:
            warnings.append(f"standard quality dimension ids not fully covered: {missing}")
    if status == "pass" and not str(verdict.get("summary") or "").strip():
        warnings.append("summary is recommended for pass verdicts")
    return errors, warnings


def _resolve_verdict_path(args, filename: str) -> Path:
    if getattr(args, "verdict_file", ""):
        return Path(args.verdict_file)
    if not getattr(args, "review_output_dir", ""):
        raise ValueError("--review-output-dir or --verdict-file is required")
    return Path(args.review_output_dir) / filename


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8-sig")


def _stage_status_from_checks(checks: list[dict]) -> tuple[int, int, str]:
    blockers = [c for c in checks if isinstance(c, dict) and not c.get("pass", True)]
    warnings = [c for c in checks if isinstance(c, dict) and c.get("warning")]
    return len(blockers), len(warnings), "passed" if not blockers else "blocked"


def _try_auto_recompute_final(verdict_path: Path, kind: str, verdict: dict) -> dict:
    """Update the sibling stage JSON and 05-final.json after a submit-* command."""
    output_dir = verdict_path.parent
    structure_path = output_dir / "01-structure.json"
    risk_path = output_dir / "02-risk.json"
    functional_path = output_dir / "03-functional-test.json"
    deep_path = output_dir / "04-deep-review.json"
    final_path = output_dir / "05-final.json"
    structure_stage = _load_json_if_exists(structure_path)
    risk_stage = _load_json_if_exists(risk_path)
    functional_stage = _load_json_if_exists(functional_path)
    deep_stage = _load_json_if_exists(deep_path)
    if not all(isinstance(stage, dict) and stage for stage in [structure_stage, risk_stage, functional_stage, deep_stage]):
        return {"status": "skipped", "reason": "stage_json_incomplete", "expected_dir": str(output_dir)}

    if kind == "risk":
        risk_checks = risk_stage.get("checks") or []
        semantic_blocked = verdict.get("status") == "blocked" or any(
            isinstance(f, dict) and f.get("decision") == "blocker" for f in verdict.get("findings", [])
        )
        script_blocked = any(isinstance(c, dict) and not c.get("pass", True) for c in risk_checks)
        risk_stage.update({
            "status": "blocked" if script_blocked or semantic_blocked else "passed",
            "semantic_review": verdict,
            "semantic_review_quality_gate": {"status": "valid", "errors": [], "warnings": []},
            "semantic_review_request": None,
            "generated_at": now_iso(),
        })
        _write_json(risk_path, risk_stage)
    elif kind == "functional":
        status = verdict.get("status")
        functional_stage.update({
            "status": status,
            "recommendation": status,
            "overall": status,
            "test_executed": status in {"pass", "blocked"},
            "scenario_count": len(verdict.get("scenarios") or []),
            "scenarios": verdict.get("scenarios") or [],
            "result": verdict,
            "summary": verdict.get("summary", ""),
            "generated_at": now_iso(),
        })
        if status != "needs_config":
            functional_stage["needs_config_instructions"] = []
        _write_json(functional_path, functional_stage)
    elif kind == "deep":
        deep_stage.update({
            "status": "blocked" if verdict.get("status") == "blocked" else "passed",
            "result": verdict,
            "deep_review_request": None,
            "generated_at": now_iso(),
        })
        _write_json(deep_path, deep_stage)

    checks = []
    checks.extend(structure_stage.get("checks") or [])
    checks.extend(risk_stage.get("checks") or [])
    blocker_count, warning_count, review_status = _stage_status_from_checks(checks)
    previous_final = _load_json_if_exists(final_path)
    review_result = {
        "skill_name": structure_stage.get("skill_name") or risk_stage.get("skill_name") or functional_stage.get("skill_name") or deep_stage.get("skill_name") or "",
        "frontmatter": structure_stage.get("frontmatter", {}),
        "checks": checks,
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "status": review_status,
        "ai_actions": previous_final.get("ai_actions", []) if isinstance(previous_final, dict) else [],
        "mode": previous_final.get("mode", "workflow") if isinstance(previous_final, dict) else "workflow",
        "deep_review_context": previous_final.get("deep_review_context", {"is_new_listing": True}) if isinstance(previous_final, dict) else {"is_new_listing": True},
    }
    final_stage = build_final_stage(review_result, structure_stage, risk_stage, functional_stage, deep_stage)
    _write_json(final_path, final_stage)
    return {"status": "updated", "path": str(final_path), "final_status": final_stage.get("status")}


def _write_validated_verdict(path: Path, verdict: dict, kind: str) -> dict:
    if kind == "risk":
        verdict = _normalize_semantic_verdict(verdict)
        errors, warnings = validate_semantic_verdict(verdict)
    elif kind == "functional":
        verdict = _normalize_functional_verdict(verdict)
        errors, warnings = validate_functional_verdict(verdict)
    else:
        verdict = _normalize_deep_verdict(verdict)
        errors, warnings = validate_deep_verdict(verdict)
    if errors:
        return {
            "status": "invalid",
            "kind": kind,
            "errors": errors,
            "warnings": warnings,
            "target_path": str(path),
            "expected_schema": expected_verdict_schema(kind),
            "next_steps": [f"run review.py schema --kind {kind} before regenerating the verdict"],
        }
    _write_json(path, verdict)
    auto_final = _try_auto_recompute_final(path, kind, verdict)
    next_steps = [] if auto_final.get("status") == "updated" else ["rerun review.py with --stage final or --stage all so 05-final.json consumes this verdict"]
    return {
        "status": "written",
        "kind": kind,
        "path": str(path),
        "verdict_status": verdict.get("status"),
        "warnings": warnings,
        "auto_final": auto_final,
        "next_steps": next_steps,
    }


def _write_verdict_from_file(args, filename: str, kind: str) -> dict:
    source_path = Path(args.from_file)
    verdict = _load_json_if_exists(source_path)
    if not verdict:
        return {"status": "invalid", "kind": kind, "errors": [f"from-file not found or empty: {source_path}"]}
    if verdict.get("status") == "invalid" and "error" in verdict:
        return {"status": "invalid", "kind": kind, "errors": [verdict["error"]], "source_path": str(source_path)}
    path = _resolve_verdict_path(args, filename)
    data = _write_validated_verdict(path, verdict, kind)
    data["source_path"] = str(source_path)
    return data


def run_review_aux_command(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Reviewer JSON helper commands")
    sub = parser.add_subparsers(dest="command", required=True)

    p_risk = sub.add_parser("submit-risk", help="Create validated 02-risk-semantic-review.json")
    p_risk.add_argument("--review-output-dir", default="", help="Stage output directory containing 02-risk.json")
    p_risk.add_argument("--verdict-file", default="", help="Explicit verdict file path")
    p_risk.add_argument("--from-file", default="", help="Read a complete verdict JSON and validate/write it")
    p_risk.add_argument("--status", choices=["pass", "blocked"], default="")
    p_risk.add_argument("--summary", default="")
    p_risk.add_argument("--reviewed-by", choices=sorted(SEMANTIC_REVIEWERS), default="security_subagent")
    p_risk.add_argument("--review-method", choices=sorted(SEMANTIC_REVIEW_METHODS), default="")
    p_risk.add_argument("--source-file", action="append", default=[], help="Repeatable file/section read by the security subagent; must include SKILL.md")
    p_risk.add_argument("--risk-area", action="append", default=[], help="Repeatable covered risk area: credential, privacy, network, unsafe_execution, prompt_injection, commercial_diversion, legal, configuration")
    p_risk.add_argument("--capability", action="append", default=[], help="Repeatable concrete capability inventory item")
    p_risk.add_argument("--reachability", action="append", default=[], help="Repeatable production/documentation reachability judgment")
    p_risk.add_argument("--finding", action="append", default=[], help="Repeatable key=value;... finding (no JSON needed)")
    p_risk.add_argument("--output-file", help="Command result JSON path")
    p_risk.add_argument("--output-mode", choices=["quiet", "summary", "verbose"], default="")

    p_deep = sub.add_parser("submit-deep", help="Create validated 04-deep-quality-review-result.json")
    p_deep.add_argument("--review-output-dir", default="", help="Stage output directory containing 04-deep-review.json")
    p_deep.add_argument("--verdict-file", default="", help="Explicit verdict file path")
    p_deep.add_argument("--from-file", default="", help="Read a complete verdict JSON and validate/write it")
    p_deep.add_argument("--status", choices=["pass", "blocked"], default="")
    p_deep.add_argument("--summary", default="")
    p_deep.add_argument("--reviewed-by", default="subagent")
    p_deep.add_argument("--review-method", choices=sorted(DEEP_REVIEW_METHODS), default="")
    p_deep.add_argument("--source-file", action="append", default=[], help="Repeatable source file/section read during deep review, must include SKILL.md")
    p_deep.add_argument("--cross-check", action="append", default=[], help="Repeatable cross-dimension consistency check")
    p_deep.add_argument("--dimension", action="append", default=[], help="Repeatable id=...;rating=...;score=1-10;evidence=...|...;rationale=...;recommendation=...")
    p_deep.add_argument("--output-file", help="Command result JSON path")
    p_deep.add_argument("--output-mode", choices=["quiet", "summary", "verbose"], default="")

    p_func = sub.add_parser("submit-functional", help="Create validated 03-functional-dialogue-test-result.json")
    p_func.add_argument("--review-output-dir", default="", help="Stage output directory containing 03-functional-test.json")
    p_func.add_argument("--verdict-file", default="", help="Explicit verdict file path")
    p_func.add_argument("--from-file", default="", help="Read a complete verdict JSON and validate/write it")
    p_func.add_argument("--status", choices=["pass", "blocked", "needs_config"], default="")
    p_func.add_argument("--summary", default="")
    p_func.add_argument("--reviewed-by", default="subagent")
    p_func.add_argument("--execution-method", choices=sorted(FUNCTIONAL_EXECUTION_METHODS), default="")
    p_func.add_argument("--static-analysis-only", choices=["true", "false"], default="false")
    p_func.add_argument("--scenario", action="append", default=[], help="Repeatable id=...;title=...;request=...;turns=...|...;intent_recognized=yes;skill_invoked=yes;artifacts=...|...;output_quality=pass;result=...;evidence=...")
    p_func.add_argument("--output-file", help="Command result JSON path")
    p_func.add_argument("--output-mode", choices=["quiet", "summary", "verbose"], default="")

    p_exempt = sub.add_parser("submit-exemption", help="Record false-positive/waiver decisions consumed by final gate")
    p_exempt.add_argument("--review-output-dir", required=True, help="Stage output directory containing 05-final.json")
    p_exempt.add_argument("--check-id", action="append", required=True, help="Check id to exempt, e.g. B15 or B21; repeatable")
    p_exempt.add_argument("--reason", required=True, help="Why this check is a false positive or accepted waiver")
    p_exempt.add_argument("--decision", choices=["false_positive", "accepted_risk", "waived"], default="false_positive")
    p_exempt.add_argument("--reviewed-by", default="llm")
    p_exempt.add_argument("--output-file", help="Command result JSON path")
    p_exempt.add_argument("--output-mode", choices=["quiet", "summary", "verbose"], default="")

    p_validate = sub.add_parser("validate-verdict", help="Validate an existing verdict JSON file")
    p_validate.add_argument("verdict_file")
    p_validate.add_argument("--kind", choices=["risk", "functional", "deep"], required=True)
    p_validate.add_argument("--output-file", help="Command result JSON path")
    p_validate.add_argument("--output-mode", choices=["quiet", "summary", "verbose"], default="")

    p_schema = sub.add_parser("schema", help="Print the expected verdict schema before generating a verdict")
    p_schema.add_argument("--kind", choices=["risk", "functional", "deep"], required=True)
    p_schema.add_argument("--output-file", help="Command result JSON path")
    p_schema.add_argument("--output-mode", choices=["quiet", "summary", "verbose"], default="")

    args = parser.parse_args(argv)
    try:
        if args.command == "schema":
            data = {"status": "ok", "kind": args.kind, "expected_schema": expected_verdict_schema(args.kind)}
        elif args.command == "submit-risk":
            if args.from_file:
                data = _write_verdict_from_file(args, SEMANTIC_REVIEW_FILENAME, "risk")
            else:
                findings = []
                parse_errors = []
                missing_args = [
                    name for name, value in {
                        "--status": args.status,
                        "--summary": args.summary,
                        "--review-method": args.review_method,
                        "--source-file": args.source_file,
                        "--risk-area": args.risk_area,
                        "--capability": args.capability,
                        "--reachability": args.reachability,
                    }.items() if value in (None, "", [])
                ]
                for raw in args.finding:
                    parsed = _parse_semicolon_kv(raw)
                    parse_errors.extend(parsed.pop("_errors", []))
                    findings.append(_finding_from_kv(parsed))
                if missing_args or parse_errors:
                    data = {"status": "invalid", "kind": "risk", "errors": parse_errors + [f"missing required argument: {name}" for name in missing_args], "expected_schema": expected_verdict_schema("risk")}
                else:
                    path = _resolve_verdict_path(args, SEMANTIC_REVIEW_FILENAME)
                    data = _write_validated_verdict(path, {
                        "status": args.status,
                        "reviewed_by": args.reviewed_by,
                        "review_method": args.review_method,
                        "source_files_reviewed": args.source_file,
                        "risk_categories_checked": args.risk_area,
                        "capability_inventory": args.capability,
                        "reachability_analysis": args.reachability,
                        "findings": findings,
                        "summary": args.summary,
                    }, "risk")
        elif args.command == "submit-deep":
            if args.from_file:
                data = _write_verdict_from_file(args, DEEP_REVIEW_FILENAME, "deep")
            else:
                dimensions = []
                parse_errors = []
                missing_args = [
                    name for name, value in {
                        "--status": args.status,
                        "--summary": args.summary,
                        "--review-method": args.review_method,
                        "--source-file": args.source_file,
                    }.items() if value in (None, "", [])
                ]
                for raw in args.dimension:
                    parsed = _parse_semicolon_kv(raw)
                    parse_errors.extend(parsed.pop("_errors", []))
                    dimensions.append(_dimension_from_kv(parsed))
                if missing_args or parse_errors:
                    data = {"status": "invalid", "kind": "deep", "errors": parse_errors + [f"missing required argument: {name}" for name in missing_args], "expected_schema": expected_verdict_schema("deep")}
                else:
                    path = _resolve_verdict_path(args, DEEP_REVIEW_FILENAME)
                    data = _write_validated_verdict(path, {
                        "status": args.status,
                        "reviewed_by": args.reviewed_by,
                        "review_method": args.review_method,
                        "source_files_reviewed": args.source_file,
                        "cross_dimension_checks": args.cross_check,
                        "dimensions": dimensions,
                        "summary": args.summary,
                    }, "deep")
        elif args.command == "submit-functional":
            if args.from_file:
                data = _write_verdict_from_file(args, FUNCTIONAL_DIALOGUE_RESULT_FILENAME, "functional")
            else:
                scenarios = []
                parse_errors = []
                missing_args = [
                    name for name, value in {
                        "--status": args.status,
                        "--summary": args.summary,
                        "--execution-method": args.execution_method,
                    }.items() if value in (None, "", [])
                ]
                for raw in args.scenario:
                    parsed = _parse_semicolon_kv(raw)
                    parse_errors.extend(parsed.pop("_errors", []))
                    scenarios.append(_scenario_from_kv(parsed))
                if missing_args or parse_errors:
                    data = {"status": "invalid", "kind": "functional", "errors": parse_errors + [f"missing required argument: {name}" for name in missing_args], "expected_schema": expected_verdict_schema("functional")}
                else:
                    path = _resolve_verdict_path(args, FUNCTIONAL_DIALOGUE_RESULT_FILENAME)
                    data = _write_validated_verdict(path, {
                        "status": args.status,
                        "reviewed_by": args.reviewed_by,
                        "execution_method": args.execution_method,
                        "static_analysis_only": args.static_analysis_only == "true",
                        "scenarios": scenarios,
                        "summary": args.summary,
                    }, "functional")
        elif args.command == "submit-exemption":
            path = Path(args.review_output_dir) / REVIEW_EXEMPTIONS_FILENAME
            existing = _load_json_if_exists(path)
            if not isinstance(existing, dict) or existing.get("status") == "invalid":
                existing = {"schema_version": "1.0", "exemptions": []}
            exemptions = existing.get("exemptions")
            if not isinstance(exemptions, list):
                exemptions = []
            now = now_iso()
            added = []
            for check_id in args.check_id:
                item = {
                    "check_id": check_id,
                    "decision": args.decision,
                    "reason": args.reason,
                    "reviewed_by": args.reviewed_by,
                    "created_at": now,
                }
                exemptions.append(item)
                added.append(item)
            existing["exemptions"] = exemptions
            existing["updated_at"] = now
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8-sig")
            data = {
                "status": "written",
                "kind": "exemption",
                "path": str(path),
                "added": added,
                "next_steps": ["rerun review.py with --stage final or --stage all so 05-final.json recomputes the gate"],
            }
        else:
            path = Path(args.verdict_file)
            verdict = _load_json_if_exists(path)
            if not verdict:
                data = {"status": "invalid", "kind": args.kind, "errors": [f"file not found or empty: {path}"]}
            elif verdict.get("status") == "invalid" and "error" in verdict:
                data = {"status": "invalid", "kind": args.kind, "errors": [verdict["error"]], "path": str(path)}
            else:
                if args.kind == "risk":
                    verdict = _normalize_semantic_verdict(verdict)
                    errors, warnings = validate_semantic_verdict(verdict)
                elif args.kind == "functional":
                    verdict = _normalize_functional_verdict(verdict)
                    errors, warnings = validate_functional_verdict(verdict)
                else:
                    verdict = _normalize_deep_verdict(verdict)
                    errors, warnings = validate_deep_verdict(verdict)
                data = {
                    "status": "valid" if not errors else "invalid",
                    "kind": args.kind,
                    "path": str(path),
                    "errors": errors,
                    "warnings": warnings,
                }
                if errors:
                    data["expected_schema"] = expected_verdict_schema(args.kind)
    except ValueError as exc:
        data = {"status": "invalid", "error": str(exc)}

    write_output_file(args.output_file, data, f"{args.command}: {data.get('status')}", output_mode=args.output_mode or None)
    return 0 if data.get("status") in {"written", "valid", "ok"} else 1
