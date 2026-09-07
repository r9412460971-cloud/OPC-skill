#!/usr/bin/env python3
"""Regression tests for staged reviewer workflow behavior."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from datetime import date
from pathlib import Path


REVIEW_PATH = Path(__file__).resolve().parent / "review.py"
spec = importlib.util.spec_from_file_location("review_under_test", REVIEW_PATH)
review = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(review)

BATCH_PATH = Path(__file__).resolve().parent / "batch.py"
batch_spec = importlib.util.spec_from_file_location("batch_under_test", BATCH_PATH)
batch = importlib.util.module_from_spec(batch_spec)
assert batch_spec and batch_spec.loader
batch_spec.loader.exec_module(batch)


def _write_skill(root: Path, body: str) -> None:
    (root / "SKILL.md").write_text(
        "---\n"
        "name: demo-skill\n"
        "description: Demo skill for staged workflow regression tests.\n"
        "version: 1.0.0\n"
        "source_type: internal\n"
        "source_metadata_waived: true\n"
        "---\n\n"
        f"{body}\n",
        encoding="utf-8",
    )


def _semantic_security_pass() -> dict:
    return {
        "status": "pass",
        "reviewed_by": "security_subagent",
        "review_method": "subagent_semantic_security_review",
        "source_files_reviewed": ["SKILL.md", "02-risk.json"],
        "risk_categories_checked": [
            "credential",
            "privacy",
            "network",
            "unsafe_execution",
            "prompt_injection",
            "commercial_diversion",
            "legal",
            "configuration",
        ],
        "capability_inventory": [
            "SKILL.md and stage risk evidence were reviewed; no reachable script execution path remains after B23 exemption.",
            "No credential collection, privacy data access, external reporting, or commercial diversion behavior is present in reviewed files.",
        ],
        "reachability_analysis": [
            "The B23 finding is treated as a reviewed false positive and is not reachable as production install/runtime behavior.",
            "No documentation example instructs the agent to execute a risky command as-is in normal skill operation.",
        ],
        "findings": [],
        "summary": "Security subagent reviewed the listed files, covered required risk areas, and found no reachable semantic safety blocker.",
    }


def test_functional_stage_pauses_for_missing_config():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_skill(root, "Set DEMO_API_KEY before running the skill, then ask it to fetch data.")
        stage = review.run_functional_test_stage(
            root,
            "demo-skill",
            {
                "skill_name": "demo-skill",
                "frontmatter": {"name": "demo-skill"},
                "deep_review_context": {"is_new_listing": True},
            },
            root / "review-output",
        )

    assert stage["status"] == "needs_config"
    assert stage["recommendation"] == "needs_config"
    assert stage["needs_config_instructions"]
    assert stage["script_executability"]["status"] == "not_applicable"


def test_functional_stage_pauses_for_unresolved_mcp_or_login_config():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_skill(root, "Before use, configure the production MCP server and login to the account console.")
        stage = review.run_functional_test_stage(
            root,
            "demo-skill",
            {
                "skill_name": "demo-skill",
                "frontmatter": {"name": "demo-skill"},
                "deep_review_context": {"is_new_listing": True},
            },
            root / "review-output",
        )

    assert stage["status"] == "needs_config"
    assert stage["configuration_requirements"]["unresolved_external_signals"]


def test_functional_stage_does_not_pause_for_negated_config_need():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_skill(root, "This skill does not need an API key, token, login, auth, credential, or MCP setup.")
        stage = review.run_functional_test_stage(
            root,
            "demo-skill",
            {
                "skill_name": "demo-skill",
                "frontmatter": {"name": "demo-skill"},
                "deep_review_context": {"is_new_listing": True},
            },
            root / "review-output",
        )

    assert stage["status"] == "requires_ai_review"
    assert not stage["configuration_requirements"]["required_for_complete_functional_test"]


def test_functional_stage_ignores_weak_policy_config_words_without_external_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        references = root / "references"
        references.mkdir()
        _write_skill(root, "Use local data only to compare two tournament teams.")
        (references / "safety_policy.md").write_text(
            "合规说明：如涉及登录、授权、MCP 或配置字样，仅作为政策背景，不是运行依赖。",
            encoding="utf-8",
        )
        stage = review.run_functional_test_stage(
            root,
            "demo-skill",
            {
                "skill_name": "demo-skill",
                "frontmatter": {"name": "demo-skill"},
                "deep_review_context": {"is_new_listing": True},
            },
            root / "review-output",
        )

    assert stage["status"] == "requires_ai_review"
    assert stage["functional_test_request"]
    assert not stage["configuration_requirements"]["required_for_complete_functional_test"]
    assert stage["configuration_requirements"]["ignored_weak_signals"]


def test_functional_stage_ignores_browser_doc_pattern_and_llm_token_words():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_skill(
            root,
            "## Common Patterns\n"
            "Every browser automation follows this pattern:\n"
            "- create temp file path\n"
            "- call browser_snapshot\n"
            "- Markdown and text snapshots with shell command examples and temporary file paths\n"
            "Please call browser_snapshot only when necessary to avoid unnecessary token consumption.\n"
            "Token-efficient operation.\n",
        )
        stage = review.run_functional_test_stage(
            root,
            "demo-skill",
            {
                "skill_name": "demo-skill",
                "frontmatter": {"name": "demo-skill"},
                "deep_review_context": {"is_new_listing": True},
            },
            root / "review-output",
        )

    assert stage["status"] == "requires_ai_review"
    assert not stage["configuration_requirements"]["required_for_complete_functional_test"]


def test_b19_ignores_markdown_decode_terms_and_frontmatter_delimiter():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_skill(root, "Function Function Function")
        result = review.run_review(root, "demo-skill", mode="workflow")
        b19 = next(c for c in result["checks"] if c["id"] == "B19")

    assert b19["pass"] is True
    assert not b19.get("warning")
    assert "---" not in json.dumps(b19, ensure_ascii=False)


def test_b20_ignores_llm_token_consumption_text():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_skill(root, "Please avoid unnecessary token consumption. Token-efficient summaries are preferred.")
        result = review.run_review(root, "demo-skill", mode="workflow")
        b20 = next(c for c in result["checks"] if c["id"] == "B20")

    assert b20["pass"] is True
    assert "ai_action" not in b20


def test_semantic_verdict_normalizes_configuration_category_alias():
    from verdicts import _normalize_semantic_verdict, validate_semantic_verdict

    verdict = _semantic_security_pass()
    verdict["findings"] = [{
        "category": "configuration",
        "severity": "low",
        "decision": "warning",
        "reachability": "documentation_example",
        "evidence": [{"file": "SKILL.md", "line": 10, "text": "configuration guidance wording"}],
        "rationale": "Configuration guidance is partial but not a security blocker.",
    }]
    normalized = _normalize_semantic_verdict(verdict)
    errors, _warnings = validate_semantic_verdict(normalized)

    assert normalized["findings"][0]["category"] == "config_guidance"
    assert not errors


def test_autopilot_outputs_strict_next_actions_without_user_ask():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "demo"
        root.mkdir()
        _write_skill(root, "Summarize text and return concise bullet points.")
        result = review.run_staged_review(
            root,
            "demo-skill",
            mode="workflow",
            output_dir=Path(tmp) / "review-output",
            autopilot=True,
        )

    workflow = result["workflow_next"]
    assert workflow["mode"] == "autopilot"
    assert workflow["phase"] == "review"
    assert workflow["ask_user_now"] is False
    assert workflow["actions"]
    assert all(action["type"] != "ask_user" for action in workflow["actions"])


def test_functional_stage_config_ack_reaches_dialogue_request():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_skill(root, "Set DEMO_API_KEY before running the skill, then ask it to fetch data.")
        stage = review.run_functional_test_stage(
            root,
            "demo-skill",
            {
                "skill_name": "demo-skill",
                "frontmatter": {"name": "demo-skill"},
                "deep_review_context": {"is_new_listing": True},
            },
            root / "review-output",
            config_ack="confirmed: local fixture does not need external config",
        )

    assert stage["status"] == "requires_ai_review"
    assert stage["functional_test_request"]
    assert stage["configuration_requirements"]["config_gate_overridden"] is True
    assert stage["functional_test_request"]["configuration_requirements"]["config_gate_overridden"] is True


def test_functional_request_keeps_json_schema_out_of_target_prompt():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_skill(root, "Summarize a product brief and return risks, opportunities, and next steps.")
        stage = review.run_functional_test_stage(
            root,
            "demo-skill",
            {
                "skill_name": "demo-skill",
                "frontmatter": {
                    "name": "demo-skill",
                    "description": "Summarize a product brief and return risks, opportunities, and next steps.",
                },
                "deep_review_context": {"is_new_listing": True},
            },
            root / "review-output",
        )

    request = stage["functional_test_request"]
    assert request["target_skill"]["skill_md_path"].endswith("SKILL.md")
    assert request["target_skill"]["description"].startswith("Summarize a product brief")
    assert request["runner"] == "main_agent_generates_scenarios_then_launches_target_skill_subagents"
    assert request["scenario_generation_required"] is True
    assert request["planned_subagent_count"] >= 2
    assert request["target_agent_tasks"] == []
    assert request["target_agent_tasks_status"] == "not_precomputed_main_agent_must_generate_from_scenario_generation_context"
    assert request["scenario_generation_context"]["skill_md_path"].endswith("SKILL.md")
    assert request["scenario_generation_context"]["skill_md_read_required"] is True
    assert request["scenario_generation_context"]["skill_md_content_inlined"] is False
    assert "skill_md_content" not in request["scenario_generation_context"]
    assert "Do not mechanically copy" in " ".join(request["scenario_generation_context"]["hard_rules"])
    assert request["target_agent_prompt_boundary"]["prompt_template"] == "加载 {skill_md_path} 并作为该 Skill 回答用户问题。\n\n用户: {user_request}"
    assert request["target_agent_prompt_boundary"]["skill_md_path_visibility"] == "neutral_target_skill_reference_allowed"
    assert request["output_schema_visibility"] == "main_agent_observation_record_only_never_send_to_target_subagent"
    sample_prompt = request["main_agent_scenario_output_schema"]["target_agent_tasks"][0]["prompt"]
    assert sample_prompt == "加载 <target SKILL.md path> 并作为该 Skill 回答用户问题。\n\n用户: {user_request}"
    assert request["main_agent_scenario_output_schema"]["target_agent_tasks"][0]["prompt_type"] == "production_like_skill_load_plus_raw_user_utterance"
    assert request["agent_launch_plan"]["launch_policy"] == "generate_scenarios_then_one_target_subagent_per_scenario"


def test_functional_request_increases_subagents_for_complex_skill():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        body = """
## 触发场景
- 生成品牌诊断报告
- 查询多平台结果
- 导出图表和文档
## 工作流
用户可以补充品牌、平台、关键词，助手需要分析、评估、生成、导出报告。
## 输出
生成 HTML 报告、表格、图表，并支持后续优化。
""" + ("\n分析 生成 查询 导出 报告 追问 优化" * 500)
        _write_skill(root, body)
        stage = review.run_functional_test_stage(
            root,
            "complex-skill",
            {
                "skill_name": "complex-skill",
                "frontmatter": {"name": "complex-skill", "description": "生成品牌诊断报告，查询多平台结果并导出图表文档。"},
                "deep_review_context": {"is_new_listing": True},
            },
            root / "review-output",
        )

    request = stage["functional_test_request"]
    assert request["planned_subagent_count"] > 2
    assert request["scenario_generation_required"] is True
    assert request["target_agent_tasks"] == []
    assert request["scenario_generation_context"]["planned_scenario_count"] == request["planned_subagent_count"]


def test_functional_request_does_not_generate_scenarios_from_policy_snippets():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        body = """
## 核心能力
支持自然语言下单、商品搜索、规格选择和订单确认。

## 安全规范
1. 下单前强制确认，不允许跳过确认直接支付。
2. 下单失败不可自动重试，避免重复订单。
11. mainOrderNo 是售后查询铁律。

## 路径定位规则
2. Python 解释器不要硬编码，必须从环境变量读取。

## API 调用
Call client.search_products(keyword, page_num=1, page_size=8)，不要假设存在 --search CLI。
"""
        _write_skill(root, body)
        stage = review.run_functional_test_stage(
            root,
            "all-girls",
            {
                "skill_name": "all-girls",
                "frontmatter": {"name": "all-girls", "description": "所有女生会员服务中心，支持自然语言下单、导购式选品和商品搜索。"},
                "deep_review_context": {"is_new_listing": True},
            },
            root / "review-output",
        )

    request = stage["functional_test_request"]
    assert stage["scenarios"] == []
    assert request["suggested_user_request_seeds"] == []
    assert request["scenario_generation_required"] is True
    context = request["scenario_generation_context"]
    assert context["skill_md_content_inlined"] is False
    assert "skill_md_content" not in context
    assert any("下单前强制确认" in item["excerpt"] for item in context["reference_context_candidates"])
    assert any(item["usage"].startswith("reference_only") for item in context["reference_context_candidates"])
    hard_rules = " ".join(context["hard_rules"])
    assert "Do not mechanically copy" in hard_rules
    assert "Before carrying any subagent-reported issue" in hard_rules



def test_functional_stage_blocks_on_script_executability_failure():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        scripts = root / "scripts"
        scripts.mkdir()
        (scripts / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
        _write_skill(root, "Run the helper script and summarize its output.")
        stage = review.run_functional_test_stage(
            root,
            "demo-skill",
            {
                "skill_name": "demo-skill",
                "frontmatter": {"name": "demo-skill"},
                "deep_review_context": {"is_new_listing": True},
            },
            root / "review-output",
        )

    assert stage["status"] == "blocked"
    assert stage["recommendation"] == "blocked"
    assert stage["reason"] == "script_executability_failed"
    assert stage["script_executability"]["blocker_count"] == 1
    assert stage["script_executability"]["results"][0]["file"] == "scripts/broken.py"


def test_functional_stage_accepts_verdict_when_config_present():
    old_value = os.environ.get("DEMO_API_KEY")
    os.environ["DEMO_API_KEY"] = "configured-for-test"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "review-output"
            out.mkdir()
            _write_skill(root, "Set DEMO_API_KEY before running the skill, then ask it to fetch data.")
            (out / review.FUNCTIONAL_DIALOGUE_RESULT_FILENAME).write_text(
                json.dumps({
                    "status": "pass",
                    "reviewed_by": "subagent",
                    "execution_method": "subagent_dialogue",
                    "static_analysis_only": False,
                    "scenarios": [
                        {
                            "id": "T1",
                            "title": "configured request",
                            "user_request": "Fetch demo data",
                            "target_agent_prompt": "加载 /tmp/demo/SKILL.md 并作为该 Skill 回答用户问题。\n\n用户: Fetch demo data",
                            "dialogue_turns": ["user: Fetch demo data", "assistant: Fetched demo data"],
                            "intent_recognized": "yes",
                            "skill_invoked": "yes",
                            "artifacts_observed": [],
                            "output_quality": "pass",
                            "result": "pass",
                            "evidence": "DEMO_API_KEY was configured and the request path completed",
                        },
                        {
                            "id": "T2",
                            "title": "error handling",
                            "user_request": "Fetch missing demo data",
                            "target_agent_prompt": "加载 /tmp/demo/SKILL.md 并作为该 Skill 回答用户问题。\n\n用户: Fetch missing demo data",
                            "dialogue_turns": ["user: Fetch missing demo data", "assistant: Reported not found"],
                            "intent_recognized": "yes",
                            "skill_invoked": "yes",
                            "artifacts_observed": [],
                            "output_quality": "pass",
                            "result": "pass",
                            "evidence": "The missing data path returned a bounded response",
                        },
                    ],
                    "summary": "Functional validation passed.",
                }),
                encoding="utf-8",
            )
            stage = review.run_functional_test_stage(
                root,
                "demo-skill",
                {
                    "skill_name": "demo-skill",
                    "frontmatter": {"name": "demo-skill"},
                    "deep_review_context": {"is_new_listing": True},
                },
                out,
            )
    finally:
        if old_value is None:
            os.environ.pop("DEMO_API_KEY", None)
        else:
            os.environ["DEMO_API_KEY"] = old_value

    assert stage["status"] == "pass"
    assert stage["test_executed"] is True
    assert not stage["needs_config_instructions"]


def test_functional_stage_rejects_static_analysis_pass():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = root / "review-output"
        out.mkdir()
        _write_skill(root, "Ask the skill to decompose an image and verify PNG/JSON outputs.")
        (out / review.FUNCTIONAL_DIALOGUE_RESULT_FILENAME).write_text(
            json.dumps({
                "status": "pass",
                "reviewed_by": "subagent",
                "execution_method": "subagent_dialogue",
                "static_analysis_only": False,
                "scenarios": [
                    {
                        "id": "T1",
                        "title": "static image decomposition",
                        "user_request": "Decompose this image",
                        "dialogue_turns": [
                            "user: Decompose this image",
                            "assistant: I reviewed the code path but did not actually execute it",
                        ],
                        "result": "pass",
                        "evidence": "Pass is based on static analysis; no subagent simulated real output.",
                    },
                    {
                        "id": "T2",
                        "title": "static artifact check",
                        "user_request": "Confirm PNG and JSON artifacts",
                        "dialogue_turns": [
                            "user: Confirm PNG and JSON artifacts",
                            "assistant: No artifacts were observed; this is code analysis only",
                        ],
                        "result": "pass",
                        "evidence": "没有实际输出结果，也没有调用 subagent。",
                    },
                ],
                "summary": "基于代码静态分析提交 pass，没有真正完成功能实测。",
            }),
            encoding="utf-8",
        )
        stage = review.run_functional_test_stage(
            root,
            "demo-skill",
            {
                "skill_name": "demo-skill",
                "frontmatter": {"name": "demo-skill"},
                "deep_review_context": {"is_new_listing": True},
            },
            out,
        )

    assert stage["status"] == "requires_ai_review"
    assert stage["reason"] == "functional_dialogue_result_invalid"
    assert any("static analysis" in error or "静态" in error for error in stage["errors"])


def test_functional_stage_rejects_test_harness_prompt_leak():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = root / "review-output"
        out.mkdir()
        _write_skill(root, "Summarize a product brief and return risks, opportunities, and next steps.")
        (out / review.FUNCTIONAL_DIALOGUE_RESULT_FILENAME).write_text(
            json.dumps({
                "status": "pass",
                "reviewed_by": "subagent",
                "execution_method": "subagent_dialogue",
                "static_analysis_only": False,
                "scenarios": [
                    {
                        "id": "T1",
                        "title": "leaked schema",
                        "user_request": "按以下精确的 JSON 格式生成结构化的功能测试结果。",
                        "dialogue_turns": [
                            "user: 按以下精确的 JSON 格式生成结构化的功能测试结果。",
                            "assistant: {\"status\":\"pass\"}",
                        ],
                        "result": "pass",
                        "evidence": "Target returned a JSON test report.",
                    },
                    {
                        "id": "T2",
                        "title": "normal request",
                        "user_request": "Summarize this product brief.",
                        "dialogue_turns": [
                            "user: Summarize this product brief.",
                            "assistant: Returned risks and next steps.",
                        ],
                        "result": "pass",
                        "evidence": "Target returned a product summary.",
                    },
                ],
                "summary": "Functional validation passed.",
            }),
            encoding="utf-8",
        )
        stage = review.run_functional_test_stage(
            root,
            "demo-skill",
            {
                "skill_name": "demo-skill",
                "frontmatter": {"name": "demo-skill"},
                "deep_review_context": {"is_new_listing": True},
            },
            out,
        )

    assert stage["status"] == "requires_ai_review"
    assert any("test-harness" in error for error in stage["errors"])


def test_functional_stage_rejects_skill_md_workflow_trace_as_pass():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = root / "review-output"
        out.mkdir()
        _write_skill(root, "Summarize a product brief and return risks, opportunities, and next steps.")
        (out / review.FUNCTIONAL_DIALOGUE_RESULT_FILENAME).write_text(
            json.dumps({
                "status": "pass",
                "reviewed_by": "subagent",
                "execution_method": "subagent_dialogue",
                "static_analysis_only": False,
                "scenarios": [
                    {
                        "id": "T1",
                        "title": "workflow trace",
                        "user_request": "Summarize this product brief.",
                        "dialogue_turns": [
                            "user: Summarize this product brief.",
                            "assistant: I will trace through the SKILL.md workflow instead of running the skill.",
                        ],
                        "intent_recognized": "yes",
                        "skill_invoked": "yes",
                        "artifacts_observed": [],
                        "output_quality": "pass",
                        "result": "pass",
                        "evidence": "The response is only a workflow walkthrough.",
                    },
                    {
                        "id": "T2",
                        "title": "normal request",
                        "user_request": "List risks from this launch note.",
                        "dialogue_turns": [
                            "user: List risks from this launch note.",
                            "assistant: Returned risks and next steps.",
                        ],
                        "intent_recognized": "yes",
                        "skill_invoked": "yes",
                        "artifacts_observed": [],
                        "output_quality": "pass",
                        "result": "pass",
                        "evidence": "Target returned a product summary.",
                    },
                ],
                "summary": "Functional validation passed.",
            }),
            encoding="utf-8",
        )
        stage = review.run_functional_test_stage(
            root,
            "demo-skill",
            {
                "skill_name": "demo-skill",
                "frontmatter": {"name": "demo-skill"},
                "deep_review_context": {"is_new_listing": True},
            },
            out,
        )

    assert stage["status"] == "requires_ai_review"
    assert any("workflow walkthrough" in error or "SKILL.md" in error for error in stage["errors"])


def test_functional_stage_skips_workflow_update_explicitly():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_skill(root, "Set DEMO_API_KEY before running the skill, then ask it to fetch data.")
        stage = review.run_functional_test_stage(
            root,
            "demo-skill",
            {
                "mode": "workflow",
                "skill_name": "demo-skill",
                "frontmatter": {"name": "demo-skill"},
                "deep_review_context": {"is_new_listing": False},
            },
            root / "review-output",
        )

    assert stage["required"] is False
    assert stage["test_executed"] is False
    assert stage["status"] == "skipped"
    assert stage["skipped"] is True
    assert stage["skip_reason"] == "version_update"


def test_functional_stage_force_functional_requires_update_and_bypasses_config_gate():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_skill(root, "Set DEMO_API_KEY before running the skill, then ask it to fetch data.")
        stage = review.run_functional_test_stage(
            root,
            "demo-skill",
            {
                "mode": "workflow",
                "skill_name": "demo-skill",
                "frontmatter": {"name": "demo-skill"},
                "deep_review_context": {"is_new_listing": False},
            },
            root / "review-output",
            force_functional=True,
        )

    assert stage["required"] is True
    assert stage["status"] == "requires_ai_review"
    assert stage["functional_test_request"]
    assert stage["configuration_requirements"]["config_gate_override_method"] == "force_functional"


def test_review_exemption_recomputes_blockers():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "review-output"
        out.mkdir()
        (out / review.REVIEW_EXEMPTIONS_FILENAME).write_text(
            json.dumps({
                "schema_version": "1.0",
                "exemptions": [{"check_id": "B15", "decision": "false_positive", "reason": "Mermaid node label"}],
            }),
            encoding="utf-8",
        )
        base = {
            "status": "blocked",
            "checks": [{"id": "B15", "pass": False, "msg": "断链引用"}],
            "blocker_count": 1,
            "warning_count": 0,
        }
        updated = review._apply_review_exemptions(base, review._load_review_exemptions(out))

    assert updated["status"] == "passed"
    assert updated["blocker_count"] == 0
    assert updated["checks"][0]["warning"] is True
    assert updated["checks"][0]["false_positive"] is True


def test_review_exemption_updates_nested_b23_status_for_risk_gate():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "review-output"
        out.mkdir()
        (out / review.REVIEW_EXEMPTIONS_FILENAME).write_text(
            json.dumps({
                "schema_version": "1.0",
                "exemptions": [{"check_id": "B23", "decision": "false_positive", "reason": "Verified safe link"}],
            }),
            encoding="utf-8",
        )
        (out / review.SEMANTIC_REVIEW_FILENAME).write_text(
            json.dumps(_semantic_security_pass()),
            encoding="utf-8",
        )
        base = {
            "skill_name": "demo-skill",
            "frontmatter": {},
            "configuration_requirements": {"status": "not_applicable", "requirements": []},
            "status": "blocked",
            "checks": [{
                "id": "B23",
                "pass": False,
                "msg": "1 blocking script/link risk",
                "details": {
                    "status": "blocked",
                    "summary": "1 blocking script/link risk",
                    "blockers": [{"type": "remote_pipe_to_interpreter"}],
                    "warnings": [],
                },
            }],
            "blocker_count": 1,
            "warning_count": 0,
        }
        updated = review._apply_review_exemptions(base, review._load_review_exemptions(out))
        stage = review.build_risk_stage(Path(tmp), "demo-skill", updated, updated["checks"], out)

    assert updated["checks"][0]["pass"] is True
    assert updated["checks"][0]["details"]["status"] == "passed"
    assert updated["checks"][0]["details"]["original_status"] == "blocked"
    assert stage["status"] == "passed"
    assert stage["script_link_validation"]["status"] == "passed"


def test_risk_stage_rejects_shallow_semantic_pass():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = root / "review-output"
        out.mkdir()
        _write_skill(root, "Summarize local notes without network access or command execution.")
        (out / review.SEMANTIC_REVIEW_FILENAME).write_text(
            json.dumps({"status": "pass", "reviewed_by": "llm", "findings": [], "summary": "ok"}),
            encoding="utf-8",
        )
        b23 = review.check_b23_script_link_risk(root)
        stage = review.build_risk_stage(
            root,
            "demo-skill",
            {"skill_name": "demo-skill", "frontmatter": {}},
            [b23],
            out,
        )

    assert stage["status"] == "requires_ai_review"
    assert stage["semantic_review"]["status"] == "invalid"
    assert stage["semantic_review_quality_gate"]["status"] == "invalid"
    assert any("reviewed_by" in error for error in stage["semantic_review"]["errors"])


def test_risk_stage_accepts_deep_subagent_semantic_pass():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = root / "review-output"
        out.mkdir()
        _write_skill(root, "Summarize local notes without network access or command execution.")
        (out / review.SEMANTIC_REVIEW_FILENAME).write_text(
            json.dumps(_semantic_security_pass()),
            encoding="utf-8",
        )
        b23 = review.check_b23_script_link_risk(root)
        stage = review.build_risk_stage(
            root,
            "demo-skill",
            {"skill_name": "demo-skill", "frontmatter": {}},
            [b23],
            out,
        )

    assert stage["status"] == "passed"
    assert stage["semantic_review"]["reviewed_by"] == "security_subagent"
    assert stage["semantic_review_quality_gate"]["status"] == "passed"


def test_final_stage_records_functional_skip_reason():
    final_stage = review.build_final_stage(
        {
            "mode": "workflow",
            "skill_name": "demo-skill",
            "status": "passed",
            "blocker_count": 0,
            "warning_count": 0,
            "checks": [],
            "deep_review_context": {"is_new_listing": False},
            "frontmatter": {"name": "demo-skill", "version": "1.0.1"},
        },
        {"status": "passed"},
        {"status": "passed"},
        {
            "stage": "functional",
            "required": False,
            "test_executed": False,
            "recommendation": "skip",
            "overall": "skipped",
            "status": "skipped",
            "skipped": True,
            "skip_reason": "version_update",
        },
        {"status": "skipped", "skipped": True, "skip_reason": "version_update"},
    )

    assert final_stage["stage_status"]["functional"] == "skipped"
    functional_records = [
        item for item in final_stage["handling_records"]
        if item.get("type") == "functional_validation"
    ]
    assert functional_records
    assert functional_records[0]["handling"] == "skipped_by_rule"
    assert functional_records[0]["skip_reason"] == "version_update"


def test_deep_stage_rejects_shallow_main_agent_review():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = root / "review-output"
        out.mkdir()
        (out / review.DEEP_REVIEW_FILENAME).write_text(
            json.dumps({
                "status": "pass",
                "reviewed_by": "llm",
                "dimensions": [
                    {
                        "id": "context_efficiency",
                        "rating": "good",
                        "score": 8,
                        "evidence": ["Looks concise."],
                        "summary": "Context is efficient.",
                    }
                ],
                "summary": "Deep quality review passed.",
            }),
            encoding="utf-8",
        )
        stage = review.build_deep_review_stage(
            {
                "skill_name": "demo-skill",
                "deep_review_context": {
                    "is_new_listing": True,
                    "skip_deep_review": False,
                },
            },
            out,
        )

    assert stage["status"] == "requires_ai_review"
    assert any("reviewed_by" in error for error in stage["errors"])
    assert any("source_files_reviewed" in error for error in stage["errors"])
    assert any("evidence" in error for error in stage["errors"])


def test_deep_stage_accepts_subagent_evidence_rich_review():
    dimension_ids = [
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
    ]
    dimensions = [
        {
            "id": dim_id,
            "rating": "good",
            "score": 7,
            "evidence": [
                f"SKILL.md section for {dim_id} was checked and contains 2 concrete workflow constraints.",
                f"references/{dim_id}.md or scripts/example.py evidence was compared against 3 documented user paths.",
            ],
            "rationale": f"{dim_id} has usable coverage with specific evidence, but still has improvement room.",
            "recommendation": f"Add one more concrete {dim_id} example tied to expected user behavior.",
        }
        for dim_id in dimension_ids
    ]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = root / "review-output"
        out.mkdir()
        (out / review.DEEP_REVIEW_FILENAME).write_text(
            json.dumps({
                "status": "pass",
                "reviewed_by": "deep_review_subagent",
                "review_method": "subagent_deep_review",
                "source_files_reviewed": ["SKILL.md", "references/example.md", "scripts/example.py"],
                "cross_dimension_checks": [
                    "context_efficiency evidence was compared against executability and maintainability.",
                    "portability evidence was compared against setup guidance and script path handling.",
                ],
                "dimensions": dimensions,
                "summary": "Deep quality review completed with evidence-rich per-dimension judgments.",
            }),
            encoding="utf-8",
        )
        stage = review.build_deep_review_stage(
            {
                "skill_name": "demo-skill",
                "deep_review_context": {
                    "is_new_listing": True,
                    "skip_deep_review": False,
                },
            },
            out,
        )

    assert stage["status"] == "passed"
    assert not stage["errors"]


def test_report_hydrates_final_gate_with_sibling_stage_files():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "review-output"
        out.mkdir()
        (out / "01-structure.json").write_text(
            json.dumps({
                "status": "passed",
                "checks": [
                    {"id": "B01", "pass": True, "msg": "SKILL.md 存在且非空"},
                    {"id": "B03", "pass": True, "warning": True, "msg": "description 过短（12 字符，建议 50-200）"},
                ],
                "frontmatter": {"name": "demo-skill", "version": "1.0.0"},
            }),
            encoding="utf-8",
        )
        (out / "02-risk.json").write_text(
            json.dumps({"status": "requires_ai_review", "script_link_validation": {"status": "passed", "summary": "0 blocking script/link risk(s)."}}),
            encoding="utf-8",
        )
        semantic_path = out / "02-risk-semantic-review.json"
        semantic_path.write_text(json.dumps(_semantic_security_pass()), encoding="utf-8")
        functional_path = out / "03-functional-dialogue-test-result.json"
        functional_path.write_text(
            json.dumps({
                "status": "pass",
                "execution_method": "subagent_dialogue",
                "static_analysis_only": False,
                "scenarios": [
                    {"title": "真实用户请求", "user_request": "帮我生成行业方案", "result": "pass", "evidence": "show_form 和资料检索均触发"}
                ],
                "summary": "功能场景通过。",
            }),
            encoding="utf-8",
        )
        (out / "04-deep-quality-review-result.json").write_text(
            json.dumps({
                "status": "pass",
                "reviewed_by": "deep_review_subagent",
                "review_method": "subagent_deep_review",
                "source_files_reviewed": ["SKILL.md"],
                "dimensions": [
                    {"id": "fault_tolerance", "rating": "needs_work", "score": 5, "evidence": ["缺少工具失败兜底"], "rationale": "工具失败路径不足", "recommendation": "补充降级策略"},
                    {"id": "user_experience", "rating": "good", "score": 8, "evidence": ["表单清晰"], "rationale": "交互清楚", "recommendation": "继续保持"},
                ],
                "summary": "深度质量审查完成。",
            }),
            encoding="utf-8",
        )
        report = review.generate_report({
            "stage": "final",
            "skill_name": "demo-skill",
            "status": "reviewed",
            "review_gate": {"status": "pass", "can_upload": True, "warning_checks": ["B03"], "functional": "pass", "risk": "passed", "deep_review": "passed"},
            "handling_records": [
                {"type": "semantic_risk_review", "path": str(semantic_path), "outcome": "pass"},
                {"type": "functional_validation", "result_file": str(functional_path), "outcome": "pass"},
            ],
        })

    assert "数据不完整" not in report
    assert "description 长度" in report
    assert "description 过短" in report
    assert "帮我生成行业方案" in report
    assert "均分 6.5/10" in report
    assert "容错与降级" in report
    assert "建议关注_checks" not in report
    assert "待复核草稿" in report
    assert "风险判定理由" not in report
    assert "内部处理记录" not in report
    assert "允许上传 | 是" not in report



def test_report_uses_verified_issues_when_provided():
    report = review.generate_report({
        "skill_name": "demo-skill",
        "status": "reviewed",
        "final_status": "reviewed",
        "frontmatter": {"name": "demo-skill", "version": "1.0.0"},
        "checks": [],
        "functional_test": {},
        "deep_stage": {},
        "report_verification": {
            "status": "verified",
            "reviewed_by": "llm_cross_check",
            "issues": [
                {"priority": "P1", "issue": "错误处理不足", "impact": "核心工具失败时用户无法获得明确兜底", "recommendation": "补充超时、失败和重试说明"}
            ],
        },
    })

    assert "已完成问题真实性与严重性复核" in report
    assert "待复核草稿" not in report
    assert "错误处理不足" in report
    assert "核心工具失败" in report



def test_report_warns_when_final_gate_lacks_stage_details():
    report = review.generate_report({
        "stage": "final",
        "skill_name": "demo-skill",
        "status": "reviewed",
        "review_gate": {"status": "pass", "can_upload": True, "functional": "pass", "risk": "passed", "deep_review": "passed"},
    })

    assert "数据不完整" in report
    assert "只凭最终门禁摘要" in report
    assert "结构、风险、功能与深度质量表现整体稳定" not in report



def test_partner_report_uses_generated_date():
    report = review.generate_partner_test_report({
        "skill_name": "demo-skill",
        "status": "reviewed",
        "final_status": "reviewed",
        "blocker_count": 0,
        "warning_count": 0,
        "parse_method": "frontmatter",
        "frontmatter": {"name": "demo-skill", "version": "1.0.0"},
        "checks": [],
        "functional_test": {},
        "deep_stage": {},
        "deep_review_context": {"is_new_listing": True},
    })

    assert "today_str" not in report
    assert date.today().isoformat() in report


def test_partner_report_omits_platform_version_checks_from_recommendations():
    report = review.generate_partner_test_report({
        "skill_name": "demo-skill",
        "status": "blocked",
        "final_status": "blocked",
        "blocker_count": 2,
        "warning_count": 0,
        "parse_method": "frontmatter",
        "frontmatter": {"name": "demo-skill"},
        "checks": [
            {"id": "B09", "pass": False, "msg": "version field missing"},
            {"id": "B15", "pass": False, "msg": "references/missing.md not found"},
        ],
        "functional_test": {},
        "deep_stage": {},
        "deep_review_context": {"is_new_listing": True},
    })

    recommendations = report.split("## 七、问题与建议", 1)[-1]
    assert "version field missing" not in recommendations
    assert "引用文件缺失或路径无效" in recommendations


def test_batch_b06_does_not_autofix_non_ascii_name():
    raw_name = "AI-Shifu Course Creator（AI 师傅课程创作器）"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "SKILL.md").write_text(
            "---\n"
            f"name: {raw_name}\n"
            "description: Demo skill.\n"
            "version: 1.0.0\n"
            "---\n\nbody\n",
            encoding="utf-8",
        )
        review_result = {
            "frontmatter": {"name": raw_name},
            "checks": [{"id": "B06", "pass": False, "msg": f"name '{raw_name}' 不符合 kebab-case 格式"}],
        }

        classification = batch.classify_blockers(review_result)
        fixes = batch.apply_ai_fixes(root, [{"id": "B06"}], review_result)
        content = (root / "SKILL.md").read_text(encoding="utf-8")

    assert classification["ai_fixable"] == []
    assert classification["needs_human"][0]["id"] == "B06"
    assert fixes == []
    assert f"name: {raw_name}" in content
    assert "ai-shifu-course-creatorai-" not in content


def test_batch_b06_autofixes_ascii_name_only():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "SKILL.md").write_text(
            "---\n"
            "name: Demo Skill_Name!\n"
            "description: Demo skill.\n"
            "version: 1.0.0\n"
            "---\n\nbody\n",
            encoding="utf-8",
        )
        review_result = {
            "frontmatter": {"name": "Demo Skill_Name!"},
            "checks": [{"id": "B06", "pass": False, "msg": "name 'Demo Skill_Name!' 不符合 kebab-case 格式"}],
        }

        classification = batch.classify_blockers(review_result)
        fixes = batch.apply_ai_fixes(root, classification["ai_fixable"], review_result)
        content = (root / "SKILL.md").read_text(encoding="utf-8")

    assert classification["needs_human"] == []
    assert classification["ai_fixable"][0]["id"] == "B06"
    assert fixes == ["B06: name Demo Skill_Name! → demo-skill-name"]
    assert "name: demo-skill-name" in content


if __name__ == "__main__":
    test_functional_stage_pauses_for_missing_config()
    print("OK test_functional_stage_pauses_for_missing_config passed")
    test_functional_stage_pauses_for_unresolved_mcp_or_login_config()
    print("OK test_functional_stage_pauses_for_unresolved_mcp_or_login_config passed")
    test_functional_stage_does_not_pause_for_negated_config_need()
    print("OK test_functional_stage_does_not_pause_for_negated_config_need passed")
    test_functional_stage_ignores_weak_policy_config_words_without_external_evidence()
    print("OK test_functional_stage_ignores_weak_policy_config_words_without_external_evidence passed")
    test_functional_stage_ignores_browser_doc_pattern_and_llm_token_words()
    print("OK test_functional_stage_ignores_browser_doc_pattern_and_llm_token_words passed")
    test_b19_ignores_markdown_decode_terms_and_frontmatter_delimiter()
    print("OK test_b19_ignores_markdown_decode_terms_and_frontmatter_delimiter passed")
    test_b20_ignores_llm_token_consumption_text()
    print("OK test_b20_ignores_llm_token_consumption_text passed")
    test_semantic_verdict_normalizes_configuration_category_alias()
    print("OK test_semantic_verdict_normalizes_configuration_category_alias passed")
    test_autopilot_outputs_strict_next_actions_without_user_ask()
    print("OK test_autopilot_outputs_strict_next_actions_without_user_ask passed")
    test_functional_request_keeps_json_schema_out_of_target_prompt()
    print("OK test_functional_request_keeps_json_schema_out_of_target_prompt passed")
    test_functional_request_increases_subagents_for_complex_skill()
    print("OK test_functional_request_increases_subagents_for_complex_skill passed")
    test_functional_request_does_not_generate_scenarios_from_policy_snippets()
    print("OK test_functional_request_does_not_generate_scenarios_from_policy_snippets passed")
    test_functional_stage_blocks_on_script_executability_failure()
    print("OK test_functional_stage_blocks_on_script_executability_failure passed")
    test_functional_stage_accepts_verdict_when_config_present()
    print("OK test_functional_stage_accepts_verdict_when_config_present passed")
    test_functional_stage_rejects_static_analysis_pass()
    print("OK test_functional_stage_rejects_static_analysis_pass passed")
    test_functional_stage_rejects_test_harness_prompt_leak()
    print("OK test_functional_stage_rejects_test_harness_prompt_leak passed")
    test_functional_stage_skips_workflow_update_explicitly()
    print("OK test_functional_stage_skips_workflow_update_explicitly passed")
    test_review_exemption_recomputes_blockers()
    print("OK test_review_exemption_recomputes_blockers passed")
    test_final_stage_records_functional_skip_reason()
    print("OK test_final_stage_records_functional_skip_reason passed")
    test_deep_stage_rejects_shallow_main_agent_review()
    print("OK test_deep_stage_rejects_shallow_main_agent_review passed")
    test_deep_stage_accepts_subagent_evidence_rich_review()
    print("OK test_deep_stage_accepts_subagent_evidence_rich_review passed")
    test_report_hydrates_final_gate_with_sibling_stage_files()
    print("OK test_report_hydrates_final_gate_with_sibling_stage_files passed")
    test_report_uses_verified_issues_when_provided()
    print("OK test_report_uses_verified_issues_when_provided passed")
    test_report_warns_when_final_gate_lacks_stage_details()
    print("OK test_report_warns_when_final_gate_lacks_stage_details passed")
    test_partner_report_uses_generated_date()
    print("OK test_partner_report_uses_generated_date passed")
    test_partner_report_omits_platform_version_checks_from_recommendations()
    print("OK test_partner_report_omits_platform_version_checks_from_recommendations passed")
    test_batch_b06_does_not_autofix_non_ascii_name()
    print("OK test_batch_b06_does_not_autofix_non_ascii_name passed")
    test_batch_b06_autofixes_ascii_name_only()
    print("OK test_batch_b06_autofixes_ascii_name_only passed")
    print("\nAll workflow regression tests passed!")
