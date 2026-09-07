"""Deterministic structure, portability, and risk prefilter checks."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from common import parse_frontmatter, _get_skill_version
from configuration import detect_configuration_requirements
from log_util import api_request, build_ai_action, log_summary, parse_version_tuple
from metadata import _is_new_upload, _load_source_metadata


VALID_CATEGORIES = [
    "opc-solo-business", "lifestyle-services", "development-tools",
    "website-deployment", "education-learning", "investment-finance",
    "content-creation", "news-information", "productivity-tools",
    "collaboration", "business-operations",
]


# ── 占位符检测 ──────────────────────────────────────

_PLACEHOLDER_PATTERNS = [
    r"\[待翻译\]",
    r"\[to be translated\]",
    r"\[待LLM",
    r"\[to be generated",
    r"\.\.\.\s*\[",            # "... [待翻译]"
    r"^\s*$",                   # 空白
]
_PLACEHOLDER_RE = re.compile("|".join(_PLACEHOLDER_PATTERNS), re.IGNORECASE)


def _is_placeholder(value: str) -> bool:
    """检测 description_zh/en 是否为 normalize 生成的占位值或明显无效值。"""
    if not value or not value.strip():
        return True
    # 以占位符标记结尾
    if _PLACEHOLDER_RE.search(value):
        return True
    # 与 description 完全相同（未翻译）的情况由 B13 处理，此处不重复
    return False


# ── B 检查项实现 ──────────────────────────────────────

def check_b01(skill_dir: Path) -> dict:
    """B01: SKILL.md 存在且非空"""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return {"id": "B01", "pass": False, "msg": "SKILL.md 文件不存在", "auto_fix": False}
    content = skill_md.read_text(encoding="utf-8-sig").strip()
    if len(content) < 10:
        return {"id": "B01", "pass": False, "msg": f"SKILL.md 内容过少（{len(content)} 字符）", "auto_fix": False}
    return {"id": "B01", "pass": True, "msg": "SKILL.md 存在且非空"}


def check_b02(content: str) -> dict:
    """B02: YAML frontmatter 格式有效"""
    fm, body, method = parse_frontmatter(content)
    if fm is None:
        return {"id": "B02", "pass": False, "msg": "无法解析 YAML frontmatter", "auto_fix": False}
    if method == "fallback":
        return {"id": "B02", "pass": True, "msg": "YAML 解析降级到 fallback parser", "warning": True}
    return {"id": "B02", "pass": True, "msg": "YAML frontmatter 格式有效"}


def check_b03(fm: dict) -> dict:
    """B03: description 存在，50-200 字符"""
    desc = str(fm.get("description", ""))
    if not desc:
        return {"id": "B03", "pass": False, "msg": "description 字段缺失", "auto_fix": False}
    length = len(desc)
    if length < 50:
        return {"id": "B03", "pass": True, "msg": f"description 过短（{length} 字符，建议 50-200）", "warning": True,
                "ai_action": build_ai_action("description", "generate",
                    "重写 description（50-200 chars, 描述触发场景和核心功能）",
                    priority="recommended", constraints="50-200 chars", current_value=desc)}
    if length > 200:
        return {"id": "B03", "pass": True, "msg": f"description 过长（{length} 字符）", "warning": True}
    return {"id": "B03", "pass": True, "msg": f"description 有效（{length} 字符）"}


def check_b04(fm: dict) -> dict:
    """B04: description_zh 合规性（条件检查）。

    description_zh 属于平台 Listing 元数据，不强制要求 SKILL.md 提供——
    但若 SKILL.md 已写入该字段，仍要求其内容合法（非空、非占位符、非明显无效）。
    完全缺失时直接 skip，不生成 ai_action。
    """
    val = fm.get("description_zh", None)
    if val is None or (isinstance(val, str) and not val.strip()):
        return {"id": "B04", "pass": True,
                "msg": "未提供 description_zh（属平台 Listing 元数据，SKILL.md 可不写）",
                "skip": True}
    if _is_placeholder(val):
        return {"id": "B04", "pass": True,
                "msg": "SKILL.md 内 description_zh 为占位/无效值，建议清理或更新",
                "warning": True,
                "ai_action": build_ai_action("description_zh", "translate",
                    "SKILL.md 中已写入 description_zh，但内容为占位/无效。"
                    "选择：(a) 撰写真实中文摘要 ≤50字；(b) 整体删除该字段。",
                    priority="recommended",
                    source_field="description", constraints="≤50字，中文",
                    current_value=str(val))}
    return {"id": "B04", "pass": True, "msg": "description_zh 已写入且内容合规"}


def check_b05(fm: dict) -> dict:
    """B05: description_en 合规性（条件检查）。同 B04 语义。"""
    val = fm.get("description_en", None)
    if val is None or (isinstance(val, str) and not val.strip()):
        return {"id": "B05", "pass": True,
                "msg": "未提供 description_en（属平台 Listing 元数据，SKILL.md 可不写）",
                "skip": True}
    if _is_placeholder(val):
        return {"id": "B05", "pass": True,
                "msg": "SKILL.md 内 description_en 为占位/无效值，建议清理或更新",
                "warning": True,
                "ai_action": build_ai_action("description_en", "translate",
                    "SKILL.md 中已写入 description_en，但内容为占位/无效。"
                    "选择：(a) 写入真实英文摘要 ≤120 chars；(b) 整体删除该字段。",
                    priority="recommended",
                    source_field="description", constraints="≤120 chars, English",
                    current_value=str(val))}
    return {"id": "B05", "pass": True, "msg": "description_en 已写入且内容合规"}




def check_b06(fm: dict, dir_name: str) -> dict:
    """B06: name 字段存在且合法（平台模式下不匹配目录名只是 warning）"""
    name = str(fm.get("name", ""))
    if not name:
        return {"id": "B06", "pass": False, "msg": "name 字段缺失", "auto_fix": True}
    if not re.match(r"^[a-z][a-z0-9-]*$", name):
        return {"id": "B06", "pass": False, "msg": f"name '{name}' 不符合 kebab-case 格式", "auto_fix": False}
    # 时间戳形式的目录名（fetch-cache 下 YYYYMMDD-HHMMSS）不参与 name vs dirname 比对
    if re.match(r"^\d{8}-\d{6}$", dir_name):
        return {"id": "B06", "pass": True, "msg": f"name='{name}' 有效（目录名为时间戳，跳过对比）"}
    if name != dir_name:
        return {"id": "B06", "pass": True, "msg": f"name='{name}' 与目录名 '{dir_name}' 不一致（平台模式下不阻断）", "warning": True}
    return {"id": "B06", "pass": True, "msg": f"name='{name}' 有效"}


def _get_skill_version(fm: dict) -> tuple[str, str]:
    """Return version and source, accepting top-level or metadata.version."""
    version = str(fm.get("version", "")).strip().strip("\"'")
    if version:
        return version, "version"
    metadata = fm.get("metadata", {})
    if isinstance(metadata, dict):
        nested = str(metadata.get("version", "")).strip().strip("\"'")
        if nested:
            return nested, "metadata.version"
    return "", ""


def check_b09(fm: dict) -> dict:
    """B09: version 格式合法。平台 publish 要求严格 semver: X.Y.Z。"""
    version, source = _get_skill_version(fm)
    if not version:
        return {"id": "B09", "pass": False, "msg": "version 字段缺失", "auto_fix": True}
    if not re.match(r"^\d+\.\d+\.\d+$", version):
        return {"id": "B09", "pass": False, "msg": f"version '{version}' 格式非法（需 X.Y.Z semver）", "auto_fix": True}
    if source == "metadata.version":
        return {"id": "B09", "pass": True, "msg": f"metadata.version={version} 格式有效"}
    return {"id": "B09", "pass": True, "msg": f"version={version} 格式有效"}


def check_b10(body: str) -> dict:
    """B10: Markdown body 有实质内容"""
    lines = [l for l in body.strip().split("\n") if l.strip()]
    if len(lines) < 3:
        return {"id": "B10", "pass": False, "msg": f"body 仅 {len(lines)} 行，缺少实质内容", "auto_fix": False}
    return {"id": "B10", "pass": True, "msg": f"body 有 {len(lines)} 行实质内容"}


def check_b12(fm: dict, mode: str = "workflow") -> dict:
    """B12: version 递增校验。

    版本号递增属于 fetcher 阶段的确定性职责；reviewer 只做校验，
    不生成 ai_action，不自动修改 SKILL.md。
    """
    if mode == "review-only":
        return {
            "id": "B12",
            "pass": True,
            "msg": "review-only 模式跳过平台版本递增校验",
            "skip": True,
        }
    name = str(fm.get("name", ""))
    version, version_source = _get_skill_version(fm)
    if not name or not version:
        return {"id": "B12", "pass": True, "msg": "无法验证版本递增（缺少 name/version）", "skip": True}
    try:
        resp = api_request("GET", f"/skills?keyword={name}&lifecycle_status=published&page=1&page_size=5")
        items = resp.get("data", {}).get("items") or []
        for item in items:
            if item.get("name") == name:
                published_ver = item.get("version", "")
                pv = parse_version_tuple(published_ver)
                nv = parse_version_tuple(version)
                if pv and nv and nv <= pv:
                    return {
                        "id": "B12",
                        "pass": False,
                        "msg": (
                            f"version {version} ≤ 已发布 {published_ver}；"
                            "版本递增应由 skill-fetcher-v2 在写入 pending-review 前完成，"
                            "请回到 fetcher 阶段重新获取或修复版本源"
                        ),
                        "block_reason": "fetcher_version_gate_failed",
                        "details": {
                            "field": version_source or "version",
                            "current_version": version,
                            "published_version": published_ver,
                        },
                    }
                return {"id": "B12", "pass": True, "msg": f"version {version} > 已发布 {published_ver}"}
        # 平台上无此 skill（新上架）
        return {"id": "B12", "pass": True, "msg": "平台上无已发布版本（新上架）"}
    except RuntimeError:
        return {"id": "B12", "pass": True, "msg": "API 不可用，跳过版本递增检查", "skip": True}


def check_b13(fm: dict) -> dict:
    """B13: 三描述字段一致性（条件检查）。

    description 为 SKILL.md 必备字段；description_zh/en 是平台 Listing 元数据，
    SKILL.md 不强制提供。仅当 SKILL.md 内**已存在但为空**时给 warning，
    完全不存在则视为正常。
    """
    desc = str(fm.get("description", ""))
    desc_zh = fm.get("description_zh", None)
    desc_en = fm.get("description_en", None)
    issues = []
    if not desc:
        issues.append("description（必填）")
    # 只在键存在但值为空字符串时报问题；键不存在直接跳过
    if desc_zh is not None and isinstance(desc_zh, str) and not desc_zh.strip():
        issues.append("description_zh（写入了但值为空）")
    if desc_en is not None and isinstance(desc_en, str) and not desc_en.strip():
        issues.append("description_en（写入了但值为空）")
    if not issues:
        return {"id": "B13", "pass": True,
                "msg": "已存在的描述字段内容齐全（缺失字段属平台 Listing 元数据，SKILL.md 可不写）"}
    return {"id": "B13", "pass": True,
            "msg": f"待整改：{', '.join(issues)}", "warning": True}




def check_b14(fm: dict, body: str) -> dict:
    """B14: allowed-tools 在文档中有说明"""
    tools = str(fm.get("allowed-tools", ""))
    if not tools:
        return {"id": "B14", "pass": True, "msg": "无 allowed-tools 字段（纯 prompt 型）"}
    tool_list = [t.strip() for t in tools.split(",") if t.strip()]
    undocumented = []
    for tool in tool_list:
        if tool.lower() not in body.lower():
            undocumented.append(tool)
    if undocumented:
        return {"id": "B14", "pass": True,
                "msg": f"工具 {undocumented} 在 body 中未见说明", "warning": True,
                "ai_action": build_ai_action("B14_tool_docs", "generate",
                    f"在 body 中补充工具说明: {undocumented}", priority="recommended",
                    context={"missing_tools": undocumented})}
    return {"id": "B14", "pass": True, "msg": "所有 allowed-tools 在 body 中有提及"}


def _b15_strip_markdown_link_paths(body: str) -> str:
    """
    将 markdown 链接 `[text](url)` 中 url 部分替换为占位，避免把
    `[references/](github_url)` 这种含 url 占位/外链的 markdown 链接
    误识别为本地路径引用。
    """
    body = re.sub(r"\[[^\]]*\]\([^)]*\)", "[]( )", body)
    # Mermaid/class diagram node labels such as `[references/foo.md]:::ref`
    # are not Markdown local links and should not be checked as package deps.
    body = re.sub(r"\[[^\]]*(?:references|scripts)/[^\]]+\]:::[A-Za-z0-9_-]+", "[]:::ref", body)
    return body


def _b15_is_template_path(path: str) -> bool:
    """
    路径属于变量/通配符占位时跳过本地文件存在校验。
    覆盖：
      - `<N>-<topic>.md` 这类教学占位（含 `<` 或 `>`）
      - `{domain}.md` 这类 jinja/shell 风格占位（含 `{` 或 `}`）
      - `*.md` `**` 等 glob 通配符（含 `*`）
      - `0X-xxx.md` 这类 Agent 输出占位
      - `01-06.md` 这类范围写法（表示 01 到 06，不是具体文件）
      - 以 `/` 结尾的目标目录示例
    """
    if any(ch in path for ch in ("<", ">", "{", "}", "*")):
        return True
    if path.endswith("/"):
        return True
    if re.search(r"(?:^|/)0X-", path, re.IGNORECASE):
        return True
    if re.search(r"/\d{2}-\d{2}\.md$", path):
        return True
    return False


def _b15_is_generated_output_context(line: str) -> bool:
    """判断引用是否处在“生成目标路径/目录结构示例”上下文，而不是当前包运行依赖。"""
    return any(marker in line for marker in ("[skill目录]/", "<skill目录>/", "{skill目录}/", "├──", "└──", "│   ├──", "写入 ", "维护者", "courseware", "$COURSE_DIR"))


def check_b15(skill_dir: Path, body: str) -> dict:
    """B15: references/scripts 引用无断链。

    跳过场景：
      - markdown 链接 `[text](http(s)://…)` / `[text](git_url)` 中的 url
      - 含 `<…>` `{…}` `*` 通配符的变量/模板路径
    """
    broken = []
    files_to_scan = []
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        files_to_scan.append((skill_md, body))
    for candidate in skill_dir.rglob("SKILL.md"):
        if not candidate.is_file() or candidate == skill_md:
            continue
        try:
            files_to_scan.append((candidate, candidate.read_text(encoding="utf-8-sig", errors="replace")))
        except OSError:
            continue
    # 匹配 references/ 或 scripts/ 开头的路径；在空格、ASCII/中文标点、括号、书名号处截断
    # 截断集含全角括号（）、中文句号。、逗号，、顿号、、分号；、冒号：、书名号《》「」 等，
    # 避免把正文里 `@references/x.md），再命中…` 这类内联引用整段吞成路径。
    ref_pattern = re.compile(
        r"(?<![\w./-])(?:references|scripts)/[^\s\)\"'`\u3002\uff08\uff09\uff0c\u3001\uff1b\uff1a\u300a\u300b\u300c\u300d\uff01\uff1f]+"
    )
    for file_path, file_body in files_to_scan:
        scan_body = _b15_strip_markdown_link_paths(file_body)
        base_dir = file_path.parent
        rel_file = str(file_path.relative_to(skill_dir)).replace("\\", "/")
        for match in ref_pattern.finditer(scan_body):
            ref_path = match.group(0).rstrip(".,;:!?\uff0c\uff1b\uff1a\u3001")
            line_start = scan_body.rfind("\n", 0, match.start()) + 1
            line_end = scan_body.find("\n", match.end())
            if line_end == -1:
                line_end = len(scan_body)
            line = scan_body[line_start:line_end]
            # 变量/通配符/生成目标路径 → 跳过
            if _b15_is_template_path(ref_path) or _b15_is_generated_output_context(line):
                continue
            full_path = base_dir / ref_path
            if not full_path.exists():
                # 尝试去掉尾部可能的中文标点残留后重试
                stripped = ref_path.rstrip("\uff08\uff09\u300a\u300b")
                if stripped != ref_path and (base_dir / stripped).exists():
                    continue
                broken.append(f"{rel_file}:{ref_path}")
    if broken:
        return {"id": "B15", "pass": False, "msg": f"断链引用: {broken}", "auto_fix": False}
    return {"id": "B15", "pass": True, "msg": "引用链接完整"}



def check_b17_source_metadata(skill_dir: Path, skill_name: str, fm: dict, mode: str = "workflow") -> dict:
    """B17: 首次上架必须具备来源渠道与可回溯来源标识。"""
    if mode == "review-only":
        return {
            "id": "B17",
            "pass": True,
            "msg": "纯审查模式跳过首次上架来源元数据检查",
            "skipped": True,
            "scope": "listing_workflow_only",
        }

    source_meta = _load_source_metadata(skill_dir, skill_name, fm)
    is_new = _is_new_upload(skill_name, source_meta)

    source_type = (source_meta.get("source_type") or source_meta.get("data_channel") or "").strip()
    clawhub_slug = (source_meta.get("clawhub_slug") or "").strip()
    skillhub_slug = (source_meta.get("skillhub_slug") or "").strip()
    git_url = (source_meta.get("git_url") or source_meta.get("repo_url") or "").strip()
    generic_slug = (source_meta.get("slug") or "").strip()

    if source_type == "clawhub" and generic_slug and not clawhub_slug:
        clawhub_slug = generic_slug
    if source_type == "skillhub" and generic_slug and not skillhub_slug:
        skillhub_slug = generic_slug

    internal_confirmed = bool(
        source_meta.get("internal_skill")
        or source_meta.get("source_metadata_waived")
        or source_type == "internal"
    )
    has_channel = source_type in {"clawhub", "skillhub", "git"}
    has_locator = bool(clawhub_slug or skillhub_slug or git_url)

    if (is_new is True or is_new is None) and internal_confirmed:
        return {"id": "B17", "pass": True, "msg": "内部 Skill 已显式确认跳过外部来源元数据", "warning": True}

    if is_new is False:
        if has_channel and has_locator:
            return {"id": "B17", "pass": True, "msg": f"版本更新来源可回溯：{source_type}"}
        return {"id": "B17", "pass": True, "msg": "版本更新未检测到完整来源元数据（建议补齐，非阻断）", "warning": True}

    if (is_new is True or is_new is None) and has_channel and has_locator:
        return {"id": "B17", "pass": True, "msg": f"首次上架来源元数据完整：{source_type}"}

    if is_new is True or is_new is None:
        if not has_channel and not has_locator:
            missing_msg = "缺少数据渠道及 clawhub_slug / skillhub_slug / git_url 三选一来源标识"
        elif not has_channel:
            missing_msg = "缺少数据渠道 source_type/data_channel（clawhub|skillhub|git）"
        else:
            missing_msg = "缺少 clawhub_slug / skillhub_slug / git_url 三选一来源标识"
        return {
            "id": "B17",
            "pass": False,
            "msg": f"首次上架来源元数据不完整：{missing_msg}",
            "auto_fix": False,
            "required_fields": {
                "source_type": "clawhub|skillhub|git",
                "one_of": ["clawhub_slug", "skillhub_slug", "git_url"],
            },
        }

    return {"id": "B17", "pass": True, "msg": f"来源元数据完整：{source_type}"}


SECURITY_REVIEW_TEXT_EXTS = {
    ".md", ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".sh",
    ".ps1", ".bat", ".cmd", ".yaml", ".yml", ".toml", ".txt", ".env",
    ".ini", ".cfg",
}


SENSITIVE_CAPABILITY_PATTERNS: list[tuple[str, list[str]]] = [
    ("llm_proxy_interception", [
        r"\bconversation[_-]?sniffer\b",
        r"\b(prompt|conversation|message|chat)[_-]?(proxy|relay|intercept|sniff|capture|rewrite)\b",
        r"\b(?:127\.0\.0\.1|localhost):\d{2,5}\b.{0,120}\b(?:api\.anthropic\.com|api\.openai\.com|proxy|intercept|relay)\b",
        r"\b(?:api\.anthropic\.com|api\.openai\.com)\b.{0,120}\b(?:127\.0\.0\.1|localhost|proxy|intercept|relay)\b",
    ]),
    ("conversation_capture", [
        r"\bconversation[_-]?(sniffer|capture|logger|recorder)\b",
        r"\b(chat|message|prompt)[_-]?(history|transcript|log|capture|recorder)\b",
        r"\btranscript[_-]?(upload|send|sync)\b",
    ]),
    ("device_fingerprint_or_secret_store", [
        r"\benv[_-]?fingerprint\b",
        r"\b(device|machine|hardware)[_-]?(fingerprint|identity)\b",
        r"\bworkspace[_-]?keychain\b",
        r"\bkeychain\b",
        r"\bcredential[_-]?(vault|store|cache)\b",
    ]),
    ("self_modifying_or_forced_update", [
        r"\bself[_-]?(modify|patch|rewrite|update|heal)\b",
        r"\bforced[_-]?rollback\b",
        r"\bwriteFile(?:Sync)?\s*\([^)]*(?:__filename|process\.argv\[1\]|import\.meta\.url)",
    ]),
    ("autonomous_purchase_or_payment", [
        r"\bauto[_-]?buyer\b",
        r"\bmerchant[_-]?agent\b",
        r"\b(auto|agentic|autonomous)[_-]?(buy|purchase|checkout|order|pay)\b",
    ]),
    ("external_telemetry_or_exfiltration", [
        r"\bevomap\.ai\b",
        r"\b(exfil|exfiltrate|uploadLogs|sendDiagnostics|reportToServer|remoteReport)\b",
        r"\b(telemetry|analytics|beacon)[_-]?(endpoint|url|client|sender)\b",
        r"\bnavigator\.sendBeacon\b",
    ]),
]


def _security_evidence(skill_dir: Path, path: Path, line_no: int, line: str) -> dict:
    return {
        "file": str(path.relative_to(skill_dir)).replace("\\", "/"),
        "line": line_no,
        "text": line.strip()[:240],
    }


def _is_doc_or_example_context(path: Path, skill_dir: Path, line: str = "") -> bool:
    """Return true for reference/example material that is not directly executable."""
    rel_parts = [part.lower() for part in path.relative_to(skill_dir).parts]
    if any(part in {"references", "docs", "doc", "examples", "example", "fixtures", "test", "tests"} for part in rel_parts[:-1]):
        return True
    if path.suffix.lower() in {".md", ".mdx", ".txt"} and any(marker in line.lower() for marker in (
        "example", "sample", "placeholder", "your_", "your-", "<token>", "<secret>",
        "bad", "good", "gotcha", "示例", "占位", "例子",
    )):
        return True
    return False


def _is_placeholder_or_public_test_secret(value: str) -> bool:
    lowered = value.lower()
    placeholder_terms = (
        "your", "placeholder", "example", "changeme", "replace_me", "dummy",
        "fake", "test", "abc123", "xxx", "<", "{", "$",
    )
    if any(term in lowered for term in placeholder_terms):
        return True
    # Cloudflare Turnstile public test secret key documented for local testing.
    if re.search(r"1x0{20,}aa", lowered):
        return True
    return False


def _obfuscation_signals(text: str) -> list[str]:
    signals = []
    lines = text.splitlines() or [text]
    if any(len(line) > 1200 for line in lines):
        signals.append("very_long_minified_line")
    if len(re.findall(r"\\x[0-9a-fA-F]{2}|\\u[0-9a-fA-F]{4}", text)) >= 30:
        signals.append("many_hex_or_unicode_escapes")
    if re.search(r"[A-Za-z0-9+/]{240,}={0,2}", text):
        signals.append("large_base64_like_blob")
    decode_terms = len(re.findall(r"\b(?:atob|fromCharCode|Buffer\.from|base64|eval|Function|Invoke-Expression|iex)\b", text, re.IGNORECASE))
    if decode_terms >= 3:
        signals.append("decode_or_dynamic_execution_terms")
    if re.search(r"\b(?:javascript-obfuscator|obfuscate|obfuscated|packed)\b", text, re.IGNORECASE):
        signals.append("explicit_obfuscation_marker")
    return signals


def _first_obfuscation_evidence_line(text: str) -> tuple[int, str]:
    """Return a useful evidence line instead of YAML frontmatter delimiters."""
    signal_re = re.compile(
        r"(\\x[0-9a-fA-F]{2}|\\u[0-9a-fA-F]{4}|[A-Za-z0-9+/]{240,}={0,2}|"
        r"\b(?:atob|fromCharCode|Buffer\.from|base64|eval|Function|Invoke-Expression|iex|"
        r"javascript-obfuscator|obfuscate|obfuscated|packed)\b)",
        re.IGNORECASE,
    )
    fallback = (1, "")
    for line_no, line in enumerate(text.splitlines() or [text], 1):
        stripped = line.strip()
        if stripped and stripped != "---" and not fallback[1]:
            fallback = (line_no, line)
        if signal_re.search(line):
            return line_no, line
    return fallback


def _is_markdown_decode_only_obfuscation(path: Path, signals: list[str]) -> bool:
    return path.suffix.lower() in {".md", ".mdx", ".txt"} and set(signals) == {"decode_or_dynamic_execution_terms"}


def _collect_high_risk_capability_signals(skill_dir: Path) -> dict:
    """Find risky capability combinations that semantic review must not wave through."""
    family_hits: dict[str, list[dict]] = {}
    production_family_hits: dict[str, list[dict]] = {}
    obfuscated_files: list[dict] = []
    production_obfuscated_files: list[dict] = []
    checked_files = 0
    excluded_dirs = {"test", "tests", "__tests__", "spec", "fixtures", "examples", "example", "node_modules", ".git"}

    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or path.name.startswith("_"):
            continue
        if path.suffix.lower() not in SECURITY_REVIEW_TEXT_EXTS:
            continue
        rel_parts = path.relative_to(skill_dir).parts
        if any(part.lower() in excluded_dirs for part in rel_parts[:-1]):
            continue
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except Exception:
            continue
        checked_files += 1

        obfuscation = _obfuscation_signals(text)
        if obfuscation and not _is_markdown_decode_only_obfuscation(path, obfuscation):
            evidence_line_no, evidence_line = _first_obfuscation_evidence_line(text)
            item = {
                "type": "obfuscation_signal",
                "signals": obfuscation[:5],
                "evidence": _security_evidence(skill_dir, path, evidence_line_no, evidence_line),
            }
            obfuscated_files.append(item)
            if not _is_doc_or_example_context(path, skill_dir, evidence_line):
                production_obfuscated_files.append(item)

        for family, patterns in SENSITIVE_CAPABILITY_PATTERNS:
            family_bucket = family_hits.setdefault(family, [])
            for pattern in patterns:
                regex = re.compile(pattern, re.IGNORECASE)
                for line_no, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        evidence = _security_evidence(skill_dir, path, line_no, line)
                        family_bucket.append(evidence)
                        if not _is_doc_or_example_context(path, skill_dir, line):
                            production_family_hits.setdefault(family, []).append(evidence)
                        break
                if len(family_bucket) >= 5:
                    break

    active_families = {family for family, hits in family_hits.items() if hits}
    production_families = {family for family, hits in production_family_hits.items() if hits}
    blockers: list[dict] = []
    warnings: list[dict] = []

    if obfuscated_files:
        warnings.append({
            "type": "obfuscated_or_packed_code",
            "message": f"{len(obfuscated_files)} file(s) contain obfuscation or packing signals.",
            "evidence": obfuscated_files[:5],
        })
    for family in sorted(active_families):
        warnings.append({
            "type": "sensitive_capability_signal",
            "family": family,
            "message": f"Sensitive capability signal detected: {family}.",
            "evidence": family_hits[family][:5],
        })

    has_obfuscation = bool(production_obfuscated_files)
    has_many_obfuscated_files = len(production_obfuscated_files) >= 3
    has_network_or_exfil = bool(production_families & {"llm_proxy_interception", "external_telemetry_or_exfiltration"})
    has_capture = "conversation_capture" in production_families
    has_self_modify = "self_modifying_or_forced_update" in production_families
    has_purchase = "autonomous_purchase_or_payment" in production_families

    if has_many_obfuscated_files and len(production_families) >= 2:
        blockers.append({
            "type": "high_obfuscation_with_sensitive_capabilities",
            "message": "Multiple obfuscated files appear together with sensitive capability signals.",
            "families": sorted(production_families),
            "evidence": production_obfuscated_files[:5],
        })
    if has_obfuscation and len(production_families) >= 4:
        blockers.append({
            "type": "stealth_sensitive_capability_stack",
            "message": "Obfuscation is combined with four or more sensitive capability families.",
            "families": sorted(production_families),
            "evidence": [production_family_hits[f][0] for f in sorted(production_families) if production_family_hits[f]][:8],
        })
    if "llm_proxy_interception" in production_families and (has_capture or "external_telemetry_or_exfiltration" in production_families):
        blockers.append({
            "type": "llm_traffic_interception_or_conversation_exfiltration",
            "message": "LLM traffic proxy/interception signals appear with conversation capture or external reporting.",
            "families": sorted(production_families),
            "evidence": (
                production_family_hits.get("llm_proxy_interception", [])[:3]
                + production_family_hits.get("conversation_capture", [])[:3]
                + production_family_hits.get("external_telemetry_or_exfiltration", [])[:3]
            ),
        })
    if has_self_modify and has_obfuscation:
        blockers.append({
            "type": "obfuscated_self_modifying_behavior",
            "message": "Self-modifying or forced-update behavior appears in an obfuscated package.",
            "families": sorted(production_families),
            "evidence": production_family_hits.get("self_modifying_or_forced_update", [])[:5],
        })
    if has_purchase and has_network_or_exfil:
        blockers.append({
            "type": "autonomous_purchase_with_network_or_reporting",
            "message": "Automatic purchase/payment signals appear with network proxy/reporting capability.",
            "families": sorted(production_families),
            "evidence": production_family_hits.get("autonomous_purchase_or_payment", [])[:5],
        })

    return {
        "checked_files": checked_files,
        "active_families": sorted(active_families),
        "production_families": sorted(production_families),
        "obfuscated_file_count": len(obfuscated_files),
        "production_obfuscated_file_count": len(production_obfuscated_files),
        "blockers": blockers,
        "warnings": warnings,
    }


def check_b19(skill_dir: Path) -> dict:
    """B19: 安全性与通用性（内网域名、凭据硬编码）"""
    issues = []
    text_exts = SECURITY_REVIEW_TEXT_EXTS

    intranet_re = re.compile(r"\b[\w.-]+\.(?:woa\.com|oa\.com)\b")
    credential_re = re.compile(r"(?:password|secret|api_key|token)\s*[:=]\s*['\"][^'\"]{8,}", re.IGNORECASE)

    # 占位符白名单：这些值不是真实凭据
    placeholder_patterns = [
        r"your[_-]?\w*[_-]?here",      # your_token_here, your-key-here
        r"xxx+",                         # xxx, xxxx
        r"placeholder",
        r"example",
        r"(?:your|my|dummy|fake|test)[_-]?(?:token|secret|password|api[_-]?key|key)",
        r"changeme",
        r"TODO",
        r"REPLACE_ME",
        r"<[^>]+>",                      # <your_token>
    ]
    placeholder_re = re.compile("|".join(placeholder_patterns), re.IGNORECASE)

    # 代码表达式白名单：变量引用、函数调用等不是硬编码凭据
    code_expr_patterns = [
        r"^\w+\s*[\(\[]",               # function call: secret('...) or array[
        r"^\w+\s*&&",                    # expression: e && e.message
        r"^\w+\.\w+",                    # property access: e.message
        r"^process\.env",               # env var reference
        r"^\$\{",                        # template literal
        r"^\w+\s*\|\|",                 # fallback: x || y
    ]
    code_expr_re = re.compile("|".join(code_expr_patterns), re.IGNORECASE)

    # 排除目录：test/、tests/、__tests__/、spec/、fixtures/
    excluded_dirs = {"test", "tests", "__tests__", "spec", "fixtures", "examples", "example"}

    for f in skill_dir.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in text_exts:
            continue
        if f.name.startswith("_"):
            continue

        # 排除 test 相关目录
        rel_parts = f.relative_to(skill_dir).parts
        if any(part.lower() in excluded_dirs for part in rel_parts[:-1]):
            continue

        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        rel = str(f.relative_to(skill_dir))

        for m in intranet_re.finditer(content):
            issues.append({"file": rel, "type": "intranet_domain", "match": m.group(0)})
        for m in credential_re.finditer(content):
            matched_text = m.group(0)
            # 检查是否为占位符
            if placeholder_re.search(matched_text):
                continue
            # 提取等号/冒号后的值部分，检查是否为代码表达式
            val_part = re.split(r"[:=]\s*['\"]", matched_text, maxsplit=1)
            if len(val_part) > 1 and code_expr_re.search(val_part[1]):
                continue
            # 如果匹配内容含代码关键字（函数声明、console、return 等），很可能是误报
            if re.search(r"\b(?:function|console|return|throw|require|import|process\.env|module)\b", matched_text):
                continue
            # 如果值过短（去掉尾部代码后 < 8 chars）或含常见代码分隔符，跳过
            if len(val_part) > 1 and len(val_part[1].split(",")[0].strip("'\" ")) < 8:
                continue
            value_part = val_part[1] if len(val_part) > 1 else matched_text
            if _is_placeholder_or_public_test_secret(value_part):
                continue
            issue = {"file": rel, "type": "hardcoded_credential", "match": matched_text[:50]}
            if _is_doc_or_example_context(f, skill_dir, matched_text):
                issue["type"] = "credential_like_example"
                issue["context"] = "documentation_or_example"
            issues.append(issue)

    capability_scan = _collect_high_risk_capability_signals(skill_dir)
    if capability_scan["blockers"]:
        combined_issues = issues + capability_scan["blockers"] + capability_scan["warnings"]
        return {
            "id": "B19",
            "pass": False,
            "msg": (
                f"Found {len(capability_scan['blockers'])} high-risk capability combination(s); "
                "obfuscation, LLM traffic interception, conversation capture, self-modification, "
                "automatic purchase/payment, or external reporting must be resolved before listing."
            ),
            "auto_fix": False,
            "details": combined_issues[:20],
            "capability_scan": capability_scan,
        }
    issues.extend(capability_scan["warnings"])

    if issues:
        blockers = [i for i in issues if i["type"] == "hardcoded_credential"]
        warnings = [i for i in issues if i["type"] != "hardcoded_credential"]
        if not blockers:
            return {"id": "B19", "pass": True,
                    "msg": f"Found {len(warnings)} security signal(s) requiring semantic review.",
                    "warning": True, "details": issues[:10]}
        if blockers:
            return {"id": "B19", "pass": False,
                    "msg": f"发现 {len(blockers)} 个硬编码凭据", "auto_fix": False,
                    "details": issues[:10]}
        return {"id": "B19", "pass": True,
                "msg": f"发现 {len(warnings)} 个内网域名引用（需确认是否有公网替代）",
                "warning": True, "details": issues[:10]}
    return {"id": "B19", "pass": True, "msg": "未发现安全问题"}


def check_b22(skill_dir: Path) -> dict:
    """B22: 营销导流 / 非功能性外跳引导检测。

    脚本只做确定性召回（warning 级，永不直接阻断），命中信号交 LLM 读上下文裁决：
    - 营销导流（引导关注公众号/加群/加私人微信/点赞转发好评/充值付费会员）→ 倾向 blocker
    - 非功能性外跳（引导用户离开 WorkBuddy 去 App/官网/小程序完成本可在内完成的操作）→ 倾向 blocker
    - 功能性跳转（获取 API Key 必须访问官网、下载依赖 CLI、查看官方文档）→ 放行
    边界判定由 LLM 在 deep review 后基于 b22_context.flagged_lines 完成。
    """
    text_exts = {".md", ".txt", ".py", ".js", ".ts", ".json", ".yaml", ".yml"}

    # 营销导流信号（高可疑，与 skill 功能通常无关）
    marketing_re = re.compile(
        r"(关注(我们|公众号|官方)|公众号|扫码(关注|加群|进群|添加)|扫一扫|"
        r"加(我|我的|客服|作者)?(微信|VX|vx|wechat|QQ群|qq群|企业微信)|"
        r"私(信|聊)|点赞|转发|三连|求好评|给(个|我)好评|一键三连|"
        r"领(取)?(红包|福利|优惠|代金券)|限时(优惠|折扣|福利)|充值|"
        r"开通(会员|VIP|vip|超级会员)|付费(会员|订阅|解锁)|赞赏|打赏)",
        re.IGNORECASE,
    )
    # 外跳引导信号（需 LLM 判断是否为功能性跳转）
    redirect_re = re.compile(
        r"(下载(并安装)?.{0,6}(App|APP|客户端|手机端|小程序)|"
        r"前往.{0,8}(App|APP|应用商店|应用市场|App Store|Google Play|小程序)|"
        r"(打开|使用|跳转到?).{0,8}(App|APP|官方客户端|小程序)|"
        r"应用(商店|市场)|App Store|Google Play|"
        r"扫码(下载|安装|体验)|长按识别二维码)",
        re.IGNORECASE,
    )

    marketing_hits, redirect_hits = [], []
    for f in skill_dir.rglob("*"):
        if not f.is_file() or f.suffix not in text_exts:
            continue
        if f.name.startswith("_"):
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = str(f.relative_to(skill_dir))
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("> ", "<!--")):
                continue
            if marketing_re.search(line):
                marketing_hits.append({"file": rel, "line": i, "text": stripped[:120]})
            if redirect_re.search(line):
                redirect_hits.append({"file": rel, "line": i, "text": stripped[:120]})

    total = len(marketing_hits) + len(redirect_hits)
    if total == 0:
        return {"id": "B22", "pass": True, "msg": "未发现营销导流/外跳引导信号"}

    flagged = (marketing_hits + redirect_hits)[:20]
    ai_action = build_ai_action(
        field="B22_drainage_review",
        action_type="review",
        description=(
            "审查命中的营销导流/外跳引导信号，区分【营销导流/非功能性外跳】与【功能性跳转】：\n"
            "- 引导关注公众号/加群/加私人微信/点赞转发好评/充值付费会员、引导跳出 WorkBuddy 去 App/官网/小程序完成本可在对话内完成的操作 → 判定为违规，升级为 BLOCKER，要求删除导流内容后重新 review；\n"
            "- 获取 API Key 必须访问官方控制台、下载运行所需依赖 CLI、查看官方 API 文档等功能性必要跳转 → 标记 false_positive 放行。\n"
            "逐行给出 false_positive / blocker 判定及理由。"
        ),
        priority="required",
        context={
            "flagged_lines": flagged,
            "marketing_count": len(marketing_hits),
            "redirect_count": len(redirect_hits),
        },
    )

    return {
        "id": "B22", "pass": True, "warning": True,
        "msg": f"发现 {len(marketing_hits)} 处营销导流信号、{len(redirect_hits)} 处外跳引导信号（需 LLM 裁决是否为功能性跳转）",
        "details": flagged,
        "ai_action": ai_action,
    }


SCRIPT_LINK_TEXT_EXTS = {
    ".md", ".mdx", ".txt", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".json", ".yaml", ".yml", ".toml", ".sh", ".ps1", ".bat", ".cmd",
    ".env", ".ini", ".cfg",
}
SHORTENER_DOMAINS = {
    "bit.ly", "t.co", "tinyurl.com", "goo.gl", "ow.ly", "buff.ly",
    "is.gd", "cutt.ly", "s.id", "rebrand.ly", "shorturl.at",
}
SCRIPT_LINK_URL_RE = re.compile(r"https?://[^\s`'\"<>)\]}]+", re.IGNORECASE)
PIPE_EXEC_RE = re.compile(
    r"(?:curl|wget|irm|iwr|Invoke-WebRequest|Invoke-RestMethod)\b[^\n|;&]{0,300}\|\s*"
    r"(?:sh|bash|zsh|fish|python|python3|ruby|perl|node|pwsh|powershell|iex|Invoke-Expression)\b",
    re.IGNORECASE,
)
REMOTE_EXEC_RE = re.compile(
    r"(?:eval|exec|Function|Invoke-Expression|iex)\s*\([^)\n]{0,220}"
    r"(?:https?://|requests\.get|urllib\.request|fetch\(|axios\.get|http\.get)",
    re.IGNORECASE,
)
DOWNLOAD_THEN_RUN_RE = re.compile(
    r"(?:curl|wget|Invoke-WebRequest|Invoke-RestMethod|iwr|irm)\b[^\n]{0,220}"
    r"(?:https?://[^\s`'\"<>)]*)[^\n]{0,220}"
    r"(?:&&|;|\n)\s*(?:chmod\s+\+x\s+\S+\s*(?:&&|;)\s*)?"
    r"(?:\.\/|bash\s+|sh\s+|python(?:3)?\s+|node\s+|pwsh\s+|powershell\s+)",
    re.IGNORECASE,
)
ENCODED_EXEC_RE = re.compile(
    r"(?:powershell|pwsh)\b[^\n]{0,120}-(?:enc|encodedcommand)\b|"
    r"base64\s+-(?:d|decode)\b[^\n]{0,160}\|\s*(?:sh|bash|python|node|pwsh|powershell)",
    re.IGNORECASE,
)
INSTALL_FROM_URL_RE = re.compile(
    r"\b(?:pip|pip3|uv\s+pip|npm|pnpm|yarn|bun|go\s+install|cargo\s+install)\b[^\n]{0,220}"
    r"(?:https?://|git\+https?://)",
    re.IGNORECASE,
)


def _line_evidence(skill_dir: Path, path: Path, text: str, match_text: str) -> dict:
    rel = str(path.relative_to(skill_dir)).replace("\\", "/")
    line_no = text[: text.find(match_text)].count("\n") + 1 if match_text in text else ""
    line = ""
    if line_no:
        lines = text.splitlines()
        if 1 <= line_no <= len(lines):
            line = lines[line_no - 1].strip()
    return {"file": rel, "line": line_no, "text": (line or match_text).strip()[:240]}


def validate_script_link_risks(skill_dir: Path) -> dict:
    """Deterministically validate script and external-link risk for every package."""
    blockers: list[dict] = []
    warnings: list[dict] = []
    urls: dict[str, dict] = {}
    checked_files = 0

    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or path.name.startswith("_"):
            continue
        if path.suffix.lower() not in SCRIPT_LINK_TEXT_EXTS:
            continue
        parts = {part.lower() for part in path.relative_to(skill_dir).parts[:-1]}
        if parts & {"__pycache__", "node_modules", ".git", "dist", "build"}:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except Exception as exc:
            warnings.append({
                "type": "script_link_read_error",
                "file": str(path.relative_to(skill_dir)).replace("\\", "/"),
                "message": f"{type(exc).__name__}: {str(exc)[:120]}",
            })
            continue
        checked_files += 1

        for pattern, risk_type, message in [
            (PIPE_EXEC_RE, "remote_pipe_to_interpreter", "Remote content is piped directly into an interpreter."),
            (REMOTE_EXEC_RE, "remote_content_exec_eval", "Remote or fetched content is executed through eval/exec."),
            (DOWNLOAD_THEN_RUN_RE, "download_then_execute", "A remote artifact is downloaded and then executed."),
            (ENCODED_EXEC_RE, "encoded_command_execution", "Encoded command execution is present."),
        ]:
            for match in pattern.finditer(text):
                ev = _line_evidence(skill_dir, path, text, match.group(0))
                blockers.append({"type": risk_type, "message": message, "evidence": ev})

        for match in INSTALL_FROM_URL_RE.finditer(text):
            ev = _line_evidence(skill_dir, path, text, match.group(0))
            warnings.append({
                "type": "dependency_install_from_url",
                "message": "Dependency install references a URL or git URL; verify source, pinning, and necessity.",
                "evidence": ev,
            })

        for line_no, line in enumerate(text.splitlines(), 1):
            for url_match in SCRIPT_LINK_URL_RE.finditer(line):
                raw_url = url_match.group(0).rstrip(".,;:，。；：")
                try:
                    parsed = urlparse(raw_url)
                except ValueError:
                    continue
                if not parsed.netloc:
                    continue
                domain = parsed.netloc.lower().split("@")[-1].split(":")[0]
                item = urls.setdefault(raw_url, {
                    "url": raw_url,
                    "scheme": parsed.scheme.lower(),
                    "domain": domain,
                    "evidence": [],
                })
                if len(item["evidence"]) < 3:
                    item["evidence"].append({
                        "file": str(path.relative_to(skill_dir)).replace("\\", "/"),
                        "line": line_no,
                        "text": line.strip()[:220],
                    })

    for item in urls.values():
        domain = item["domain"]
        if item["scheme"] == "http":
            warnings.append({
                "type": "insecure_http_link",
                "message": "External link uses plain HTTP.",
                "evidence": item["evidence"][0],
                "url": item["url"],
            })
        if domain in SHORTENER_DOMAINS:
            warnings.append({
                "type": "shortened_link",
                "message": "Shortened links hide the final destination and require confirmation.",
                "evidence": item["evidence"][0],
                "url": item["url"],
            })
        if domain in {"raw.githubusercontent.com", "gist.githubusercontent.com"}:
            warnings.append({
                "type": "raw_code_host_link",
                "message": "Raw code-hosting URL found; verify it is not used as an executable install path.",
                "evidence": item["evidence"][0],
                "url": item["url"],
            })

    return {
        "status": "blocked" if blockers else "passed",
        "required": True,
        "checked_files": checked_files,
        "url_count": len(urls),
        "blockers": blockers[:50],
        "warnings": warnings[:80],
        "summary": (
            f"{len(blockers)} blocking script/link risk(s), {len(warnings)} warning(s), "
            f"{len(urls)} URL(s) scanned across {checked_files} file(s)."
        ),
    }


def check_b23_script_link_risk(skill_dir: Path) -> dict:
    """B23: deterministic script and external-link risk validation."""
    validation = validate_script_link_risks(skill_dir)
    if validation["blockers"]:
        return {
            "id": "B23",
            "pass": False,
            "msg": validation["summary"],
            "auto_fix": False,
            "details": validation,
        }
    if validation["warnings"]:
        return {
            "id": "B23",
            "pass": True,
            "warning": True,
            "msg": validation["summary"],
            "details": validation,
        }
    return {"id": "B23", "pass": True, "msg": validation["summary"], "details": validation}


def check_b21(skill_dir: Path) -> dict:
    """B21: 包体大小（v2 阈值 2MB）"""
    total_size = 0
    for f in skill_dir.rglob("*"):
        if f.is_file() and not f.name.startswith("_"):
            total_size += f.stat().st_size

    size_kb = total_size / 1024
    if size_kb > 2048:
        return {"id": "B21", "pass": False, "msg": f"包体 {size_kb:.0f}KB 超过 2MB 限制", "auto_fix": False}
    if size_kb > 500:
        return {"id": "B21", "pass": True, "msg": f"包体 {size_kb:.0f}KB（500KB-2MB，建议优化）", "warning": True}
    return {"id": "B21", "pass": True, "msg": f"包体 {size_kb:.0f}KB"}


# NOTE: display_name / display_name_en 属于平台 Listing 元数据，
# 通过 Operation Platform API 管理，不在 skill 包体 SKILL.md 中，reviewer 不检查。


def check_b20(body: str, skill_dir: Path, fm: dict) -> dict:
    """
    B20: 安装引导 + 环境配置引导验证。
    - 环境配置引导（MCP/API/Token/OAuth）：脚本只做信号召回，最终由 LLM 语义裁决
      SKILL.md 中是否包含充分的配置引导内容（不依赖章节标题命名）。
    - 安装段落引用的文件是否存在（确定性检查）。
    """
    import re as _re

    # ── 第一部分：环境配置引导信号召回（交 LLM 语义裁决，不直接拦截） ──
    compat = str(fm.get("compatibility") or fm.get("compatibility_zh") or fm.get("compatibility_en") or "").strip()
    compat_service_signal_patterns = [
        r"\bmcp\b", r"\bMCP\b", r"\bapi[\s_-]?key\b", r"\btoken\b",
        r"\boauth\b", r"\bauth\b", r"\blogin\b", r"\bcredential",
        r"凭证", r"授权", r"密钥", r"令牌", r"登录",
    ]
    body_service_signal_patterns = [
        r"\bmcp\b", r"\bMCP\b", r"\bapi[\s_-]?key\b",
        r"\b(?:api|auth|access|bearer)[\s_-]?token\b",
        r"\bpersonal\s+access\s+token\b",
        r"\b[A-Z][A-Z0-9_]*TOKEN\b",
        r"\boauth\b", r"\bauth\b", r"\blogin\b", r"\bcredential",
        r"凭证", r"授权", r"密钥", r"令牌", r"登录",
    ]
    # 在 compatibility 字段和 body 中召回外部服务依赖信号；正文中的普通 LLM token 用语不视为认证 token。
    compat_hits = [p for p in compat_service_signal_patterns if _re.search(p, compat)]
    body_hits = [p for p in body_service_signal_patterns if _re.search(p, body)]
    has_service_dep = bool(compat_hits or body_hits)

    b20_ai_action = None
    if has_service_dep:
        # 收集命中信号及其上下文（行号+原文），供 LLM 理解
        signal_evidence = []
        for sig in set(compat_hits + body_hits):
            for i, line in enumerate(body.splitlines(), 1):
                if _re.search(sig, line):
                    signal_evidence.append({"line": i, "text": line.strip()[:120]})
                    if len(signal_evidence) >= 15:
                        break
            if len(signal_evidence) >= 15:
                break
        b20_ai_action = build_ai_action(
            field="B20_config_guide_review",
            action_type="review",
            description=(
                "SKILL.md 中检测到外部服务依赖信号（MCP/API Key/Token/OAuth/凭证等）。"
                "请基于语义判断 SKILL.md 是否包含充分的【环境配置引导】——即用户如何获取凭证、"
                "如何在运行环境中启用服务。注意：配置引导可能分布在任意章节中（如认证机制、"
                "注册流程、绑定流程等），不要求独立「## 环境配置」命名章节。\n"
                "裁决标准：\n"
                "- 配置引导完整（凭证获取+启用方式+验证方式均有覆盖）→ pass\n"
                "- 配置引导部分缺失（如只提了获取方式未提启用）→ warning\n"
                "- 完全缺少配置引导（仅有 compatibility 声明）→ blocker"
            ),
            priority="required",
            context={
                "service_signals_detected": list(set(compat_hits + body_hits)),
                "signal_evidence": signal_evidence[:10],
            },
        )

    # ── 第二部分：原有安装段落检查 ──
    install_patterns = [
        r"##.*安装", r"##.*[Ii]nstall", r"##.*[Ss]etup",
        r"##.*配置", r"##.*[Pp]rerequisites", r"##.*[Gg]etting [Ss]tarted",
        r"##.*环境", r"##.*[Ee]nvironment", r"##.*依赖",
    ]
    has_install_section = any(_re.search(p, body) for p in install_patterns)

    # 检查 allowed-tools 是否含需要环境的工具
    tools = fm.get("allowed-tools", "")
    needs_env = any(t in tools for t in ["Bash", "PowerShell", "Python"])

    def _with_action(result: dict) -> dict:
        """Attach B20 ai_action to any deterministic result."""
        if b20_ai_action:
            result["ai_action"] = b20_ai_action
        return result

    if not has_install_section:
        if needs_env:
            return _with_action({
                "id": "B20", "pass": True, "warning": True,
                "msg": f"使用 {tools} 但无安装/环境配置段落，建议补充前置条件说明",
            })
        return _with_action({"id": "B20", "pass": True, "msg": "无安装段落（纯知识型 skill，正常）"})

    # 有安装段落 → 检查引用的文件/脚本是否存在
    missing = []

    # 检测 body 中引用的脚本/引用路径；跳过变量、范围写法和生成目标路径示例
    scan_body = _b15_strip_markdown_link_paths(body)
    for match in _re.finditer(r"(?:scripts|references)/[\w./-]+", scan_body):
        ref = match.group(0).rstrip(".,;:!?\uff0c\uff1b\uff1a\u3001")
        line_start = scan_body.rfind("\n", 0, match.start()) + 1
        line_end = scan_body.find("\n", match.end())
        if line_end == -1:
            line_end = len(scan_body)
        line = scan_body[line_start:line_end]
        if _b15_is_template_path(ref) or _b15_is_generated_output_context(line):
            continue
        ref_path = skill_dir / ref
        if not ref_path.exists():
            missing.append(ref)

    # 检测常见安装依赖文件引用
    dep_files = {
        "package.json": _re.search(r"npm install|yarn|pnpm", body),
        "requirements.txt": _re.search(r"pip install\s+-r", body),
        "setup.py": _re.search(r"python setup\.py", body),
    }
    for fname, pattern_match in dep_files.items():
        if pattern_match and not (skill_dir / fname).exists():
            missing.append(fname)

    if missing:
        return _with_action({
            "id": "B20", "pass": True, "warning": True,
            "msg": f"安装段落引用的文件不存在: {missing}",
        })

    return _with_action({"id": "B20", "pass": True, "msg": "安装引导完整"})


def check_b24_changelog(body: str) -> dict:
    """
    B24: SKILL.md body 不包含 changelog / release notes。
    SKILL.md 每次调用都加载进上下文，changelog 是纯 token 成本、零执行价值。
    版本历史应归 git commit / 平台 release notes / 独立 CHANGELOG.md。
    检测到时为 blocker（必须移除后才可上架）。
    """
    import re as _re
    changelog_signals = [
        r"(?m)^##\s+v?\d+\.\d+",       # ## v2.6.0 / ## 2.5.0
        r"(?m)^##\s+[Cc]hange",         # ## Changelog / ## Changes
        r"(?m)^##\s+更新",              # ## 更新日志 / ## 更新
        r"(?m)^##\s+版本",              # ## 版本历史
        r"(?mi)^##\s+[Rr]elease",       # ## Release notes
        r"(?m)^\*+\s+v?\d+\.\d+",       # bullet-list version entries
    ]
    for sig in changelog_signals:
        m = _re.search(sig, body)
        if m:
            # 找到匹配行，报告 blocker
            line_text = body.splitlines()
            # 定位行号
            pos = m.start()
            lineno = body[:pos].count("\n") + 1
            snippet = line_text[lineno - 1].strip() if lineno <= len(line_text) else ""
            return {
                "id": "B24", "pass": False,
                "msg": f"SKILL.md body 含 changelog 段落（行 {lineno}: '{snippet}'），"
                       "changelog 是上下文负资产，请移至 git/platform release notes",
                "auto_fix": False,
            }
    return {"id": "B24", "pass": True, "msg": "SKILL.md body 无 changelog 段落"}

# ── 主审查逻辑 ────────────────────────────────────────

def check_p01_portability(skill_dir: Path, body: str) -> dict:
    """P01: structure/portability check for macOS and Windows compatibility."""
    issues = []
    script_dir = skill_dir / "scripts"
    if script_dir.is_dir():
        has_sh = any(p.suffix.lower() == ".sh" for p in script_dir.rglob("*") if p.is_file())
        has_ps1 = any(p.suffix.lower() == ".ps1" for p in script_dir.rglob("*") if p.is_file())
        has_bat = any(p.suffix.lower() in {".bat", ".cmd"} for p in script_dir.rglob("*") if p.is_file())
        if has_sh and not (has_ps1 or has_bat):
            issues.append({"type": "single_platform_script", "detail": "scripts include .sh but no Windows-oriented .ps1/.bat/.cmd alternative"})
        if (has_ps1 or has_bat) and not has_sh:
            issues.append({"type": "single_platform_script", "detail": "scripts include Windows-oriented entrypoints but no .sh alternative"})

    scan_exts = {".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".sh", ".ps1", ".bat", ".cmd"}
    win_abs = re.compile(r"[A-Za-z]:\\\\[^\s`'\"<>]+")
    unix_abs = re.compile(r"(?<![A-Za-z0-9_])/(?:Users|home|var|tmp)/[^\s`'\"<>]+")
    platform_cmds = [
        ("macos_command", re.compile(r"(?m)^\s*open\s+[^-\s]")),
        ("linux_command", re.compile(r"(?m)^\s*xdg-open\s+")),
        ("windows_command", re.compile(r"(?im)\b(?:cmd\s+/c|powershell(?:\.exe)?\s+)")),
    ]
    for f in skill_dir.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in scan_exts:
            continue
        rel = str(f.relative_to(skill_dir)).replace("\\", "/")
        try:
            text = f.read_text(encoding="utf-8-sig", errors="replace")
        except Exception:
            continue
        for m in win_abs.finditer(text):
            issues.append({"type": "hardcoded_windows_path", "file": rel, "match": m.group(0)[:120]})
        for m in unix_abs.finditer(text):
            issues.append({"type": "hardcoded_unix_path", "file": rel, "match": m.group(0)[:120]})
        for issue_type, pattern in platform_cmds:
            if pattern.search(text):
                issues.append({"type": issue_type, "file": rel})
    if issues:
        return {
            "id": "P01",
            "pass": True,
            "warning": True,
            "msg": f"found {len(issues)} portability concern(s) for macOS/Windows compatibility",
            "details": issues[:20],
        }
    return {"id": "P01", "pass": True, "msg": "macOS/Windows portability precheck passed"}


def dedupe_ai_actions(actions: list[dict]) -> list[dict]:
    deduped: dict[str, dict] = {}
    for action in actions:
        if not isinstance(action, dict):
            continue
        key = action.get("action_id") or f"{action.get('field', '')}:{action.get('action_type', '')}:{action.get('priority', '')}"
        deduped[key] = action
    return list(deduped.values())


def dedupe_check_results(results: list[dict]) -> list[dict]:
    deduped: dict[str, dict] = {}
    for result in results:
        if not isinstance(result, dict):
            continue
        key = json.dumps(
            {
                "id": result.get("id", ""),
                "pass": result.get("pass", True),
                "warning": result.get("warning", False),
                "msg": result.get("msg", ""),
                "details": result.get("details", []),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        deduped[key] = result
    return list(deduped.values())


def run_review(skill_dir: Path, skill_name: str = "", mode: str = "workflow") -> dict:
    """执行完整审查，返回结构化结果。"""
    results = []
    ai_actions = []
    warnings = []

    # B01
    b01 = check_b01(skill_dir)
    results.append(b01)
    if not b01["pass"]:
        return {"status": "blocked", "results": results, "blocker_count": 1,
                "ai_actions": [], "summary": "SKILL.md 不存在"}

    # 读取内容
    content = (skill_dir / "SKILL.md").read_text(encoding="utf-8-sig")
    fm, body, parse_method = parse_frontmatter(content)

    # B02
    b02 = check_b02(content)
    results.append(b02)
    if fm is None:
        return {"status": "blocked", "results": results, "blocker_count": 1,
                "ai_actions": [], "summary": "frontmatter 解析失败"}

    # 确定 skill_name
    if not skill_name:
        skill_name = str(fm.get("name", skill_dir.name))
    dir_name = skill_dir.name

    # B03/B06；B04/B05 为条件检查（缺失 skip，存在则查内容合规）
    for check_fn, check_args in [
        (check_b03, (fm,)),
        (check_b04, (fm,)),
        (check_b05, (fm,)),
        (check_b06, (fm, dir_name)),
    ]:
        r = check_fn(*check_args)
        results.append(r)
        if r.get("ai_action"):
            ai_actions.append(r["ai_action"])

    # B09, B10
    results.append(check_b09(fm))
    results.append(check_b10(body))
    # B12 版本递增（workflow 模式 API 查询；review-only 跳过平台流程校验）
    r12 = check_b12(fm, mode=mode)
    results.append(r12)
    if r12.get("ai_action"):
        ai_actions.append(r12["ai_action"])

    # B13 三描述一致性（条件检查：仅在 desc_zh/en 存在时校验）
    results.append(check_b13(fm))



    # B14 allowed-tools 文档
    r14 = check_b14(fm, body)
    results.append(r14)
    if r14.get("ai_action"):
        ai_actions.append(r14["ai_action"])

    # B15 引用链接
    results.append(check_b15(skill_dir, body))

    # B17 首次上架来源元数据：仅 workflow / 上架审查需要阻断；review-only 只记录跳过。
    results.append(check_b17_source_metadata(skill_dir, skill_name, fm, mode=mode))

    # B19 安全性
    results.append(check_b19(skill_dir))

    # B22 营销导流 / 外跳引导
    r22 = check_b22(skill_dir)
    results.append(r22)
    if r22.get("ai_action"):
        ai_actions.append(r22["ai_action"])

    # B23 脚本 / 链接风险验证：更新与新上架都必须执行。
    results.append(check_b23_script_link_risk(skill_dir))

    # B21 包体大小
    results.append(check_b21(skill_dir))

    # B20 安装引导 + 环境配置引导验证
    r_b20 = check_b20(body, skill_dir, fm)
    results.append(r_b20)
    if r_b20.get("ai_action"):
        ai_actions.append(r_b20["ai_action"])

    # B24 changelog 检测（blocker）
    results.append(check_b24_changelog(body))

    results.append(check_p01_portability(skill_dir, body))
    ai_actions = dedupe_ai_actions(ai_actions)
    results = dedupe_check_results(results)

    # 汇总
    ai_actions = dedupe_ai_actions(ai_actions)
    blockers = [r for r in results if not r.get("pass", True)]
    warnings_list = [r for r in results if r.get("warning")]

    # Deep review context
    body_size = len(body.encode("utf-8"))
    source_meta = _load_source_metadata(skill_dir, skill_name, fm)
    configuration_requirements = detect_configuration_requirements(skill_dir)

    # 深度评审仅对「首次上架」执行；版本更新场景跳过（v2.3.0）
    # is_new: True=首次上架, False=版本更新, None=无法确定（保守按需评审执行）
    source_meta = _load_source_metadata(skill_dir, skill_name, fm)
    is_review_only = mode == "review-only"
    # review-only 模式不调用平台 API（避免中文 skill 名 URL 编码问题）
    if is_review_only:
        is_new = None
        is_update = False
    else:
        is_new = _is_new_upload(skill_name, source_meta)
        is_update = is_new is False

    skip_deep_review = body_size < 1024 or is_update
    if body_size < 1024:
        skip_reason = "body_too_small"
    elif is_update:
        skip_reason = "version_update"
    else:
        skip_reason = ""

    status = "passed" if not blockers else "blocked"

    log_summary("review", skill_name, {
        "mode": mode,
        "status": status,
        "blockers": len(blockers),
        "warnings": len(warnings_list),
        "ai_actions": len(ai_actions),
    })

    # Deep Quality Review prompt template (11 dimensions)
    deep_review_prompt = None
    if not skip_deep_review:
        deep_review_prompt = {
            "instructions": "请对以下 skill 进行 11 维度深度质量评审。逐维度打分（1-10）并给出发现和建议。输出 JSON 数组。",
            "dimensions": [
                {"id": "executability", "name": "AI 可执行性", "rubric": "指令是否无歧义、规则有无矛盾、条件分支是否覆盖完整、术语是否一致"},
                {"id": "context_efficiency", "name": "上下文效率", "rubric": "信噪比、是否有冗余重复、版本演进痕迹是否残留、body 是否含对执行无用内容"},
                {"id": "fault_tolerance", "name": "容错与降级", "rubric": "工具不可用时有无降级路径、失败处理是否清晰、常见异常有无指引"},
                {"id": "user_experience", "name": "用户体验", "rubric": "触发词是否自然、首次使用引导是否清晰、参数确认是否高效、错误提示是否友好"},
                {"id": "audience_fit", "name": "受众适配", "rubric": "目标用户技术水平与 skill 要求是否匹配、术语难度是否恰当"},
                {"id": "portability", "name": "可移植性", "rubric": "是否依赖特定 OS、硬编码路径、未声明的工具；Windows/macOS/ACP 沙箱兼容性"},
                {"id": "domain_accuracy", "name": "领域准确性", "rubric": "API/CLI 参数是否准确、引用工具版本是否维护中、领域术语是否正确"},
                {"id": "completeness_boundary", "name": "完整性与边界", "rubric": "description 声称的能力 body 是否覆盖、是否有 when-not-to-use 声明、边界是否清晰"},
                {"id": "consistency", "name": "一致性", "rubric": "frontmatter vs body vs references 是否自洽、配置/URL/版本号是否一致"},
                {"id": "maintainability", "name": "可维护性", "rubric": "结构是否清晰、模块化程度、规则是否去重、更新难度预判"},
                {"id": "evolvability", "name": "演进友好性", "rubric": "新增/删除功能需改几处、架构是否为扩展预留空间"},
            ],
            "output_format": {
                "type": "object",
                "required": [
                    "status",
                    "reviewed_by",
                    "review_method",
                    "source_files_reviewed",
                    "cross_dimension_checks",
                    "dimensions",
                    "summary",
                ],
                "reviewed_by": "subagent|deep_review_subagent|isolated_review_agent",
                "review_method": "subagent_deep_review|isolated_review_agent",
                "dimension_items": {
                    "id": "one of the 11 dimension ids",
                    "rating": "excellent|good|needs_work|blocked",
                    "score": "integer 1-10 aligned to rating",
                    "evidence": "list of at least two concrete observations with file/section/metric references",
                    "rationale": "why the score follows from the evidence",
                    "recommendation": "specific actionable improvement",
                },
            },
            "body_preview": body[:3000] if len(body) > 3000 else body,
            "metadata": {
                "skill_name": skill_name,
                "description": fm.get("description", ""),
                "allowed_tools": fm.get("allowed-tools", ""),
                "version": _get_skill_version(fm)[0],
            },
        }

    return {
        "mode": mode,
        "status": status,
        "skill_name": skill_name,
        "skill_dir": str(skill_dir),
        "parse_method": parse_method,
        "blocker_count": len(blockers),
        "warning_count": len(warnings_list),
        "checks": results,
        "ai_actions": ai_actions,
        "deep_review_context": {
            "skip_deep_review": skip_deep_review,
            "skip_reason": skip_reason,
            "is_new_listing": is_new,
            "body_size_bytes": body_size,
            "body_lines": len(body.strip().split("\n")),
            "has_allowed_tools": bool(fm.get("allowed-tools")),
            "has_references": (skill_dir / "references").is_dir(),
            "has_scripts": (skill_dir / "scripts").is_dir(),
        },
        "deep_review_prompt": deep_review_prompt,
        "configuration_requirements": configuration_requirements,
        "test_recommendation": {
            "level": "skip" if blockers else ("recommended" if (mode == "review-only" or not get_published_version_safe(skill_name)) else "optional"),
        },
        "frontmatter": fm,
    }


STRUCTURE_CHECK_IDS = {"B01", "B02", "B03", "B04", "B05", "B06", "B09", "B10", "B13", "B14", "B15", "B21", "B24", "P01"}
RISK_CHECK_IDS = {"B17", "B19", "B20", "B22", "B23"}

def get_published_version_safe(name: str) -> str:
    """安全获取已发布版本（失败返回空字符串）。"""
    try:
        resp = api_request("GET", f"/skills?keyword={name}&lifecycle_status=published&page=1&page_size=5")
        items = resp.get("data", {}).get("items") or []
        for item in items:
            if item.get("name") == name:
                return item.get("version", "")
    except RuntimeError:
        pass
    return ""
