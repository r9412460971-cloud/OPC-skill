"""Human-readable and partner-facing review report generation."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re


DIMENSION_NAMES = {
    "executability": "AI 可执行性",
    "context_efficiency": "上下文效率",
    "fault_tolerance": "容错与降级",
    "user_experience": "用户体验",
    "audience_fit": "受众适配",
    "portability": "可移植性",
    "domain_accuracy": "领域准确性",
    "completeness_boundary": "完整性与边界",
    "consistency": "一致性",
    "maintainability": "可维护性",
    "evolvability": "演进友好性",
    "accuracy": "准确性",
    "completeness": "完整性",
    "clarity": "清晰度",
    "usability": "可用性",
    "error_handling": "错误处理",
    "edge_cases": "边界情况",
    "structure": "结构清晰度",
    "scalability": "扩展性",
    "safety": "安全性",
}

CHECK_NAMES = {
    "B01": "主文件存在性",
    "B02": "frontmatter 格式",
    "B03": "description 长度",
    "B04": "中文描述字段",
    "B05": "英文描述字段",
    "B06": "名称一致性",
    "B09": "版本字段",
    "B10": "正文内容量",
    "B12": "版本递增",
    "B13": "描述一致性",
    "B14": "工具权限说明",
    "B15": "引用文件",
    "B17": "来源元数据",
    "B19": "凭证与敏感信息",
    "B20": "配置说明",
    "B21": "包体大小",
    "B22": "营销导流",
    "B23": "脚本与外链风险",
    "B24": "更新记录",
    "P01": "跨平台兼容",
}

RATING_LABELS = {
    "excellent": "优秀",
    "good": "良好",
    "needs_work": "建议优化",
    "blocked": "需修复",
    "poor": "需修复",
}

STATUS_LABELS = {
    "reviewed": "通过审查",
    "passed": "通过",
    "pass": "通过",
    "blocked": "阻断",
    "needs_config": "等待配置",
    "needs_ai_review": "等待 AI 审查",
    "requires_ai_review": "等待 AI 审查",
    "missing": "待补充审查结果",
    "invalid": "结果格式无效",
    "skipped": "已跳过",
    "skip": "已跳过",
    "warning": "建议关注",
    "warn": "建议关注",
}

PLATFORM_ONLY_CHECK_IDS = {"B09", "B12"}

FIELD_LABELS = {
    "status": "门禁状态",
    "can_upload": "允许上传",
    "blocking_checks": "阻断检查项",
    "warning_checks": "建议关注项",
    "checked_at": "检查时间",
}

STAGE_FILENAMES = {
    "structure": "01-structure.json",
    "risk": "02-risk.json",
    "risk_semantic": "02-risk-semantic-review.json",
    "functional": "03-functional-test.json",
    "functional_result": "03-functional-dialogue-test-result.json",
    "deep": "04-deep-review.json",
    "deep_result": "04-deep-quality-review-result.json",
    "report_verification": "06-report-verification.json",
}


def today_str() -> str:
    return date.today().isoformat()


def _format_report_value(value: object, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        if not value:
            return "无"
        return "、".join(_format_report_value(item, default="") for item in value)
    if isinstance(value, dict):
        if not value:
            return "无"
        return "；".join(f"{k}: {_format_report_value(v, default='')}" for k, v in value.items())
    return str(value)


def _cell(value: object, default: str = "") -> str:
    text = _clean_partner_text(_format_report_value(value, default))
    text = text.replace("\r", " ").replace("\n", "<br>")
    text = text.replace("|", "&#124;")
    return text.strip() or default


def _key_cell(key: str) -> str:
    text = FIELD_LABELS.get(key, key)
    return text.replace("|", "&#124;")


def _clean_partner_text(value: object) -> str:
    text = str(value or "")
    replacements = [
        ("needs_work", "建议优化"),
        ("blocked", "阻断"),
        ("passed", "通过"),
        ("pass", "通过"),
        ("failed", "失败"),
        ("warning", "建议关注"),
        ("warn", "建议关注"),
        ("requires_ai_review", "等待 AI 审查"),
        ("needs_config", "等待配置"),
        ("subagent_dialogue", "子代理对话验证"),
        ("isolated_test_agent", "隔离测试代理"),
        ("subagent_deep_review", "子代理深度评审"),
        ("isolated_review_agent", "隔离评审代理"),
        ("static analysis", "静态分析"),
        ("Core script compiles and", "核心脚本可正常编译，并且"),
        ("The package repeatedly tells users to edit", "包内说明多次要求用户编辑"),
        ("but that file is not included", "但包内未包含该文件"),
        ("Add a real", "建议补充实际的"),
        ("template or change all setup guidance to point to an existing documented config file", "模板，或将配置说明统一指向已存在的配置文件"),
        ("The deterministic portability pass found Windows and Unix path examples that need qualification", "跨平台检查发现文档示例中存在需要区分系统的 Windows/Unix 路径或命令"),
        ("The scripts themselves use pathlib and were runnable on Windows", "脚本实现本身已使用跨平台路径处理，并可在 Windows 上运行"),
        ("Label OS-specific examples clearly and add Windows/macOS equivalents where a command is platform-specific", "建议明确标注系统差异，并为平台相关命令补充 Windows/macOS 对应示例"),
        ("Set required environment variables before functional testing:", "建议在复测前配置环境变量："),
        ("Missing now:", "当前未检测到："),
        ("Create or populate the documented config file(s) before continuing:", "建议在继续复测前补充或填写配置文件："),
        ("the reviewer", "测试流程"),
        ("The reviewer", "测试流程"),
    ]
    for old, new in replacements:
        if re.fullmatch(r"[A-Za-z0-9_ -]+", old):
            text = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(old)}(?![A-Za-z0-9_])", new, text)
        else:
            text = text.replace(old, new)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _status_text(status: object) -> str:
    raw = str(status or "").strip()
    return STATUS_LABELS.get(raw, raw or "未记录")


def _rating_text(rating: object) -> str:
    raw = str(rating or "").strip().lower()
    return RATING_LABELS.get(raw, raw or "未评级")


def _result_mark(check: dict) -> str:
    if not check.get("pass", True):
        return "❌ 阻断"
    if check.get("warning"):
        return "⚠️ 建议关注"
    return "✅ 通过"


def _is_platform_only_check(check: dict) -> bool:
    cid = str(check.get("id") or "")
    msg = str(check.get("msg") or "")
    if cid in PLATFORM_ONLY_CHECK_IDS:
        return True
    return bool(re.search(r"\bversion\b|版本", msg, re.IGNORECASE)) and cid in {"B09", "B12"}


def _is_partner_visible(check: dict) -> bool:
    cid = str(check.get("id") or "")
    text = str(check)
    if _is_platform_only_check(check):
        return False
    if cid in {"B17", "B22"} and "false_positive" in text.lower():
        return False
    if cid == "B19" and re.search(r"your[_-]?api[_-]?key|<your|placeholder|example", text, re.IGNORECASE):
        return False
    return True


def _frontmatter(data: dict) -> dict:
    fm = data.get("frontmatter", {})
    return fm if isinstance(fm, dict) else {}


def _version(data: dict) -> str:
    fm = _frontmatter(data)
    metadata = fm.get("metadata", {}) if isinstance(fm.get("metadata"), dict) else {}
    return str(fm.get("version") or metadata.get("version") or data.get("reviewed_version") or "").strip()


def _package_size(data: dict) -> str:
    for check in data.get("checks", []) or []:
        if isinstance(check, dict) and check.get("id") == "B21":
            return str(check.get("msg", "")).replace("包体 ", "").strip()
    skill_dir = data.get("skill_dir")
    if not skill_dir:
        return ""
    root = Path(skill_dir)
    if not root.exists():
        return ""
    try:
        total = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    except OSError:
        return ""
    if total >= 1024 * 1024:
        return f"{total / 1024 / 1024:.1f}MB"
    return f"{total / 1024:.0f}KB"


def _source_text(data: dict) -> str:
    source_meta = ((data.get("functional_test") or {}).get("source_metadata") or {})
    source = source_meta.get("source") or source_meta.get("source_type") or data.get("source")
    return str(source or "").strip()


def _load_json_file(path: Path) -> dict:
    try:
        if path.exists() and path.is_file():
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def _candidate_output_dirs(data: dict) -> list[Path]:
    candidates: list[Path] = []
    direct_keys = ["review_output_dir", "output_dir"]
    for key in direct_keys:
        value = data.get(key)
        if value:
            candidates.append(Path(str(value)))
    for value in (data.get("stage_paths") or {}).values() if isinstance(data.get("stage_paths"), dict) else []:
        if value:
            candidates.append(Path(str(value)).parent)
    if data.get("final_review_path"):
        candidates.append(Path(str(data.get("final_review_path"))).parent)
    for record in data.get("handling_records", []) or []:
        if not isinstance(record, dict):
            continue
        for key in ["path", "result_file"]:
            value = record.get(key)
            if value:
                candidates.append(Path(str(value)).parent)
    seen: set[str] = set()
    result: list[Path] = []
    for path in candidates:
        try:
            resolved = path.expanduser().resolve()
        except Exception:
            resolved = path
        key = str(resolved).lower()
        if key not in seen and resolved.exists() and resolved.is_dir():
            seen.add(key)
            result.append(resolved)
    return result


def _checks_from_handling_records(data: dict) -> list[dict]:
    checks = []
    for record in data.get("handling_records", []) or []:
        if not isinstance(record, dict) or record.get("type") != "deterministic_check":
            continue
        outcome = str(record.get("outcome") or "").lower()
        checks.append({
            "id": record.get("id", ""),
            "pass": outcome != "blocker",
            "warning": outcome == "warning",
            "msg": record.get("message", ""),
            "from_handling_record": True,
        })
    return checks


def _wrap_submitted_risk(stage: dict, submitted: dict) -> dict:
    if not submitted:
        return stage
    stage = dict(stage or {})
    stage["semantic_review"] = submitted
    status = submitted.get("status")
    if status == "pass":
        stage["status"] = "passed"
    elif status == "blocked":
        stage["status"] = "blocked"
    return stage


def _wrap_submitted_functional(stage: dict, submitted: dict) -> dict:
    if not submitted:
        return stage
    stage = dict(stage or {})
    status = submitted.get("status")
    recommendation = "pass" if status == "pass" else status
    stage.update({
        "status": recommendation,
        "recommendation": recommendation,
        "overall": recommendation,
        "test_executed": status == "pass",
        "result": submitted,
        "summary": submitted.get("summary", stage.get("summary", "")),
        "scenarios": submitted.get("scenarios", []),
    })
    return stage


def _wrap_submitted_deep(stage: dict, submitted: dict) -> dict:
    if not submitted:
        return stage
    stage = dict(stage or {})
    status = submitted.get("status")
    stage["status"] = "passed" if status == "pass" else ("blocked" if status == "blocked" else status or stage.get("status"))
    stage["result"] = submitted
    return stage


def _hydrate_report_data(input_data: dict) -> dict:
    """Merge final-gate JSON with sibling stage verdict/result files before rendering.

    Auto reports are often generated from 05-final.json. That file is a gate
    summary, not enough for a readable report. Hydration recovers 01-04 details
    from sibling files or, as a last resort, deterministic handling records.
    """
    data = dict(input_data or {})
    if data.get("_report_hydrated"):
        return data
    output_dir = None
    for candidate in _candidate_output_dirs(data):
        output_dir = candidate
        break
    if output_dir:
        structure = _load_json_file(output_dir / STAGE_FILENAMES["structure"])
        if structure:
            if not data.get("checks"):
                data["checks"] = structure.get("checks", [])
            if not data.get("frontmatter"):
                data["frontmatter"] = structure.get("frontmatter", {})
        risk = _load_json_file(output_dir / STAGE_FILENAMES["risk"])
        risk_submitted = _load_json_file(output_dir / STAGE_FILENAMES["risk_semantic"])
        if risk or risk_submitted:
            data["risk_stage"] = _wrap_submitted_risk(risk, risk_submitted)
        functional = _load_json_file(output_dir / STAGE_FILENAMES["functional"])
        functional_submitted = _load_json_file(output_dir / STAGE_FILENAMES["functional_result"])
        if functional or functional_submitted:
            data["functional_test"] = _wrap_submitted_functional(functional, functional_submitted)
        deep = _load_json_file(output_dir / STAGE_FILENAMES["deep"])
        deep_submitted = _load_json_file(output_dir / STAGE_FILENAMES["deep_result"])
        if deep or deep_submitted:
            data["deep_stage"] = _wrap_submitted_deep(deep, deep_submitted)
        report_verification = _load_json_file(output_dir / STAGE_FILENAMES["report_verification"])
        if report_verification and not data.get("report_verification"):
            data["report_verification"] = report_verification
        data["_report_output_dir"] = str(output_dir)
    if not data.get("checks"):
        data["checks"] = _checks_from_handling_records(data)
    if not data.get("final_status") and data.get("stage") == "final":
        data["final_status"] = data.get("status")
    data["_report_hydrated"] = True
    data["_report_data_gaps"] = _report_data_gaps(data)
    return data


def _report_data_gaps(data: dict) -> list[str]:
    gaps = []
    if not data.get("checks"):
        gaps.append("结构检查明细缺失")
    risk_stage = data.get("risk_stage") or {}
    if not risk_stage:
        gaps.append("安全风险审查明细缺失")
    functional = data.get("functional_test") or {}
    functional_status = functional.get("recommendation") or functional.get("status") or functional.get("overall") or ((data.get("review_gate") or {}).get("functional"))
    if functional_status == "pass" and not _scenario_rows(functional):
        gaps.append("功能测试场景明细缺失")
    deep_stage = data.get("deep_stage") or {}
    deep_status = deep_stage.get("status") or ((data.get("review_gate") or {}).get("deep_review"))
    if deep_status in {"passed", "pass"} and not _quality_dimensions(data):
        gaps.append("深度质量评审维度明细缺失")
    return gaps


def _report_verification(data: dict) -> dict:
    verification = data.get("report_verification")
    return verification if isinstance(verification, dict) else {}


def _report_verified(data: dict) -> bool:
    verification = _report_verification(data)
    status = str(verification.get("status") or verification.get("recommendation") or "").lower()
    return status in {"verified", "pass", "passed"}


def _verification_issues(data: dict) -> list[dict]:
    verification = _report_verification(data)
    issues = verification.get("issues") or verification.get("verified_issues") or []
    return [item for item in issues if isinstance(item, dict)]


def _safe_sentence(value: object, max_len: int = 140) -> str:
    text = _clean_partner_text(value)
    text = re.sub(r"\b[A-Za-z_]+\b", lambda m: m.group(0), text).strip()
    if len(text) > max_len:
        return text[: max_len - 1].rstrip("，。；;,. ") + "…"
    return text


def _draft_notice(data: dict) -> list[str]:
    if _report_verified(data):
        verification = _report_verification(data)
        reviewer = verification.get("reviewed_by") or verification.get("verifier") or "LLM/人工复核"
        return [f"**报告复核**：已完成问题真实性与严重性复核（{_cell(reviewer)}）。"]
    return [
        "**报告状态**：待复核草稿。当前内容来自结构化审查结果汇总，尚未完成 LLM/人工对问题真实性与严重性的二次复核，不能作为最终对外报告。"
    ]


def _quality_dimensions(data: dict) -> list[dict]:
    result = ((data.get("deep_stage") or {}).get("result") or {})
    dimensions = result.get("dimensions") if isinstance(result, dict) else []
    return [d for d in dimensions or [] if isinstance(d, dict)]


def _quality_average(dimensions: list[dict]) -> float | None:
    scores = []
    for dim in dimensions:
        score = dim.get("score")
        if isinstance(score, int | float):
            scores.append(float(score))
        elif str(score or "").strip().isdigit():
            scores.append(float(str(score).strip()))
    return round(sum(scores) / len(scores), 1) if scores else None


def _quality_grade(avg: float | None, deep_status: str = "") -> str:
    if deep_status == "blocked":
        return "需修复"
    if avg is None:
        return "未完成深度评审"
    if avg >= 9:
        return "优秀"
    if avg >= 7:
        return "良好"
    if avg >= 4:
        return "建议优化"
    return "需修复"


def _risk_status(data: dict) -> str:
    risk_stage = data.get("risk_stage") or {}
    status = risk_stage.get("status") or ((data.get("review_gate") or {}).get("risk"))
    if status in {"passed", "pass"}:
        return "✅ 无高风险"
    if status == "requires_ai_review":
        return "⚠️ 待完成语义风险审查"
    if status == "blocked":
        return "❌ 存在风险阻断项"
    return _status_text(status)


def _functional_status(data: dict) -> str:
    functional = data.get("functional_test") or {}
    status = functional.get("recommendation") or functional.get("status") or functional.get("overall") or ((data.get("review_gate") or {}).get("functional"))
    if status == "pass":
        scenarios = _scenario_rows(functional)
        return f"✅ 场景验证通过（{len(scenarios)} 个场景）" if scenarios else "✅ 场景验证通过"
    if status == "blocked":
        return "❌ 功能验证阻断"
    if status == "needs_config":
        return "⚠️ 需补充配置后验证"
    if status in {"requires_ai_review", "missing"}:
        return "⚠️ 待补充功能测试"
    if status in {"skip", "skipped"}:
        return "已按规则跳过"
    return _status_text(status)


def _visible_checks(data: dict, *, partner: bool) -> list[dict]:
    checks = [c for c in data.get("checks", []) or [] if isinstance(c, dict)]
    if partner:
        checks = [c for c in checks if _is_partner_visible(c)]
    return checks


def _blocking_checks(data: dict, *, partner: bool) -> list[dict]:
    return [c for c in _visible_checks(data, partner=partner) if not c.get("pass", True)]


def _warning_checks(data: dict, *, partner: bool) -> list[dict]:
    return [c for c in _visible_checks(data, partner=partner) if c.get("warning") and c.get("pass", True)]


def _package_tree(data: dict, max_items: int = 18) -> list[str]:
    root_text = data.get("skill_dir") or data.get("skill_name") or "skill"
    root = Path(root_text)
    root_name = root.name if root.name else str(root_text)
    if not root.exists() or not root.is_dir():
        return [f"{root_name}/", "└── 未提供本地包体路径，无法展开目录结构"]
    items = [p for p in sorted(root.iterdir(), key=lambda x: (x.is_file(), x.name.lower())) if not p.name.startswith(".workbuddy")]
    lines = [f"{root_name}/"]
    shown = items[:max_items]
    for idx, path in enumerate(shown):
        branch = "└──" if idx == len(shown) - 1 and len(items) <= max_items else "├──"
        suffix = "/" if path.is_dir() else ""
        note = ""
        if path.name == "SKILL.md":
            note = "    # 主说明文件"
        elif path.name == "README.md":
            note = "    # 使用说明"
        elif path.name == "scripts":
            note = "    # 脚本目录"
        elif path.name == "references":
            note = "    # 参考资料"
        lines.append(f"{branch} {path.name}{suffix}{note}")
    if len(items) > max_items:
        lines.append(f"└── ... 其余 {len(items) - max_items} 项")
    return lines


def _stage_overview_section(data: dict) -> list[str]:
    checks = data.get("checks") or []
    structure_status = "passed" if checks and all(c.get("pass", True) for c in checks if isinstance(c, dict)) else ((data.get("stage_status") or {}).get("structure") or "未记录")
    warning_count = len([c for c in checks if isinstance(c, dict) and c.get("warning")])
    scenarios = _scenario_rows(data.get("functional_test") or {})
    dimensions = _quality_dimensions(data)
    avg = _quality_average(dimensions)
    risk_status = (data.get("risk_stage") or {}).get("status") or ((data.get("review_gate") or {}).get("risk"))
    risk_summary = "未发现高风险" if risk_status in {"passed", "pass"} else "需查看风险结论"
    rows = [
        ("结构与可移植性", structure_status, f"{len(checks)} 项检查，{warning_count} 项建议关注" if checks else "未找到结构检查明细"),
        ("安全与合规风险", risk_status, risk_summary),
        ("功能测试", (data.get("functional_test") or {}).get("recommendation") or (data.get("functional_test") or {}).get("status") or ((data.get("review_gate") or {}).get("functional")), f"{len(scenarios)} 个真实对话场景" if scenarios else "未展开场景或按规则跳过"),
        ("质量评估", (data.get("deep_stage") or {}).get("status") or ((data.get("review_gate") or {}).get("deep_review")), f"均分 {avg}/10，{len(dimensions)} 个维度" if avg is not None else "未找到维度明细"),
        ("最终结论", data.get("final_status") or data.get("status"), "已形成审查结论"),
    ]
    lines = ["## 二、分阶段摘要", "", "| 阶段 | 结果 | 摘要 |", "|------|------|------|"]
    for name, status, summary in rows:
        lines.append(f"| {_cell(name)} | {_cell(_status_text(status))} | {_cell(summary)} |")
    return lines



def _structure_section(data: dict, *, partner: bool) -> list[str]:
    checks = [c for c in _visible_checks(data, partner=partner) if str(c.get("id") or "") in {
        "B01", "B02", "B03", "B04", "B05", "B06", "B10", "B13", "B14", "B15", "B20", "B21", "B24", "P01"
    }]
    blockers = [c for c in checks if not c.get("pass", True)]
    warnings = [c for c in checks if c.get("warning") and c.get("pass", True)]
    lines = ["## 三、结构检查结论", ""]
    if not checks:
        lines.append("未找到结构检查明细。")
        return lines
    lines.extend([
        f"结构检查共 {len(checks)} 项，阻断 {len(blockers)} 项，建议关注 {len(warnings)} 项。",
        "",
    ])
    visible = blockers + warnings
    if not visible:
        lines.append("未发现需要写入报告的结构问题。")
        return lines
    lines.extend(["| 检查项 | 结果 | 结论 |", "|--------|------|------|"])
    for check in visible:
        name = CHECK_NAMES.get(str(check.get("id") or ""), str(check.get("id") or "检查项"))
        lines.append(f"| {_cell(name)} | {_result_mark(check)} | {_cell(_safe_sentence(check.get('msg'), 100))} |")
    return lines


def _semantic_findings(data: dict) -> list[dict]:
    semantic = ((data.get("risk_stage") or {}).get("semantic_review") or {})
    findings = semantic.get("findings") if isinstance(semantic, dict) else []
    return [f for f in findings or [] if isinstance(f, dict)]


def _risk_section(data: dict, *, partner: bool) -> list[str]:
    risk_stage = data.get("risk_stage") or {}
    script_link = risk_stage.get("script_link_validation") or {}
    semantic = risk_stage.get("semantic_review") or {}
    findings = _semantic_findings(data)
    blockers = [f for f in findings if f.get("decision") == "blocker"]
    warnings = [f for f in findings if f.get("decision") == "warning"]
    status = risk_stage.get("status") or ((data.get("review_gate") or {}).get("risk"))
    conclusion = "未发现高风险或阻断性安全问题。" if status in {"passed", "pass"} and not blockers else "存在需进一步处理的风险项。"
    lines = [
        "## 四、安全与风险结论",
        "",
        conclusion,
        "",
        "| 项目 | 结论 |",
        "|------|------|",
        f"| 整体风险 | {_cell(_risk_status(data))} |",
        f"| 阻断风险 | {len(blockers)} 项 |",
        f"| 建议关注 | {len(warnings)} 项 |",
    ]
    if script_link:
        script_status = script_link.get("status")
        lines.append(f"| 脚本/外链 | {_cell(_status_text(script_status))} |")
    if semantic:
        lines.append(f"| 语义风险 | {_cell(_status_text(semantic.get('status')))} |")
    if blockers or warnings:
        lines.extend(["", "### 需关注的风险项", "", "| 类型 | 严重性 | 处理建议 |", "|------|------|------|"])
        for finding in blockers + warnings:
            lines.append(
                f"| {_cell(finding.get('category') or '其他')} | {_cell(finding.get('severity') or '未分级')} | "
                f"{_cell(finding.get('recommendation') or finding.get('summary') or '建议复核后决定是否修正。')} |"
            )
    return lines


def _scenario_rows(functional: dict) -> list[dict]:
    scenarios = functional.get("scenarios")
    if not isinstance(scenarios, list):
        scenarios = ((functional.get("result") or {}).get("scenarios") or [])
    return [s for s in scenarios or [] if isinstance(s, dict)]


def _functional_scope_statement(functional: dict) -> str:
    status = functional.get("recommendation") or functional.get("status") or functional.get("overall")
    result = functional.get("result") if isinstance(functional.get("result"), dict) else {}
    method = str(result.get("execution_method") or "").strip()
    static_only = bool(result.get("static_analysis_only"))
    scenarios = _scenario_rows(functional)
    if status == "pass" and scenarios and method in {"subagent_dialogue", "isolated_test_agent"} and not static_only:
        return "功能测试范围：本轮完成了隔离目标 Skill 会话中的自然用户对话验证。"
    if status == "blocked" and scenarios and method in {"subagent_dialogue", "isolated_test_agent"} and not static_only:
        return "功能测试范围：本轮执行了隔离目标 Skill 会话，失败结论来自实际对话或产物观察。"
    if status == "needs_config":
        return "功能测试范围：本轮停在配置预检阶段，尚未进入完整端到端对话验证。"
    if status in {"requires_ai_review", "missing"} and functional.get("required"):
        return "功能测试范围：本轮已生成对话测试请求，尚未提交完整端到端对话结果。"
    if functional.get("script_executability") and not scenarios:
        return "功能测试范围：本轮仅记录脚本/可执行文件预检，未形成完整端到端对话结论。"
    if functional.get("skipped"):
        return "功能测试范围：本轮按版本更新规则跳过功能对话验证。"
    return ""


def _user_intent_label(text: object) -> str:
    raw = str(text or "").strip()
    if not raw:
        return "未记录"
    ascii_letters = sum(1 for ch in raw if "A" <= ch <= "Z" or "a" <= ch <= "z")
    cjk_chars = sum(1 for ch in raw if "\u4e00" <= ch <= "\u9fff")
    if ascii_letters > 20 and cjk_chars == 0:
        return "英文用户请求"
    return _safe_sentence(raw, 80)


def _functional_section(data: dict) -> list[str]:
    functional = data.get("functional_test") or {}
    scenarios = _scenario_rows(functional)
    status = functional.get("recommendation") or functional.get("status") or functional.get("overall")
    lines = ["## 五、功能测试结论", ""]
    if status == "pass" and scenarios:
        lines.extend([f"本轮覆盖 {len(scenarios)} 个真实用户场景，核心触发与主要路径通过。", ""])
    elif status == "needs_config":
        lines.extend(["完整功能验证需要先补充运行配置。", ""])
    elif functional.get("skipped"):
        lines.extend(["本轮按规则跳过功能对话测试。", ""])
    elif status in {"requires_ai_review", "missing"}:
        lines.extend(["功能测试结果尚未完成，不能输出最终质量结论。", ""])
    if scenarios:
        lines.extend(["| 场景 | 用户意图 | 结果 | 备注 |", "|------|----------|------|------|"])
        for idx, scenario in enumerate(scenarios, 1):
            user_request = scenario.get("user_request") or "未记录"
            note = scenario.get("notes") or ("需关注" if scenario.get("result") == "warn" else "通过")
            lines.append(
                f"| 场景 {idx} | {_cell(_user_intent_label(user_request))} | "
                f"{_cell(_status_text(scenario.get('result')))} | {_cell(_safe_sentence(note, 100))} |"
            )
    elif functional.get("needs_config_instructions"):
        lines.extend(["### 待补充配置", "", "| 配置项 | 说明 |", "|--------|------|"])
        for idx, item in enumerate(functional.get("needs_config_instructions") or [], 1):
            lines.append(f"| {idx} | {_cell(item)} |")
    return lines


def _deep_section(data: dict) -> list[str]:
    deep_stage = data.get("deep_stage") or {}
    result = deep_stage.get("result") or {}
    dimensions = _quality_dimensions(data)
    avg = _quality_average(dimensions)
    lines = ["## 六、质量结论", ""]
    if not dimensions:
        status = deep_stage.get("status")
        lines.append(f"深度质量评审状态：{_status_text(status)}。")
        return lines

    weak = [d for d in dimensions if str(d.get("rating") or "").lower() in {"needs_work", "blocked", "poor"}]
    strong = [d for d in dimensions if str(d.get("rating") or "").lower() in {"excellent", "good"}]
    grade = _quality_grade(avg, deep_stage.get("status"))
    lines.extend([
        f"整体质量：**{grade}**" + (f"（均分 {avg}/10）" if avg is not None else ""),
        f"优势维度：{len(strong)} 项；建议优化维度：{len(weak)} 项。",
        "",
    ])
    if weak:
        lines.extend(["### 重点优化维度", "", "| 维度 | 评分 | 评级 |", "|------|:----:|------|"])
        for dim in weak:
            dim_id = str(dim.get("id") or "")
            name = dim.get("name") or DIMENSION_NAMES.get(dim_id, dim_id.replace("_", " ") or "质量维度")
            lines.append(f"| {_cell(name)} | {_cell(dim.get('score'), '-')} | {_cell(_rating_text(dim.get('rating')))} |")
        lines.extend(["", "具体问题和处理建议见下方“问题与建议”。"])
    else:
        lines.append("未发现需要重点优化的质量维度。")
    return lines


def _problem_from_check(check: dict) -> tuple[str, str, str]:
    cid = str(check.get("id") or "")
    msg = _clean_partner_text(check.get("msg"))
    if cid == "B15":
        return ("引用文件缺失或路径无效", msg, "补齐被引用文件，或删除/修正无效引用路径。")
    if cid == "B20":
        return ("配置说明不完整", msg, "补齐安装、配置、验证步骤，并确保示例配置文件存在。")
    if cid == "P01":
        return ("跨平台说明不足", msg or "存在需要区分系统的路径或命令。", "为 Windows/macOS/Linux 的差异命令增加对应说明。")
    if cid == "B06":
        return ("名称一致性问题", msg, "让包目录、技能名称和发布名称保持易识别的一致关系。")
    if cid == "B19":
        return ("凭证或敏感信息风险", msg, "确认示例不包含真实凭证，并统一使用明显占位符。")
    if cid == "B22":
        return ("营销导流或外跳风险", msg, "移除与核心能力无关的商业引流、外跳或转化引导。")
    if cid == "B23":
        return ("脚本与外链风险", msg, "解释必要性或移除高风险脚本、外链与执行路径。")
    if cid == "B24":
        return ("更新记录缺失", msg, "补充面向用户的变更记录或发布说明。")
    return (CHECK_NAMES.get(cid, "结构规范问题"), msg, "按平台发布规范调整后重新提交。")


def _risk_issue_items(data: dict) -> list[tuple[str, str, str, str]]:
    items = []
    for finding in _semantic_findings(data):
        decision = finding.get("decision")
        if decision not in {"warning", "blocker"}:
            continue
        title = f"语义风险：{finding.get('category') or 'other'}"
        severity = str(finding.get("severity") or "")
        rationale = finding.get("rationale") or finding.get("summary") or ""
        fix = "根据证据移除风险行为、补充边界说明，或提供可审计的必要性解释。"
        priority = "P0" if decision == "blocker" or severity in {"high", "critical"} else "P1"
        items.append((priority, title, _clean_partner_text(rationale), fix))
    return items


def _functional_issue_items(data: dict) -> list[tuple[str, str, str, str]]:
    functional = data.get("functional_test") or {}
    status = functional.get("recommendation") or functional.get("status") or functional.get("overall")
    items = []
    script_check = functional.get("script_executability") or {}
    for result in script_check.get("results", []) or []:
        if not isinstance(result, dict) or result.get("status") not in {"blocked", "warning"}:
            continue
        priority = "P0" if result.get("status") == "blocked" else "P1"
        title = f"脚本预检：{result.get('file') or '未知文件'}"
        fix = "修复脚本语法/编译问题后重新执行功能验证。" if priority == "P0" else "在隔离运行场景中覆盖该脚本，或补充可安全检查的启动方式。"
        items.append((priority, title, _clean_partner_text(result.get("message")), fix))
    if status == "blocked":
        items.append(("P0", "功能场景验证失败", _clean_partner_text(functional.get("summary") or functional.get("reason")), "根据失败场景修复核心流程后重新执行功能测试。"))
    elif status == "needs_config":
        instructions = "；".join(str(x) for x in functional.get("needs_config_instructions") or [])
        items.append(("P1", "功能测试配置未完成", _clean_partner_text(instructions or functional.get("summary")), "补充必要的 API Key、Token、账号登录、MCP 或本地依赖配置后复测。"))
    elif status in {"requires_ai_review", "missing"} and functional.get("required"):
        items.append(("P1", "缺少真实对话功能测试", _clean_partner_text(functional.get("reason")), "补充至少两个真实用户对话场景，并提交可观察的对话证据。"))
    for scenario in _scenario_rows(functional):
        if scenario.get("result") == "warn":
            items.append(("P1", f"功能场景建议关注：{scenario.get('title') or scenario.get('id')}", _clean_partner_text(scenario.get("evidence")), _clean_partner_text(scenario.get("notes") or "结合该场景补充边界说明或交互优化。")))
    return items


def _deep_issue_items(data: dict) -> list[tuple[str, str, str, str]]:
    items = []
    for dim in _quality_dimensions(data):
        rating = str(dim.get("rating") or "").lower()
        if rating not in {"needs_work", "blocked"}:
            continue
        dim_id = str(dim.get("id") or "")
        name = DIMENSION_NAMES.get(dim_id, dim_id.replace("_", " "))
        priority = "P0" if rating == "blocked" else "P1"
        evidence = dim.get("evidence") or dim.get("rationale") or ""
        if isinstance(evidence, list):
            evidence = "；".join(str(x) for x in evidence[:2])
        items.append((priority, name, _clean_partner_text(evidence), _clean_partner_text(dim.get("recommendation") or "结合深评意见优化。")))
    return items


def _recommendation_items(data: dict, *, partner: bool) -> tuple[list[tuple[str, str, str, str]], list[tuple[str, str, str, str]], list[tuple[str, str, str, str]]]:
    p0: list[tuple[str, str, str, str]] = []
    p1: list[tuple[str, str, str, str]] = []
    p2: list[tuple[str, str, str, str]] = []
    for check in _blocking_checks(data, partner=partner):
        problem, detail, fix = _problem_from_check(check)
        p0.append(("P0", problem, detail, fix))
    for check in _warning_checks(data, partner=partner):
        problem, detail, fix = _problem_from_check(check)
        p1.append(("P1", problem, detail, fix))
    for item in _risk_issue_items(data) + _functional_issue_items(data) + _deep_issue_items(data):
        if item[0] == "P0":
            p0.append(item)
        elif item[0] == "P1":
            p1.append(item)
        else:
            p2.append(item)

    seen = set()
    deduped = []
    for item in p0 + p1 + p2:
        key = (item[0], item[1], item[2])
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    p0 = [i for i in deduped if i[0] == "P0"]
    p1 = [i for i in deduped if i[0] == "P1"]
    p2 = [i for i in deduped if i[0] == "P2"]

    if not p2:
        for dim in _quality_dimensions(data):
            rating = str(dim.get("rating") or "").lower()
            recommendation = str(dim.get("recommendation") or "").strip()
            if rating in {"excellent", "good"} and recommendation:
                dim_id = str(dim.get("id") or "")
                name = DIMENSION_NAMES.get(dim_id, dim_id.replace("_", " "))
                p2.append(("P2", name, _clean_partner_text(dim.get("rationale") or ""), _clean_partner_text(recommendation)))
            if len(p2) >= 4:
                break
    return p0, p1, p2


def _recommendations_section(data: dict, *, partner: bool) -> list[str]:
    lines = ["## 七、问题与建议", ""]
    verified_issues = _verification_issues(data)
    if _report_verified(data):
        if not verified_issues:
            lines.append("经复核，本轮未发现需要写入报告的问题。")
            return lines
        lines.extend(["以下问题已完成真实性与严重性复核。", "", "| 优先级 | 问题 | 实际影响 | 建议 |", "|--------|------|----------|------|"])
        for issue in verified_issues:
            priority = issue.get("priority") or issue.get("severity") or "P1"
            title = issue.get("issue") or issue.get("title") or issue.get("problem") or "未命名问题"
            impact = issue.get("impact") or issue.get("actual_impact") or issue.get("evidence") or "已复核"
            fix = issue.get("recommendation") or issue.get("fix") or "建议按复核结论处理。"
            lines.append(f"| {_cell(priority)} | {_cell(title)} | {_cell(_safe_sentence(impact, 120))} | {_cell(_safe_sentence(fix, 120))} |")
        return lines

    p0, p1, _ = _recommendation_items(data, partner=partner)
    draft_items = (p0 + p1)[:6]
    lines.extend([
        "当前仅为待复核问题清单。生成最终报告前，需要 LLM/人工逐条确认问题是否真实存在、影响是否准确、优先级是否合理。",
        "",
    ])
    if not draft_items:
        lines.append("暂无待复核问题。")
        return lines
    lines.extend(["| 初步优先级 | 待复核问题 | 复核要求 |", "|------------|----------|----------|"])
    for priority, problem, _detail, _fix in draft_items:
        lines.append(f"| {_cell(priority)} | {_cell(_safe_sentence(problem, 80))} | 确认问题真实性、实际影响和优先级后，再写入正式报告。 |")
    return lines


def _summary_section(data: dict, *, partner: bool) -> list[str]:
    p0, p1, _ = _recommendation_items(data, partner=partner)
    if _report_verified(data):
        verified = _verification_issues(data)
        p0 = [item for item in verified if str(item.get("priority") or "").upper() == "P0"]
        p1 = [item for item in verified if str(item.get("priority") or "").upper() != "P0"]
    dimensions = _quality_dimensions(data)
    avg = _quality_average(dimensions)
    grade = _quality_grade(avg, (data.get("deep_stage") or {}).get("status", ""))
    final_status = data.get("final_status") or data.get("status")
    quality = f"{grade}（均分 {avg}/10，{len(dimensions)} 维度深度评审）" if avg is not None else grade
    gaps = data.get("_report_data_gaps") or []
    report_status = "已复核" if _report_verified(data) else "待复核草稿"
    lines = [
        "## 一、总体结论",
        "",
        "| 项目 | 结果 |",
        "|------|------|",
        f"| 报告状态 | {report_status} |",
        f"| 整体状态 | {_status_text(final_status)} |",
        f"| 质量评级 | **{quality}** |",
        f"| 安全性 | {_risk_status(data)} |",
        f"| 功能完整性 | {_functional_status(data)} |",
        f"| 必须修复 | {len(p0)} 项 |",
        f"| 建议优化 | {len(p1)} 项 |",
    ]
    if gaps:
        lines.append(f"| 报告完整性 | ⚠️ 数据不完整：{_cell('；'.join(gaps))} |")
    return lines


def _title_block(data: dict, *, partner: bool) -> list[str]:
    skill_name = data.get("skill_name") or "Skill"
    fm = _frontmatter(data)
    lines = [
        f"# {skill_name} 测试报告" if partner else f"# {skill_name} 审查报告",
        "",
        f"**测试时间**：{today_str()}",
        f"**测试对象**：{skill_name}",
    ]
    version = _version(data)
    if version:
        lines.append(f"**Skill 版本**：{version}")
    package_size = _package_size(data)
    if package_size:
        lines.append(f"**包体大小**：{package_size}")
    author = fm.get("author") or fm.get("maintainer")
    if author:
        lines.append(f"**作者**：{_clean_partner_text(author)}")
    source = _source_text(data)
    if source:
        lines.append(f"**来源**：{_clean_partner_text(source)}")
    return lines


def _summarize_ai_action(action: dict) -> str:
    field = str(action.get("field") or "")
    text = str(action.get("action") or action.get("description") or "")
    if field == "B20_config_guide_review":
        return "配置引导需完成语义复核；正文不展开完整审查 prompt。"
    if len(text) > 120:
        return text[:117].rstrip() + "..."
    return text


def _internal_section(data: dict) -> list[str]:
    lines = ["## 八、内部处理记录", ""]
    gate = data.get("review_gate") or {}
    if gate:
        lines.extend(["| 项目 | 值 |", "|------|------|"])
        for key in ["status", "can_upload", "blocking_checks", "warning_checks", "checked_at"]:
            lines.append(f"| {_key_cell(key)} | {_cell(gate.get(key))} |")
        lines.append("")
    actions = data.get("ai_actions") or []
    if actions:
        lines.extend(["### AI Actions", "", "| 字段 | 类型 | 优先级 | 摘要 |", "|------|------|------|------|"])
        for action in actions:
            if not isinstance(action, dict):
                continue
            lines.append(
                f"| {_cell(action.get('field'))} | {_cell(action.get('action_type'))} | "
                f"{_cell(action.get('priority'))} | {_cell(_summarize_ai_action(action))} |"
            )
    else:
        lines.append("本轮未记录待处理的 AI Action。")
    return lines


def _final_summary(data: dict, *, partner: bool) -> list[str]:
    p0, p1, _ = _recommendation_items(data, partner=partner)
    if _report_verified(data):
        verified = _verification_issues(data)
        p0 = [item for item in verified if str(item.get("priority") or "").upper() == "P0"]
        p1 = [item for item in verified if str(item.get("priority") or "").upper() != "P0"]
    dimensions = _quality_dimensions(data)
    avg = _quality_average(dimensions)
    grade = _quality_grade(avg, (data.get("deep_stage") or {}).get("status", ""))
    skill_name = data.get("skill_name") or "该 skill"
    gaps = data.get("_report_data_gaps") or []
    if gaps:
        text = f"{skill_name} 当前报告数据不完整，缺少{'、'.join(gaps)}。请基于完整 review-output 重新生成报告，避免只凭最终门禁摘要下结论。"
    elif not _report_verified(data):
        text = f"{skill_name} 已形成结构化审查草稿，但尚未完成问题真实性与严重性复核。生成正式报告前，应由 LLM/人工逐条确认问题是否真实、影响是否准确、优先级是否合理。"
    elif p0:
        text = f"{skill_name} 已完成本轮结构、风险、功能与深度质量检查。当前主要结论为 {grade}，但仍有 {len(p0)} 项必须修复事项，建议优先处理后再进入发布或交付流程。"
    elif p1:
        text = f"{skill_name} 核心路径整体可用，质量结论为 {grade}。本轮未发现必须修复项，建议同步处理 {len(p1)} 项体验或维护优化，以提升合作交付质量。"
    else:
        text = f"{skill_name} 结构、风险、功能与深度质量表现整体稳定，质量结论为 {grade}。本轮未发现需要合作方处理的阻断或重点优化问题。"
    return ["## 八、总结", "", text]


def _generate_full_report(data: dict, *, partner: bool) -> str:
    data = _hydrate_report_data(data)
    sections: list[list[str]] = [
        _title_block(data, partner=partner),
        _draft_notice(data),
        ["---"],
        _summary_section(data, partner=partner),
        ["---"],
        _stage_overview_section(data),
        ["---"],
        _structure_section(data, partner=partner),
        ["---"],
        _risk_section(data, partner=partner),
        ["---"],
        _functional_section(data),
        ["---"],
        _deep_section(data),
        ["---"],
        _recommendations_section(data, partner=partner),
    ]
    sections.extend([["---"], _final_summary(data, partner=partner)])

    lines: list[str] = []
    for section in sections:
        if lines and lines[-1] != "":
            lines.append("")
        lines.extend(section)
        if lines and lines[-1] != "":
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def generate_report(data: dict) -> str:
    """生成完整 Markdown 审查报告，保留必要的内部处理记录。"""
    return _generate_full_report(data, partner=False)


def generate_partner_test_report(data: dict) -> str:
    """生成面向合作方的完整 Markdown 测试报告。"""
    return _generate_full_report(data, partner=True)
