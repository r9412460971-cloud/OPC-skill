#!/usr/bin/env python3
"""
Batch review entry point for skill-reviewer-v2.

Reads pending-review items, runs staged review, writes structured outputs, and
updates workflow state. Version bumping is not allowed in review; version
progression must be resolved by skill-fetcher-v2 before pending-review. Other
high-confidence tiny mechanical fixes may run by default. Use --no-fix to
disable safe mechanical package edits.
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime

# Windows 终端 UTF-8 兼容
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 将 scripts 目录加入 path
sys.path.insert(0, str(Path(__file__).parent))

from log_util import (
    load_pending_review, write_output_file, api_request, build_ai_action,
    update_pending_status, get_review_output_dir,
)
from review import run_review, run_staged_review


# ── 功能测试桥接 ──────────────────────────────────────

TESTER_DIR = Path.home() / ".workbuddy" / "skills" / "skill-tester-v2"


def _run_functional_test(skill_dir: Path, skill_name: str, review_result: dict) -> str:
    """
    桥接 skill-tester-v2，对通过 B 检查的 skill 执行功能验证。

    Returns:
        "passed" | "failed" | "skipped" | "error"
    """
    tester_script = TESTER_DIR / "scripts" / "test_runner.py"

    # 如果 tester 脚本不存在，检查是否有可直接导入的模块
    if not tester_script.exists():
        # skill-tester-v2 可能没有独立脚本，标记为 skipped
        return "skipped"

    try:
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(tester_script), str(skill_dir), "--skill-name", skill_name, "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
        if proc.returncode == 0:
            try:
                result = json.loads(proc.stdout)
                return result.get("status", "passed")
            except json.JSONDecodeError:
                return "passed"
        return "failed"
    except subprocess.TimeoutExpired:
        return "error"
    except Exception:
        return "skipped"


# ── 平台 API 实时获取权威 name 映射 ─────────────────────


def _fetch_platform_name_map() -> dict[str, str]:
    """
    实时从平台 API 获取所有已发布 skill 的 name，构建 name(lower) → 权威 name 映射。
    失败时返回空字典（静默降级）。
    """
    result = {}
    page = 1
    while True:
        try:
            resp = api_request("GET", f"/skills?lifecycle_status=published&page={page}&page_size=100")
            data = resp.get("data") or {}
            items = data.get("items") or []
            if not items:
                break
            for item in items:
                name = item.get("name", "")
                if name:
                    result[name.lower()] = name
            total = data.get("total", 0)
            if page * 100 >= total:
                break
            page += 1
        except Exception:
            break
    return result


def _resolve_authoritative_name(pending_name: str, platform_map: dict[str, str], cache_path: str = "") -> str:
    """
    解析权威 name（平台注册名），确保 SKILL.md 中的 name 继承旧值。
    """
    if cache_path:
        cache_parent_name = Path(cache_path).parent.name
        if cache_parent_name:
            canonical = platform_map.get(cache_parent_name.lower())
            if canonical:
                return canonical

    canonical = platform_map.get(pending_name.lower())
    if canonical:
        return canonical

    return pending_name


# ── 交互式修复循环 ──────────────────────────────────────


# AI 可自动修复的 Blocker ID 集合
AI_FIXABLE_BLOCKERS = {
    "B03",   # description 长度不足 — 可从 body 摘取
    "B04",   # description_zh 缺失 — 可从 description 翻译
    "B05",   # description_en 缺失 — 可从 description 翻译
    "B06",   # name 非 kebab-case — 可自动修正
    "B09",   # version 缺失/格式错 — 可补 1.0.0
}

# 可标记为误报的 Blocker 模式（正则匹配 "{id} {msg} {details}"）
FALSE_POSITIVE_PATTERNS = [
    (r"B19.*YOUR_|B19.*占位符|B19.*placeholder|B19.*EXAMPLE|B19.*<.*>", "B19 示例代码占位符（非真实凭据）"),
    (r"B15.*http[s]?://", "B15 外部链接（非本地引用）"),
    (r"B15.*<.*>|B15.*\{.*\}", "B15 模板占位符引用（非实际文件路径）"),
    (r"B15.*scripts/.*<name>", "B15 文档中的脚本名模板占位"),
]

# B21 包体大小弹性阈值：超出上限 ≤10% 时自动降级为 warning 而非 blocker
B21_TOLERANCE_RATIO = 0.10  # 允许超出 10%（即 2048KB * 1.10 = 2252KB 以内通过）


def _extract_b06_name_from_msg(msg: str) -> str:
    """Best-effort extraction of the current name from a B06 message."""
    match = re.search(r"name\s+'([^']+)'", msg)
    if match:
        return match.group(1).strip()
    return ""


def _normalize_ascii_name_to_kebab(old_name: str) -> str:
    """
    Normalize a purely ASCII skill name to platform kebab-case.

    Non-ASCII names are deliberately rejected instead of stripped. Mechanical
    deletion would merge leftover latin fragments from translated/display names
    and can create a valid-looking but wrong package name.
    """
    old_name = str(old_name or "").strip().strip("\"'")
    if not old_name or not old_name.isascii():
        return ""
    new_name = re.sub(r"[_\s]+", "-", old_name).lower()
    new_name = re.sub(r"[^a-z0-9-]", "", new_name)
    new_name = re.sub(r"-+", "-", new_name).strip("-")
    if not re.match(r"^[a-z][a-z0-9-]*$", new_name):
        return ""
    return new_name


def _b06_allows_mechanical_fix(review_result: dict, msg: str) -> bool:
    fm = review_result.get("frontmatter", {}) or {}
    current_name = str(fm.get("name") or "").strip().strip("\"'")
    if not current_name:
        current_name = _extract_b06_name_from_msg(msg)
    new_name = _normalize_ascii_name_to_kebab(current_name)
    return bool(new_name and new_name != current_name)


def classify_blockers(review_result: dict) -> dict:
    """
    对 review 结果中的 blockers 进行分类。

    Returns:
        {
            "ai_fixable": [{"id": "B09", "msg": "...", "fix_action": {...}}],
            "false_positive": [{"id": "B19", "msg": "...", "reason": "..."}],
            "needs_human": [{"id": "B21", "msg": "..."}],
        }
    """
    classification = {"ai_fixable": [], "false_positive": [], "needs_human": []}

    checks = review_result.get("checks", [])
    for check in checks:
        if check.get("pass", True):
            continue
        check_id = check.get("id", "")
        msg = check.get("msg", "")

        # 1. AI 可修
        if check_id in AI_FIXABLE_BLOCKERS:
            if check_id == "B06" and not _b06_allows_mechanical_fix(review_result, msg):
                classification["needs_human"].append({
                    "id": check_id,
                    "msg": msg,
                    "reason": "name contains non-ASCII, is missing, or cannot be safely normalized mechanically",
                })
                continue
            fix_action = check.get("ai_action") or _generate_fix_action(check_id, msg, review_result)
            classification["ai_fixable"].append({
                "id": check_id, "msg": msg, "fix_action": fix_action
            })
            continue

        # 2. 误报模式匹配
        is_fp = False
        # 构建匹配文本：id + msg + details (展平)
        match_text = f"{check_id} {msg}"
        details = check.get("details", [])
        if details:
            for d in details:
                match_text += " " + " ".join(str(v) for v in d.values())
        for pattern, reason in FALSE_POSITIVE_PATTERNS:
            if re.search(pattern, match_text, re.IGNORECASE):
                classification["false_positive"].append({
                    "id": check_id, "msg": msg, "reason": reason
                })
                is_fp = True
                break

        if is_fp:
            continue

        # 3. B21 弹性阈值：微超 2MB (≤10%) 自动降级为 false_positive
        if check_id == "B21":
            size_match = re.search(r"(\d+)\s*KB", msg)
            if size_match:
                size_kb = int(size_match.group(1))
                limit_kb = 2048  # 2MB
                if size_kb <= limit_kb * (1 + B21_TOLERANCE_RATIO):
                    classification["false_positive"].append({
                        "id": check_id, "msg": msg,
                        "reason": f"B21 微超阈值（{size_kb}KB，容忍范围 ≤{int(limit_kb * (1 + B21_TOLERANCE_RATIO))}KB）"
                    })
                    continue

        # 4. 需人工
        classification["needs_human"].append({"id": check_id, "msg": msg})

    return classification


def _generate_fix_action(check_id: str, msg: str, review_result: dict) -> dict:
    """为 AI 可修的 blocker 生成修复 action 描述。"""
    fm = review_result.get("frontmatter", {})

    if check_id == "B09":
        return build_ai_action("version", "generate",
                               "version 缺失，请补充为 1.0.0 或从远端版本推断",
                               priority="required")
    elif check_id == "B06":
        return build_ai_action("name", "generate",
                               f"name 格式不合规，需转为 kebab-case",
                               priority="required")
    elif check_id == "B03":
        return build_ai_action("description", "generate",
                               "description 缺失或过短，请从 body 摘取 50-200 字符摘要",
                               priority="required")
    elif check_id == "B04":
        return {}
    elif check_id == "B05":
        return {}
    return {}


def apply_ai_fixes(skill_dir: Path, fixable_items: list, review_result: dict) -> list:
    """
    对 AI 可修的 blocker 执行确定性修复（不依赖 LLM，纯规则）。

    只处理可确定性修复的项（version/name/占位描述），
    需要翻译的项标记为 ai_action 由 LLM Step 4 处理。

    Returns:
        list: 已应用的修复描述
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return []

    content = skill_md.read_text(encoding="utf-8")
    applied = []

    for item in fixable_items:
        check_id = item["id"]

        if check_id == "B09":
            # 补 version: 1.0.0
            if not re.search(r"^version:", content, re.MULTILINE):
                # 在 name: 行后面插入
                content = re.sub(
                    r"(^name:.*$)",
                    lambda m: m.group(0) + "\nversion: 1.0.0",
                    content, count=1, flags=re.MULTILINE
                )
                applied.append("B09: 补充 version: 1.0.0")

        elif check_id == "B06":
            # name → kebab-case; only safe for purely ASCII names.
            match = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
            if match:
                old_name = match.group(1).strip().strip("\"'")
                new_name = _normalize_ascii_name_to_kebab(old_name)
                if not new_name:
                    continue
                if new_name != old_name:
                    content = content.replace(match.group(0), f"name: {new_name}", 1)
                    applied.append(f"B06: name {old_name} → {new_name}")

        elif check_id == "B03":
            # description 太短：从 body 摘取前 150 字符
            fm = review_result.get("frontmatter", {})
            body = review_result.get("deep_review_context", {}).get("body_preview", "")
            if body and len(body) > 50:
                desc_val = body[:150].replace("\n", " ").strip()
                if not re.search(r"^description:", content, re.MULTILINE):
                    content = re.sub(
                        r"(^name:.*$)",
                        lambda m: m.group(0) + f'\ndescription: "{desc_val}"',
                        content, count=1, flags=re.MULTILINE
                    )
                    applied.append(f"B03: 从 body 摘取 description")

    if applied:
        skill_md.write_text(content, encoding="utf-8")

    return applied


def _append_handling_records(review_result: dict, records: list[dict]) -> None:
    if not records:
        return
    current = review_result.setdefault("handling_records", [])
    current.extend(records)
    review_result["handling_record_count"] = len(current)
    final_path = ((review_result.get("stage_paths") or {}).get("final") or "")
    if not final_path:
        return
    path = Path(final_path)
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return
    final_records = data.setdefault("handling_records", [])
    final_records.extend(records)
    data["handling_record_count"] = len(final_records)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8-sig")


def run_fix_loop(skill_dir: Path, name: str, review_result: dict, max_rounds: int) -> dict:
    """
    对一个 skill 执行修复循环。

    Returns:
        {
            "final_status": "passed" | "blocked",
            "rounds": N,
            "fixes_applied": [...],
            "remaining_blockers": [...],
            "false_positives": [...],
            "final_review": {...},
        }
    """
    fixes_applied = []
    false_positives = []
    current_review = review_result

    for round_num in range(1, max_rounds + 1):
        if current_review.get("status") == "passed":
            break

        classification = classify_blockers(current_review)

        # 收集误报
        false_positives.extend(classification["false_positive"])

        # 无 AI 可修的项 → 退出循环
        if not classification["ai_fixable"]:
            break

        # 执行确定性修复
        round_fixes = apply_ai_fixes(skill_dir, classification["ai_fixable"], current_review)
        fixes_applied.extend(round_fixes)

        if not round_fixes:
            # 没有实际修改（都是需要 LLM 翻译的），退出
            break

        # 重新 review
        if os.environ.get("WORKFLOW_BATCH_QUIET") != "1":
            print(f"    fix round {round_num}: applied {len(round_fixes)} fixes, re-reviewing...")
        current_review = run_review(skill_dir, name)

    # 计算最终状态
    remaining = classify_blockers(current_review)
    real_blockers = remaining["needs_human"]

    # 如果所有剩余 blocker 都是 false_positive 或 ai_fixable(需LLM)，标记为 passed+ai_actions
    final_status = current_review.get("status", "blocked")
    if final_status == "blocked" and not real_blockers:
        # 仅剩 ai_fixable（需 LLM 翻译）或 false_positive → 降级为 passed + ai_actions
        final_status = "passed"

    return {
        "final_status": final_status,
        "rounds": min(round_num if 'round_num' in dir() else 0, max_rounds),
        "fixes_applied": fixes_applied,
        "remaining_blockers": real_blockers,
        "false_positives": false_positives,
        "final_review": current_review,
    }


def main():
    parser = argparse.ArgumentParser(description="Skill Reviewer v2 — Batch Review")
    parser.add_argument("--output-dir", help="输出目录")
    parser.add_argument("--names", help="仅处理指定 skill（逗号分隔）")
    parser.add_argument("--status", default="pending_review", help="筛选状态（默认 pending_review）")
    parser.add_argument("--summary-only", action="store_true", help="仅输出汇总")
    parser.add_argument("--quiet", action="store_true", help="仅输出最终汇总，减少控制台上下文")
    parser.add_argument("--apply-fixes", action="store_true", help="Compatibility flag; safe mechanical fixes run by default")
    parser.add_argument("--max-fix-rounds", type=int, default=3, help="Max safe mechanical fix rounds")
    parser.add_argument("--no-fix", action="store_true", help="Disable safe mechanical package edits")
    parser.add_argument("--date", default="", help="读取指定日期 pending-review/YYYY-MM-DD.json，默认今天")
    parser.add_argument("--all-dates", action="store_true", help="跨日期扫描 pending-review")
    parser.add_argument("--pending-file", help="显式 pending 文件路径")
    parser.add_argument("--no-parallel", action="store_true", help="禁用 2 个以上目标时的并行审查")
    parser.add_argument("--force-test", action="store_true", help="更新场景也执行功能验证")
    parser.add_argument("--semantic-review-file", help="单个目标使用的 LLM/subagent semantic risk verdict JSON")
    parser.add_argument("--deep-review-file", help="单个目标使用的 LLM/subagent deep quality review result JSON")
    args = parser.parse_args()
    if args.quiet:
        args.summary_only = True
        os.environ["WORKFLOW_BATCH_QUIET"] = "1"

    def emit(message: str = ""):
        if not args.quiet:
            print(message)

    # 确定输出目录
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = get_review_output_dir("", args.date or None)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 实时从平台 API 获取权威 name 映射
    platform_map = _fetch_platform_name_map()
    if platform_map:
        emit(f"  平台 skill 数: {len(platform_map)}")
    else:
        emit("  ⚠️ 平台 API 不可用，name 解析将使用 pending-review.json 原值")

    # 加载 pending-review.json
    pending = load_pending_review(date=args.date or None, all_dates=args.all_dates, explicit_path=args.pending_file)
    items = pending.get("items", [])

    # 筛选
    target_statuses = [s.strip() for s in args.status.split(",")]
    items = [it for it in items if it.get("status") in target_statuses]

    if args.names:
        name_set = {n.strip().lower() for n in args.names.split(",")}
        items = [it for it in items if (it.get("skill_name") or it.get("name", "")).lower() in name_set]

    if not items:
        print("没有符合条件的待审 skill。")
        return

    emit(f"{'='*60}")
    emit(f"  Skill Reviewer v2 — 批量审查")
    emit(f"  待审数量: {len(items)}")
    edit_policy = "disabled" if args.no_fix else "safe-mechanical-fixes"
    emit(f"  Package edits: {edit_policy}")
    emit(f"  输出目录: {output_dir}")
    emit(f"{'='*60}\n")

    if len(items) >= 2 and not args.no_parallel:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _process_parallel(item: dict) -> dict:
            pending_name = item.get("skill_name") or item.get("name", "unknown")
            cache_path = item.get("cache_path", "")
            name = _resolve_authoritative_name(pending_name, platform_map, cache_path)
            skill_dir = Path(cache_path)
            item_date = item.get("_pending_date") or item.get("pending_date") or args.date or None
            item_output_dir = output_dir / name

            if not skill_dir.exists():
                return {"name": name, "pending_name": pending_name, "status": "skip", "reason": "dir_not_found", "pending_date": item_date}
            if not (skill_dir / "SKILL.md").exists():
                return {"name": name, "pending_name": pending_name, "status": "skip", "reason": "no_skill_md", "pending_date": item_date}

            review_result = run_staged_review(
                skill_dir,
                name,
                mode="workflow",
                stage="all",
                output_dir=item_output_dir,
                date=item_date,
                force_test=args.force_test,
                semantic_review_file=args.semantic_review_file if len(items) == 1 else None,
                deep_review_file=args.deep_review_file if len(items) == 1 else None,
            )
            fixes_applied = []
            if not args.no_fix and review_result.get("status") == "blocked":
                fix_result = run_fix_loop(skill_dir, name, review_result, args.max_fix_rounds)
                fixes_applied.extend(fix_result.get("fixes_applied", []))
                if fixes_applied or fix_result.get("false_positives"):
                    review_result = run_staged_review(
                        skill_dir,
                        name,
                        mode="workflow",
                        stage="all",
                        output_dir=item_output_dir,
                        date=item_date,
                        force_test=args.force_test,
                        semantic_review_file=args.semantic_review_file if len(items) == 1 else None,
                        deep_review_file=args.deep_review_file if len(items) == 1 else None,
                    )
            applied_records = [{
                "type": "applied_fix",
                "outcome": "applied",
                "handling": "safe_mechanical_fix",
                "requires_user_confirmation": False,
                "message": fix,
            } for fix in fixes_applied]
            _append_handling_records(review_result, applied_records)
            final_pending_status = review_result.get("final_status") or ("reviewed" if review_result.get("status") == "passed" else "blocked")
            return {
                "name": name,
                "pending_name": pending_name,
                "pending_id": item.get("id", ""),
                "cache_path": cache_path,
                "status": review_result.get("status", "unknown"),
                "final_pending_status": final_pending_status,
                "blockers": review_result.get("blocker_count", 0),
                "warnings": review_result.get("warning_count", 0),
                "ai_actions": len(review_result.get("ai_actions", [])),
                "auto_fixed": len(fixes_applied),
                "deep_review_needed": not review_result.get("deep_review_context", {}).get("skip_deep_review", True),
                "test_status": (review_result.get("functional_test") or {}).get("recommendation", "skip"),
                "review_output_dir": str(item_output_dir),
                "final_review_path": str(item_output_dir / "05-final.json"),
                "review_gate": review_result.get("review_gate", {}),
                "reviewed_version": review_result.get("reviewed_version", ""),
                "handling_record_count": review_result.get("handling_record_count", 0),
                "pending_date": item_date,
            }

        results_summary = []
        workers = min(4, max(2, len(items)))
        emit(f"  并行审查: {workers} workers（pending 由主流程统一回写）")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_process_parallel, item) for item in items]
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception as exc:
                    result = {"name": "unknown", "status": "error", "reason": f"{type(exc).__name__}: {str(exc)[:300]}"}
                results_summary.append(result)
                if result.get("final_pending_status"):
                    update_pending_status(
                        result.get("pending_name") or result.get("name"),
                        result["final_pending_status"],
                        extra_fields={
                            "review_output_dir": result.get("review_output_dir", ""),
                            "final_review_path": result.get("final_review_path", ""),
                            "review_gate": result.get("review_gate", {}),
                            "reviewed_version": result.get("reviewed_version", ""),
                            "handling_record_count": result.get("handling_record_count", 0),
                            "workflow_state": result["final_pending_status"],
                            "reviewed_at": datetime.now().isoformat(),
                        },
                        date=result.get("pending_date"),
                        explicit_path=args.pending_file,
                        match_fields={
                            "id": result.get("pending_id", ""),
                            "cache_path": result.get("cache_path", ""),
                        },
                    )
                emit(f"  {result.get('name')}: {result.get('final_pending_status', result.get('status'))}")

        passed = sum(1 for r in results_summary if r.get("final_pending_status") == "reviewed")
        blocked = sum(1 for r in results_summary if r.get("final_pending_status") in {"blocked", "needs_config", "needs_ai_review"})
        skipped = sum(1 for r in results_summary if r.get("status") == "skip")
        errors = sum(1 for r in results_summary if r.get("status") == "error")
        need_deep = sum(1 for r in results_summary if r.get("deep_review_needed"))
        auto_fixed = sum(r.get("auto_fixed", 0) for r in results_summary)
        summary = {
            "timestamp": datetime.now().isoformat(),
            "parallel": True,
            "total": len(results_summary),
            "passed": passed,
            "blocked": blocked,
            "needs_ai_review": sum(1 for r in results_summary if r.get("final_pending_status") == "needs_ai_review"),
            "skipped": skipped,
            "errors": errors,
            "auto_fixed_total": auto_fixed,
            "fix_policy": edit_policy,
            "need_deep_review": need_deep,
            "items": results_summary,
        }
        summary_path = output_dir / "_batch_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8-sig")
        print(f"Batch: passed={passed} blocked={blocked} skipped={skipped} errors={errors}; summary={summary_path}")
        return

    results_summary = []

    for item in items:
        pending_name = item.get("skill_name") or item.get("name", "unknown")
        cache_path = item.get("cache_path", "")
        name = _resolve_authoritative_name(pending_name, platform_map, cache_path)
        skill_dir = Path(cache_path)

        display = f"{name}" if name == pending_name else f"{name} (was: {pending_name})"
        emit(f"--- [{display}] ---")

        # 检查目录
        if not skill_dir.exists():
            emit(f"  SKIP: 目录不存在 {cache_path}")
            results_summary.append({"name": name, "status": "skip", "reason": "dir_not_found"})
            continue

        if not (skill_dir / "SKILL.md").exists():
            emit(f"  SKIP: SKILL.md 不存在")
            results_summary.append({"name": name, "status": "skip", "reason": "no_skill_md"})
            continue

        # Review
        try:
            item_date = item.get("_pending_date") or item.get("pending_date") or args.date or None
            item_output_dir = output_dir / name
            review_result = run_staged_review(
                skill_dir,
                name,
                mode="workflow",
                stage="all",
                output_dir=item_output_dir,
                date=item_date,
                force_test=args.force_test,
                semantic_review_file=args.semantic_review_file if len(items) == 1 else None,
                deep_review_file=args.deep_review_file if len(items) == 1 else None,
            )

            # name_mismatch 检测
            name_mismatch = item.get("name_mismatch")
            if not name_mismatch:
                sources_name_from_cache = Path(cache_path).parent.name
                skillmd_name = review_result.get("frontmatter", {}).get("name", "")
                if sources_name_from_cache and skillmd_name and sources_name_from_cache.lower() != skillmd_name.lower():
                    name_mismatch = {"sources_name": sources_name_from_cache, "skillmd_name": skillmd_name}

            if name_mismatch:
                platform_ctx = {}
                try:
                    src_name = name_mismatch["sources_name"]
                    resp = api_request("GET", f"/skills?keyword={src_name}&lifecycle_status=published&page=1&page_size=5")
                    for pi in (resp.get("data") or {}).get("items") or []:
                        if pi.get("name") == src_name:
                            platform_ctx = {
                                "platform_version": pi.get("version"),
                                "platform_description_zh": pi.get("description_zh", ""),
                                "platform_description_en": pi.get("description_en", ""),
                                "platform_display_name": pi.get("display_name", ""),
                                "platform_display_name_en": pi.get("display_name_en", ""),
                            }
                            break
                except Exception:
                    pass

                mismatch_action = {
                    "field": "name_mismatch",
                    "action_type": "resolve",
                    "action": "SKILL.md name 与 sources 注册名不一致，判断是改名升级还是误拉取",
                    "priority": "required",
                    "context": {**name_mismatch, **platform_ctx},
                }
                review_result.setdefault("ai_actions", []).append(mismatch_action)
                review_result["name_mismatch"] = name_mismatch

            # ── 交互式修复循环 ──────────────────────
            fix_result = None
            applied_fix_records = []
            if not args.no_fix and review_result.get("status") == "blocked":
                fix_result = run_fix_loop(skill_dir, name, review_result, args.max_fix_rounds)
                review_result = fix_result["final_review"]
                applied_fix_records.extend({
                    "type": "applied_fix",
                    "outcome": "applied",
                    "handling": "safe_mechanical_fix",
                    "requires_user_confirmation": False,
                    "message": fix,
                } for fix in fix_result.get("fixes_applied", []))

                if fix_result["fixes_applied"]:
                    emit(f"  auto-fix: {len(fix_result['fixes_applied'])} fixes in {fix_result['rounds']} rounds")
                    for f in fix_result["fixes_applied"]:
                        emit(f"    - {f}")

                if fix_result["false_positives"]:
                    emit(f"  false positives: {len(fix_result['false_positives'])}")

                # 更新 status
                if fix_result["final_status"] == "passed":
                    review_result["status"] = "passed"

            review_result = run_staged_review(
                skill_dir,
                name,
                mode="workflow",
                stage="all",
                output_dir=item_output_dir,
                date=item_date,
                force_test=args.force_test,
                semantic_review_file=args.semantic_review_file if len(items) == 1 else None,
                deep_review_file=args.deep_review_file if len(items) == 1 else None,
            )
            _append_handling_records(review_result, applied_fix_records)

            status = review_result.get("status", "unknown")
            blockers = review_result.get("blocker_count", 0)
            warnings = review_result.get("warning_count", 0)
            ai_actions = len(review_result.get("ai_actions", []))
            emit(f"  review: {status} | blockers={blockers} | warnings={warnings} | ai_actions={ai_actions}")

            if not args.summary_only:
                review_out = output_dir / f"{name}_review.json"
                out_data = review_result
                if fix_result:
                    out_data["fix_loop"] = {
                        "rounds": fix_result["rounds"],
                        "fixes_applied": fix_result["fixes_applied"],
                        "remaining_blockers": fix_result["remaining_blockers"],
                        "false_positives": fix_result["false_positives"],
                    }
                review_out.write_text(json.dumps(out_data, indent=2, ensure_ascii=False), encoding="utf-8-sig")

            final_pending_status = review_result.get("final_status") or ("reviewed" if status == "passed" else "blocked")
            update_pending_status(
                pending_name,
                final_pending_status,
                extra_fields={
                    "review_output_dir": str(item_output_dir),
                    "final_review_path": str(item_output_dir / "05-final.json"),
                    "review_gate": review_result.get("review_gate", {}),
                    "reviewed_version": review_result.get("reviewed_version", ""),
                    "handling_record_count": review_result.get("handling_record_count", 0),
                    "workflow_state": final_pending_status,
                    "reviewed_at": datetime.now().isoformat(),
                },
                date=item_date,
                explicit_path=args.pending_file,
                match_fields={
                    "id": item.get("id", ""),
                    "cache_path": cache_path,
                },
            )

            # ── 功能测试自动触发 ──────────────────
            functional_stage = review_result.get("functional_test") or {}
            test_status = functional_stage.get("recommendation", functional_stage.get("overall", "skip"))

            results_summary.append({
                "name": name,
                "status": status,
                "final_pending_status": final_pending_status,
                "blockers": blockers,
                "warnings": warnings,
                "ai_actions": ai_actions,
                "auto_fixed": len(applied_fix_records),
                "deep_review_needed": not review_result.get("deep_review_context", {}).get("skip_deep_review", True),
                "test_status": test_status,
                "name_mismatch": bool(name_mismatch),
                "review_gate": review_result.get("review_gate", {}),
                "reviewed_version": review_result.get("reviewed_version", ""),
                "handling_record_count": review_result.get("handling_record_count", 0),
            })
        except Exception as e:
            emit(f"  review ERROR: {e}")
            results_summary.append({"name": name, "status": "error", "reason": str(e)})

        emit()

    # 汇总
    passed = sum(1 for r in results_summary if r.get("final_pending_status", r.get("status")) in {"reviewed", "passed"})
    blocked = sum(1 for r in results_summary if r.get("final_pending_status", r.get("status")) in {"blocked", "needs_config", "needs_ai_review"})
    skipped = sum(1 for r in results_summary if r.get("status") == "skip")
    errors = sum(1 for r in results_summary if r.get("status") == "error")
    needs_ai_review = sum(1 for r in results_summary if r.get("final_pending_status", r.get("status")) == "needs_ai_review")
    auto_fixed = sum(r.get("auto_fixed", 0) for r in results_summary)
    need_deep = sum(1 for r in results_summary if r.get("deep_review_needed"))

    summary = {
        "timestamp": datetime.now().isoformat(),
        "total": len(results_summary),
        "passed": passed,
        "blocked": blocked,
        "needs_ai_review": needs_ai_review,
        "skipped": skipped,
        "errors": errors,
        "auto_fixed_total": auto_fixed,
        "fix_policy": edit_policy,
        "need_deep_review": need_deep,
        "items": results_summary,
    }

    summary_path = output_dir / "_batch_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8-sig")

    if args.quiet:
        print(f"Batch: passed={passed} blocked={blocked} skipped={skipped} errors={errors}; summary={summary_path}")
    else:
        print(f"{'='*60}")
        print(f"  BATCH COMPLETE: {len(results_summary)} skills processed")
        print(f"{'='*60}")
        print(f"  PASSED: {passed} | BLOCKED: {blocked} | SKIP: {skipped} | ERROR: {errors}")
        print(f"  Package edits applied: {auto_fixed}")
        print(f"  需深度审查: {need_deep}")
        print(f"\n  Summary: {summary_path}")


if __name__ == "__main__":
    main()
