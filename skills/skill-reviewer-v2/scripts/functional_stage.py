"""Functional dialogue validation request/result stage."""

from __future__ import annotations

import py_compile
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from common import _load_json_if_exists, parse_frontmatter
from configuration import _collect_text_review_inventory, detect_configuration_requirements
from metadata import _load_source_metadata
from verdicts import (
    FUNCTIONAL_DIALOGUE_RESULT_FILENAME,
    _normalize_functional_verdict,
    validate_functional_verdict,
)

TESTER_DIRS = [
    Path.home() / ".codex" / "skills" / "skill-tester-v2",
    Path.home() / ".workbuddy" / "skills" / "skill-tester-v2",
]


def _find_tester_script() -> Path | None:
    for tester_dir in TESTER_DIRS:
        script = tester_dir / "scripts" / "test_runner.py"
        if script.exists():
            return script
    return None


def _script_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix in {".js", ".mjs", ".cjs"}:
        return "node"
    if suffix == ".sh":
        return "shell"
    if suffix == ".ps1":
        return "powershell"
    if suffix in {".bat", ".cmd"}:
        return "windows_batch"
    try:
        first_line = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()[0]
    except Exception:
        return ""
    if first_line.startswith("#!"):
        lowered = first_line.lower()
        if "python" in lowered:
            return "python"
        if "node" in lowered:
            return "node"
        if "bash" in lowered or " sh" in lowered:
            return "shell"
    return ""


def _candidate_script_files(skill_dir: Path) -> list[Path]:
    roots = [skill_dir / "scripts"]
    for child in skill_dir.iterdir() if skill_dir.exists() else []:
        if child.is_file() and _script_kind(child):
            roots.append(skill_dir)
            break
    candidates: list[Path] = []
    seen: set[Path] = set()
    ignored_dirs = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build"}
    for root in roots:
        if not root.exists():
            continue
        paths = root.rglob("*") if root.is_dir() else [root]
        for path in paths:
            if not path.is_file():
                continue
            rel_parts = set(path.relative_to(skill_dir).parts)
            if rel_parts & ignored_dirs:
                continue
            if not _script_kind(path):
                continue
            if path not in seen:
                candidates.append(path)
                seen.add(path)
    return sorted(candidates, key=lambda p: str(p.relative_to(skill_dir)).replace("\\", "/"))


def _run_check(command: list[str], timeout: int = 15) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout}s"
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    output = (completed.stdout + "\n" + completed.stderr).strip()
    return completed.returncode == 0, output[:1200]


def validate_script_executability(skill_dir: Path) -> dict:
    """Validate script parse/compile readiness without executing package logic."""
    results = []
    for path in _candidate_script_files(skill_dir):
        rel = str(path.relative_to(skill_dir)).replace("\\", "/")
        kind = _script_kind(path)
        item = {
            "file": rel,
            "kind": kind,
            "status": "passed",
            "check": "parse_or_compile_only",
            "message": "",
        }
        if kind == "python":
            try:
                py_compile.compile(str(path), doraise=True)
                item["message"] = "Python compile check passed."
            except py_compile.PyCompileError as exc:
                item["status"] = "blocked"
                item["message"] = str(exc)[:1200]
        elif kind == "node":
            node = shutil.which("node")
            if not node:
                item["status"] = "warning"
                item["message"] = "Node.js is not available; JavaScript syntax check was not executed."
            else:
                ok, output = _run_check([node, "--check", str(path)])
                item["status"] = "passed" if ok else "blocked"
                item["message"] = output or "Node.js syntax check passed."
        elif kind == "shell":
            bash = shutil.which("bash")
            if not bash:
                item["status"] = "warning"
                item["message"] = "bash is not available; shell syntax check was not executed."
            else:
                ok, output = _run_check([bash, "-n", str(path)])
                item["status"] = "passed" if ok else "blocked"
                item["message"] = output or "Shell syntax check passed."
        elif kind == "powershell":
            shell = shutil.which("pwsh") or shutil.which("powershell")
            if not shell:
                item["status"] = "warning"
                item["message"] = "PowerShell is not available; .ps1 parse check was not executed."
            else:
                parser = (
                    "$tokens=$null;$errors=$null;"
                    "[System.Management.Automation.Language.Parser]::ParseFile($args[0],[ref]$tokens,[ref]$errors) | Out-Null;"
                    "if ($errors.Count -gt 0) { $errors | ForEach-Object { $_.Message }; exit 1 }"
                )
                ok, output = _run_check([shell, "-NoProfile", "-NonInteractive", "-Command", parser, str(path)])
                item["status"] = "passed" if ok else "blocked"
                item["message"] = output or "PowerShell parse check passed."
        elif kind == "windows_batch":
            item["status"] = "warning"
            item["message"] = "Windows batch files cannot be safely syntax-checked without execution; cover this file in dialogue/isolated runtime validation."
        else:
            item["status"] = "warning"
            item["message"] = "No safe syntax checker is configured for this file type."
        results.append(item)

    blockers = [item for item in results if item.get("status") == "blocked"]
    warnings = [item for item in results if item.get("status") == "warning"]
    if blockers:
        status = "blocked"
    elif warnings:
        status = "warning"
    elif results:
        status = "passed"
    else:
        status = "not_applicable"
    return {
        "status": status,
        "checked_count": len(results),
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "results": results,
        "summary": (
            f"{len(results)} script/executable file(s) checked; "
            f"{len(blockers)} blocker(s), {len(warnings)} warning(s)."
            if results else "No script/executable files found for functional preflight."
        ),
    }


def _clean_reference_excerpt(text: str, max_chars: int = 280) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip(" -\t`\"'“”‘’")
    return cleaned[:max_chars]


def _extract_reference_context_candidates(fm: dict, body: str, limit: int = 16) -> list[dict[str, str]]:
    """Collect likely constraints as reference context, never as user requests."""
    candidates: list[dict[str, str]] = []
    active_heading = ""
    reference_pattern = re.compile(
        r"安全|规范|规则|约束|确认|禁止|不可|不要|必须|不得|权限|登录|令牌|token|api key|配置|环境|路径|解释器|命令|脚本|重试|下单|支付|隐私|credential|config|requirement|must|never|forbid|confirm|path|command|script",
        re.IGNORECASE,
    )
    for line in body.splitlines():
        stripped = line.strip()
        heading_match = re.match(r"^#{2,5}\s+(.+)$", stripped)
        if heading_match:
            active_heading = _clean_reference_excerpt(heading_match.group(1), 80)
            continue
        if len(stripped) < 8 or stripped.startswith("|"):
            continue
        if not reference_pattern.search(stripped) and not reference_pattern.search(active_heading):
            continue
        excerpt = _clean_reference_excerpt(stripped)
        if not excerpt:
            continue
        candidates.append({
            "source": active_heading or "SKILL.md body",
            "excerpt": excerpt,
            "usage": "reference_only_do_not_use_as_user_request",
        })
        if len(candidates) >= limit:
            break
    desc_text = "\n".join(str(fm.get(key) or "") for key in ("description", "description_zh", "description_en"))
    if desc_text and reference_pattern.search(desc_text):
        candidates.insert(0, {
            "source": "frontmatter.description",
            "excerpt": _clean_reference_excerpt(desc_text),
            "usage": "reference_only_do_not_use_as_user_request_if_it_is_policy_or_capability_catalog",
        })
    return candidates[:limit]


def _estimate_functional_scenario_count(body: str, fm: dict, script_executability: dict) -> int:
    """Pick a scenario/subagent count from documented capability complexity."""
    text = "\n".join([
        str(fm.get("description") or ""),
        str(fm.get("description_zh") or ""),
        str(fm.get("description_en") or ""),
        body or "",
    ])
    count = 2
    capability_keywords = {
        "generate": r"生成|创建|制作|generate|create|build",
        "analyze": r"分析|诊断|评估|审查|analy[sz]e|diagnose|evaluate|review",
        "query": r"查询|搜索|检索|获取|search|query|fetch|get",
        "download": r"下载|导出|保存|download|export|save",
        "upload": r"上传|发布|同步|upload|publish|sync",
        "report": r"报告|文档|表格|图表|report|document|table|chart",
        "multi_turn": r"澄清|补充|追问|调整|优化|refine|follow[- ]?up|clarif",
    }
    matched = [name for name, pattern in capability_keywords.items() if re.search(pattern, text, re.IGNORECASE)]
    headings = [line for line in body.splitlines() if re.match(r"^#{2,4}\s+", line.strip())]
    trigger_lines = [line for line in body.splitlines() if re.search(r"触发|trigger|when users?|适用于|场景", line, re.IGNORECASE)]
    if len(matched) >= 4:
        count += 1
    if len(headings) >= 6 or len(trigger_lines) >= 3:
        count += 1
    if len(body) > 7000:
        count += 1
    if (script_executability or {}).get("checked_count", 0) >= 3:
        count += 1
    return max(2, min(5, count))


def _build_scenario_generation_context(
    skill_dir: Path,
    skill_name: str,
    fm: dict,
    body: str,
    skill_md_char_count: int,
    planned_scenario_count: int,
) -> dict[str, Any]:
    description = str(fm.get("description") or fm.get("description_zh") or fm.get("description_en") or "").strip()
    return {
        "generation_owner": "main_agent_llm_judgement",
        "skill_name": skill_name or skill_dir.name,
        "skill_md_path": str(skill_dir / "SKILL.md"),
        "skill_md_read_required": True,
        "skill_md_content_inlined": False,
        "skill_md_char_count": skill_md_char_count,
        "frontmatter_description": description,
        "planned_scenario_count": planned_scenario_count,
        "scenario_count_rule": "simple skills use 2 scenarios; complex or multi-capability skills use 3-5 scenarios based on capability diversity, branches, safety rules, external dependencies, and script count",
        "scenario_types_required": [
            {
                "type": "core_function",
                "goal": "Identify a primary user-facing capability and create a natural request that directly triggers it.",
            },
            {
                "type": "complete_flow",
                "goal": "Create a request that can exercise the main multi-step workflow from input to observable output or confirmation.",
            },
            {
                "type": "edge_or_safety",
                "goal": "Convert a documented safety or workflow constraint into an abnormal user request that attempts to violate it, then observe whether the target assistant handles it correctly.",
            },
            {
                "type": "branch_coverage",
                "goal": "Cover an alternate mode, optional path, parameter variation, refinement turn, or decision branch when the SKILL.md documents one.",
            },
        ],
        "reference_context_candidates": _extract_reference_context_candidates(fm, body),
        "hard_rules": [
            "Do not mechanically copy frontmatter.description, safety rules, path rules, API configuration, command examples, or implementation notes into user_request.",
            "Use constraints only as reference_context or validation_focus; turn them into real end-user situations when they need to be tested.",
            "Each user_request must be something a real user could naturally send to the target skill.",
            "Each generated target prompt must be production-like: one neutral loading instruction with the target SKILL.md path, followed by the exact natural user request. Do not add boundary conditions, safety reminders, reviewer schemas, scoring criteria, or answer-quality hints.",
            "Before carrying any subagent-reported issue into the final verdict, verify the claimed SKILL.md text, command, file path, or runtime behavior with direct evidence such as search, file read, or an actual safe test.",
        ],
        "scenario_output_contract": {
            "id": "T1",
            "title": "short scenario title",
            "scenario_type": "core_function|complete_flow|edge_or_safety|branch_coverage",
            "user_request": "natural end-user request to send to the target subagent",
            "validation_focus": "what behavior this scenario is intended to observe",
            "reference_context": ["optional SKILL.md constraints or branches used to design the scenario; never send these as user_request"],
        },
    }


def _safe_agent_name(skill_name: str, scenario_id: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", skill_name or "skill").strip("-").lower() or "skill"
    return f"functional-{stem}-{scenario_id.lower()}"[:48]


def _target_agent_prompt(skill_md_path: Path, scenario: dict) -> str:
    user_request = str(scenario.get("user_request") or "").strip()
    return f"加载 {skill_md_path} 并作为该 Skill 回答用户问题。\n\n用户: {user_request}"


def _build_target_agent_tasks(skill_dir: Path, skill_name: str, scenarios: list[dict]) -> list[dict[str, Any]]:
    skill_md_path = skill_dir / "SKILL.md"
    tasks = []
    for scenario in scenarios:
        scenario_id = str(scenario.get("id") or f"T{len(tasks) + 1}")
        tasks.append({
            "id": scenario_id,
            "subagent_name": _safe_agent_name(skill_name, scenario_id),
            "description": f"Run real user scenario {scenario_id}",
            "prompt": _target_agent_prompt(skill_md_path, scenario),
            "prompt_type": "production_like_skill_load_plus_raw_user_utterance",
            "send_this_prompt_to_target_subagent": True,
            "skill_md_path_reference": str(skill_md_path),
            "do_not_append_reviewer_schema_or_test_instructions": True,
            "source_scenario": scenario,
        })
    return tasks


def _functional_test_request(
    skill_dir: Path,
    skill_name: str,
    review_result: dict,
    planned_scenario_count: int,
    result_file: Path,
    script_executability: dict,
    skill_md_content: str,
    body: str,
) -> dict:
    fm = review_result.get("frontmatter", {}) if isinstance(review_result.get("frontmatter"), dict) else {}
    description = str(fm.get("description") or fm.get("description_zh") or fm.get("description_en") or "").strip()
    scenario_context = _build_scenario_generation_context(
        skill_dir,
        skill_name,
        fm,
        body,
        len(skill_md_content or ""),
        planned_scenario_count,
    )
    return {
        "required": True,
        "runner": "main_agent_generates_scenarios_then_launches_target_skill_subagents",
        "minimum_scenarios": 2,
        "planned_scenarios": planned_scenario_count,
        "planned_subagent_count": planned_scenario_count,
        "scenario_generation_required": True,
        "target_skill": {
            "skill_md_path": str(skill_dir / "SKILL.md"),
            "skill_dir": str(skill_dir),
            "description": description,
        },
        "reviewer_instruction": (
            "The script no longer precomputes user requests from SKILL.md snippets. The main agent "
            "must read scenario_generation_context.skill_md_path when the full SKILL.md is not already "
            "available in context, understand the target skill's user-facing capabilities, generate 2-5 realistic end-user scenarios, then launch one "
            "isolated target subagent per generated scenario. The target subagent message must contain only a neutral load instruction with the target SKILL.md path and the raw realistic user utterance. Do not add boundary conditions, expected behavior, safety reminders, reviewer instructions, "
            "schemas, scoring criteria, or test wording to target subagents. Track each target "
            "subagent until observable output is returned; after all target subagents finish, verify "
            "any reported issue against source text or safe runtime evidence before submitting the "
            "structured functional verdict."
        ),
        "scenario_generation_context": scenario_context,
        "dialogue_execution_protocol": [
            "First generate main_agent_scenarios from the full SKILL.md using LLM judgement; read scenario_generation_context.skill_md_path if the full file is not already in context, and do not use mechanical text extraction.",
            "Each generated user_request must be a realistic message a real end user could send to the target skill.",
            "Use safety rules, path rules, API configuration, command examples, and implementation notes only as reference_context or validation_focus, never as user_request text.",
            "For each generated scenario, create a target prompt with exactly two parts: a neutral load instruction `加载 <SKILL.md path> 并作为该 Skill 回答用户问题。` and `用户: <raw user_request>`; do not append any reviewer context.",
            "Launch one isolated target-skill subagent per scenario so the target receives only the neutral Skill load instruction and a realistic raw end-user utterance.",
            "Do not tell the target subagent it is being tested, do not use phrases such as 'You are functional testing the skill', and do not ask it to simulate a test, trace SKILL.md, output JSON, or follow the reviewer schema.",
            "Main agent tracks each target subagent until completion and records the returned output or artifact evidence.",
            "If the target asks a clarifying question or the skill naturally supports iteration, main agent sends a natural follow-up turn and records the full transcript.",
            "Before including a subagent-reported issue in the verdict, verify the claimed command, instruction, path, or behavior with direct evidence; mark unverified claims as notes, not findings.",
            "Submit blocked if results are workflow walkthroughs, inferred from static reading, unverified subagent claims, or lack observable target output.",
        ],
        "target_agent_prompt_boundary": {
            "allowed": "Only a neutral Skill load instruction with the target SKILL.md path plus the raw natural user utterance; follow-up messages must be natural user replies only.",
            "prompt_template": "加载 {skill_md_path} 并作为该 Skill 回答用户问题。\n\n用户: {user_request}",
            "skill_md_path_visibility": "neutral_target_skill_reference_allowed",
            "forbidden": [
                "Do not send raw SKILL.md policy/config/path/command snippets as user_request.",
                "Do not include the target SKILL.md path with test/reviewer wording; only the neutral load instruction is allowed.",
                "Do not add expected behavior, boundary conditions, answer-quality hints, safety reminders, or decision-tree instructions to the target prompt.",
                "Do not tell the target subagent it is being functionally tested.",
                "Do not use prompts like 'You are functional testing the skill at SKILL.md path: ...'.",
                "Do not ask the target skill to simulate a test scenario.",
                "Do not ask the target skill to trace through or walk through SKILL.md.",
                "Do not ask the target skill to output the reviewer JSON schema.",
                "Do not include reviewer scoring criteria in the target-skill user message.",
                "Do not send reviewer_instruction or dialogue_execution_protocol to the target subagent.",
                "Do not submit inferred dialogue turns or unverified issue claims without observable target output.",
            ],
        },
        "agent_launch_plan": {
            "launch_policy": "generate_scenarios_then_one_target_subagent_per_scenario",
            "subagent_count": planned_scenario_count,
            "scenario_count_rule": scenario_context["scenario_count_rule"],
            "main_agent_tracking_required": True,
            "completion_condition": "all generated scenario subagents have completed and the main agent has submitted a valid functional verdict, or a blocking failure is recorded",
            "result_owner": "main_agent_after_generating_scenarios_and_observing_target_subagent_outputs",
        },
        "target_agent_tasks": [],
        "target_agent_tasks_status": "not_precomputed_main_agent_must_generate_from_scenario_generation_context",
        "main_agent_scenario_output_schema": {
            "main_agent_scenarios": [scenario_context["scenario_output_contract"]],
            "target_agent_tasks": [
                {
                    "id": "T1",
                    "subagent_name": "functional-<skill>-t1",
                    "description": "Run generated real user scenario T1",
                    "prompt": "加载 <target SKILL.md path> 并作为该 Skill 回答用户问题。\n\n用户: {user_request}",
                    "prompt_type": "production_like_skill_load_plus_raw_user_utterance",
                    "send_this_prompt_to_target_subagent": True,
                    "skill_md_path_reference": "<target SKILL.md path>",
                    "do_not_append_reviewer_schema_or_test_instructions": True,
                }
            ],
        },
        "result_file": str(result_file),
        "helper_command": (
            "python <skill-reviewer-v2>/scripts/review.py submit-functional "
            f"--review-output-dir \"{result_file.parent}\" --from-file \"<functional-verdict.json>\""
        ),
        "output_schema_visibility": "main_agent_observation_record_only_never_send_to_target_subagent",
        "output_schema": {
            "status": "pass|blocked|needs_config",
            "reviewed_by": "subagent",
            "execution_method": "subagent_dialogue|isolated_test_agent",
            "static_analysis_only": False,
            "scenario_generation_method": "main_agent_llm_from_skill_md_path_or_existing_context",
            "scenarios": [
                {
                    "id": "T1",
                    "agent_task_id": "T1",
                    "title": "short scenario title",
                    "scenario_type": "core_function|complete_flow|edge_or_safety|branch_coverage",
                    "user_request": "raw natural user request sent to the target subagent",
                    "target_agent_prompt": "exact prompt sent to the target subagent, using: 加载 <SKILL.md path> 并作为该 Skill 回答用户问题。\\n\\n用户: <user_request>",
                    "dialogue_turns": ["user: ...", "assistant: ...", "user: optional follow-up", "assistant: ..."],
                    "intent_recognized": "yes|partial|no",
                    "skill_invoked": "yes|partial|no|not_observable",
                    "artifacts_observed": ["file/url/widget/tool output observed, or empty list"],
                    "output_quality": "pass|warn|blocked",
                    "result": "pass|warn|blocked|needs_config",
                    "evidence": "specific observed behavior, not inferred from SKILL.md",
                    "issue_verification": "directly verified source/runtime evidence for each issue, or none",
                    "notes": "optional",
                }
            ],
            "summary": "short conclusion",
            "must_not_pass_if": [
                "no subagent or equivalent isolated test agent was used",
                "dialogue turns are inferred from static code/instruction analysis",
                "artifacts or outputs required by the workflow were not actually observed",
                "the target skill was asked to output JSON/test results instead of receiving natural user requests",
                "reported issues were copied from target subagents without source/runtime verification",
            ],
        },
        "suggested_user_request_seeds": [],
        "suggested_user_request_seeds_status": "deprecated_not_generated_to_avoid_mechanical_prompt_seeds",
        "skill_name": skill_name,
        "script_executability": script_executability,
        "configuration_requirements": review_result.get("configuration_requirements") or {},
        "text_inventory": _collect_text_review_inventory(skill_dir, max_file_chars=6000, max_total_chars=60000),
    }


def _apply_functional_config_override(config_requirements: dict, *, config_ack: str = "", force_functional: bool = False) -> dict:
    """Allow a user-confirmed override to reach the functional dialogue request."""
    if not config_requirements.get("required_for_complete_functional_test"):
        return config_requirements
    ack = str(config_ack or "").strip()
    if not ack and not force_functional:
        return config_requirements
    overridden = dict(config_requirements)
    original_required = bool(overridden.get("required_for_complete_functional_test"))
    overridden["required_for_complete_functional_test"] = False
    overridden["original_required_for_complete_functional_test"] = original_required
    overridden["config_gate_overridden"] = True
    overridden["config_gate_override_method"] = "force_functional" if force_functional and not ack else "user_ack"
    if ack:
        overridden["config_gate_acknowledgement"] = ack
    notes = list(overridden.get("config_scan_notes") or [])
    notes.append(
        "Configuration detection was acknowledged/overridden so Stage 03 can request real subagent dialogue validation."
    )
    overridden["config_scan_notes"] = notes
    instructions = list(overridden.get("instructions") or [])
    if instructions:
        overridden["original_instructions"] = instructions
    overridden["instructions"] = []
    return overridden


def run_functional_test_stage(
    skill_dir: Path,
    skill_name: str,
    review_result: dict,
    output_dir: Path,
    force_test: bool = False,
    functional_test_file: str | Path | None = None,
    config_ack: str = "",
    force_functional: bool = False,
) -> dict:
    source_meta = _load_source_metadata(skill_dir, skill_name, review_result.get("frontmatter", {}))
    config_requirements = review_result.get("configuration_requirements") or detect_configuration_requirements(skill_dir)
    config_requirements = _apply_functional_config_override(
        config_requirements,
        config_ack=config_ack,
        force_functional=force_functional,
    )
    review_result = dict(review_result)
    review_result["configuration_requirements"] = config_requirements
    mode = review_result.get("mode", "workflow")
    is_new = review_result.get("deep_review_context", {}).get("is_new_listing")
    is_update = is_new is False
    required = bool(force_test or force_functional or mode == "review-only" or is_new is not False)

    if mode == "workflow" and is_update and not (force_test or force_functional):
        return {
            "stage": "functional",
            "skill_name": skill_name,
            "required": False,
            "test_executed": False,
            "recommendation": "skip",
            "overall": "skipped",
            "status": "skipped",
            "skipped": True,
            "skip_reason": "version_update",
            "skip_rule": "workflow_version_update_without_force_test",
            "reason": "functional_validation_skipped_for_workflow_version_update",
            "summary": "Workflow version update: Stage 03 functional dialogue validation skipped by rule. Use --force-test to require it.",
            "source_metadata": source_meta,
        }

    content = (skill_dir / "SKILL.md").read_text(encoding="utf-8-sig", errors="replace") if (skill_dir / "SKILL.md").exists() else ""
    fm = review_result.get("frontmatter", {}) if isinstance(review_result.get("frontmatter"), dict) else {}
    _, body, _ = parse_frontmatter(content) if content else ({}, "", "missing")
    candidate = Path(functional_test_file) if functional_test_file else output_dir / FUNCTIONAL_DIALOGUE_RESULT_FILENAME
    result = _load_json_if_exists(candidate)
    tester_script = _find_tester_script()
    script_executability = validate_script_executability(skill_dir)
    planned_scenario_count = _estimate_functional_scenario_count(body, fm, script_executability)

    if required and script_executability.get("status") == "blocked":

        return {
            "stage": "functional",
            "skill_name": skill_name,
            "required": required,
            "test_executed": False,
            "recommendation": "blocked",
            "overall": "blocked",
            "status": "blocked",
            "reason": "script_executability_failed",
            "result_file": str(candidate),
            "scenario_count": 0,
            "planned_scenario_count": planned_scenario_count,
            "scenarios": [],
            "scenario_generation_required": True,
            "script_executability": script_executability,
            "configuration_requirements": config_requirements,
            "needs_config_instructions": config_requirements.get("instructions", []) if config_requirements.get("required_for_complete_functional_test") else [],
            "summary": script_executability.get("summary", ""),
        }

    if not result:
        if required and config_requirements.get("required_for_complete_functional_test"):
            return {
                "stage": "functional",
                "skill_name": skill_name,
                "required": required,
                "test_executed": False,
                "recommendation": "needs_config",
                "overall": "needs_config",
                "status": "needs_config",
                "reason": "configuration_required_before_functional_dialogue_test",
                "result_file": str(candidate),
                "scenario_count": 0,
                "planned_scenario_count": planned_scenario_count,
                "scenarios": [],
                "scenario_generation_required": True,
                "script_executability": script_executability,
                "configuration_requirements": config_requirements,
                "needs_config_instructions": config_requirements.get("instructions", []),
                "functional_test_request": _functional_test_request(skill_dir, skill_name, review_result, planned_scenario_count, candidate, script_executability, content, body),
            }
        return {
            "stage": "functional",
            "skill_name": skill_name,
            "required": required,
            "test_executed": False,
            "recommendation": "requires_ai_review" if required else "skip",
            "overall": "requires_ai_review" if required else "skipped",
            "status": "requires_ai_review" if required else "skipped",
            "reason": "functional_dialogue_subagent_result_required",
            "result_file": str(candidate),
            "scenario_count": 0,
            "planned_scenario_count": planned_scenario_count,
            "scenarios": [],
            "scenario_generation_required": True,
            "script_executability": script_executability,
            "tester_options": {
                "builtin_dialogue_request": True,
                "external_skill_tester_v2": bool(tester_script),
                "external_script": str(tester_script) if tester_script else "",
            },
            "configuration_requirements": config_requirements,
            "needs_config_instructions": config_requirements.get("instructions", []) if required and config_requirements.get("required_for_complete_functional_test") else [],
            "functional_test_request": _functional_test_request(skill_dir, skill_name, review_result, planned_scenario_count, candidate, script_executability, content, body) if required else None,
        }

    if result.get("status") == "invalid" and "error" in result:
        return {
            "stage": "functional",
            "skill_name": skill_name,
            "required": required,
            "test_executed": False,
            "recommendation": "requires_ai_review",
            "overall": "requires_ai_review",
            "status": "requires_ai_review",
            "reason": "functional_dialogue_result_invalid_json",
            "result": result,
            "result_file": str(candidate),
            "script_executability": script_executability,
            "functional_test_request": _functional_test_request(skill_dir, skill_name, review_result, planned_scenario_count, candidate, script_executability, content, body),
            "configuration_requirements": config_requirements,
        }

    normalized = _normalize_functional_verdict(result)
    errors, warnings = validate_functional_verdict(normalized)
    if errors:
        return {
            "stage": "functional",
            "skill_name": skill_name,
            "required": required,
            "test_executed": False,
            "recommendation": "requires_ai_review",
            "overall": "requires_ai_review",
            "status": "requires_ai_review",
            "reason": "functional_dialogue_result_invalid",
            "errors": errors,
            "warnings": warnings,
            "result": normalized,
            "result_file": str(candidate),
            "script_executability": script_executability,
            "functional_test_request": _functional_test_request(skill_dir, skill_name, review_result, planned_scenario_count, candidate, script_executability, content, body),
            "configuration_requirements": config_requirements,
        }

    rec = normalized.get("status")
    if (
        required
        and config_requirements.get("required_for_complete_functional_test")
        and rec not in {"blocked", "needs_config"}
    ):
        warnings.append(
            "configuration requirements were detected, but a valid submitted functional verdict exists; keeping the submitted verdict"
        )

    return {
        "stage": "functional",
        "skill_name": skill_name,
        "required": required,
        "test_executed": rec in {"pass", "blocked"},
        "recommendation": rec,
        "overall": rec,
        "status": rec,
        "result_file": str(candidate),
        "scenario_count": len(normalized.get("scenarios", [])),
        "scenarios": normalized.get("scenarios", []),
        "result": normalized,
        "warnings": warnings,
        "script_executability": script_executability,
        "configuration_requirements": config_requirements,
        "needs_config_instructions": normalized.get("needs_config_instructions", []),
        "source_metadata": source_meta,
    }
