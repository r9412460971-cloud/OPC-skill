"""Configuration and text inventory helpers used by semantic and functional stages."""

from __future__ import annotations

import os
import re
from pathlib import Path

TEXT_REVIEW_EXTS = {
    ".md", ".mdx", ".txt", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".json", ".yaml", ".yml", ".toml", ".sh", ".ps1", ".bat", ".cmd",
}


def _collect_text_review_inventory(skill_dir: Path, max_file_chars: int = 12000, max_total_chars: int = 180000) -> dict:
    files = []
    total_chars = 0
    truncated = False
    for f in sorted(skill_dir.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in TEXT_REVIEW_EXTS:
            continue
        rel = str(f.relative_to(skill_dir)).replace("\\", "/")
        if any(part.startswith("_") for part in Path(rel).parts):
            continue
        try:
            text = f.read_text(encoding="utf-8-sig", errors="replace")
        except Exception as exc:
            files.append({"path": rel, "read_error": f"{type(exc).__name__}: {str(exc)[:120]}"})
            continue
        remaining = max_total_chars - total_chars
        if remaining <= 0:
            truncated = True
            break
        snippet = text[: min(max_file_chars, remaining)]
        if len(text) > len(snippet):
            truncated = True
        total_chars += len(snippet)
        files.append({
            "path": rel,
            "chars": len(text),
            "content": snippet,
            "truncated": len(text) > len(snippet),
        })
    return {
        "files": files,
        "file_count": len(files),
        "total_included_chars": total_chars,
        "truncated": truncated,
    }


CONFIG_ENV_RE = re.compile(
    r"\b[A-Z][A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|CLIENT[_-]?ID|CLIENT[_-]?SECRET|ACCESS[_-]?KEY|KB[_-]?ID|APP[_-]?ID)\b"
)
CONFIG_NEED_RE = re.compile(
    r"(api\s*key|apikey|token|secret|credential|client[_ -]?id|client[_ -]?secret|"
    r"access[_ -]?key|mcp|login|\bauth\b|oauth|\bpat\b|personal\s+access\s+token|凭证|密钥|令牌|登录|授权|配置)",
    re.IGNORECASE,
)
STRONG_CONFIG_NEED_RE = re.compile(
    r"(api\s*key|apikey|token|secret|credential|client[_ -]?id|client[_ -]?secret|"
    r"access[_ -]?key|oauth|\bpat\b|personal\s+access\s+token|凭证|密钥|令牌)",
    re.IGNORECASE,
)
WEAK_CONFIG_NEED_RE = re.compile(r"(mcp|login|\bauth\b|登录|授权|配置)", re.IGNORECASE)
NON_AUTH_TOKEN_CONTEXT_RE = re.compile(
    r"(token[-\s]*(?:consumption|efficient|efficiency|usage|budget|cost|count|limit)|"
    r"(?:context|prompt|llm|model|unnecessary)\s+tokens?)",
    re.IGNORECASE,
)
AUTH_TOKEN_CONTEXT_RE = re.compile(
    r"(api[_ -]?token|auth[_ -]?token|access[_ -]?token|bearer\s+token|personal\s+access\s+token|\b[A-Z][A-Z0-9_]*TOKEN\b|令牌)",
    re.IGNORECASE,
)
EXPLICIT_SETUP_RE = re.compile(
    r"(before\s+(?:use|running)|must|required\s+to|need\s+to|configure|set\s+up|login\s+to|sign\s+in|"
    r"运行前|使用前|需要[^。\n]*(?:配置|登录|授权|MCP)|必须[^。\n]*(?:配置|登录|授权|MCP))",
    re.IGNORECASE,
)
EXTERNAL_CODE_RE = re.compile(
    r"(^\s*(?:import|from)\s+(?:requests|urllib|http\.client|aiohttp|openai|anthropic|google\.generativeai|boto3|mcp)\b|"
    r"\b(?:requests\.|urllib\.request|urlopen\(|http\.client|fetch\(|axios\.|openai\.|anthropic\.|mcp\.)\b)",
    re.IGNORECASE,
)
CONFIG_NEGATION_RE = re.compile(
    r"(不需要|无需|无须|不依赖|无需配置|"
    r"(does\s+not|do\s+not|doesn't|don't)\s+need\s+(an?\s+)?(api\s*key|token|login|auth|credential|mcp)|"
    r"not\s+require\s+(an?\s+)?(api\s*key|token|login|auth|credential|mcp)|"
    r"no\s+(api\s*key|token|login|auth|credential|mcp)|"
    r"without\s+(an?\s+)?(api\s*key|token|login|auth|credential|mcp))",
    re.IGNORECASE,
)
CONFIG_URL_RE = re.compile(r"https?://[^\s`'\"<>)]+" , re.IGNORECASE)
CODE_SIGNAL_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".sh", ".ps1"}


def _external_code_signals(inventory: dict) -> list[dict]:
    signals = []
    for file_item in inventory.get("files", []):
        rel = file_item.get("path", "")
        if Path(rel).suffix.lower() not in CODE_SIGNAL_EXTS:
            continue
        text = file_item.get("content") or ""
        for line_no, line in enumerate(text.splitlines(), 1):
            if EXTERNAL_CODE_RE.search(line):
                signals.append({"file": rel, "line": line_no, "text": line.strip()[:220]})
                break
        if len(signals) >= 20:
            break
    return signals


def detect_configuration_requirements(skill_dir: Path) -> dict:
    """Detect user-provided configuration needed for complete functional testing."""
    inventory = _collect_text_review_inventory(skill_dir, max_file_chars=20000, max_total_chars=240000)
    env_vars: dict[str, dict] = {}
    config_files: dict[str, dict] = {}
    urls: dict[str, dict] = {}
    signals = []
    unresolved_external_signals = []
    ignored_weak_signals = []
    external_code_signals = _external_code_signals(inventory)
    has_external_code_signal = bool(external_code_signals)

    for file_item in inventory.get("files", []):
        rel = file_item.get("path", "")
        text = file_item.get("content") or ""
        if not text:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if not CONFIG_NEED_RE.search(line) and not CONFIG_ENV_RE.search(line):
                continue
            clean = line.strip()
            if not clean:
                continue
            env_matches = list(CONFIG_ENV_RE.finditer(line))
            cfg_matches = list(re.finditer(r"[\w./~\\-]*config\.(?:json|yaml|yml|toml|env)", line, re.IGNORECASE))
            negated = bool(CONFIG_NEGATION_RE.search(line))
            if negated and not env_matches and not cfg_matches:
                continue
            line_missing_env = False
            line_missing_config = False
            for env_match in env_matches:
                name = env_match.group(0).replace("-", "_")
                configured = bool(os.environ.get(name))
                line_missing_env = line_missing_env or not configured
                env_vars.setdefault(name, {
                    "name": name,
                    "configured": configured,
                    "evidence": {"file": rel, "line": line_no, "text": clean[:220]},
                })
            for cfg_match in cfg_matches:
                cfg = cfg_match.group(0).strip("`'\".,;:，。；：")
                if cfg:
                    cfg_path = Path(cfg).expanduser()
                    if not cfg_path.is_absolute():
                        cfg_path = skill_dir / cfg
                    exists = cfg_path.exists()
                    line_missing_config = line_missing_config or not exists
                    config_files.setdefault(cfg, {
                        "path": cfg,
                        "exists": exists,
                        "evidence": {"file": rel, "line": line_no, "text": clean[:220]},
                    })
            for url_match in CONFIG_URL_RE.finditer(line):
                url = url_match.group(0).rstrip(".,;:，。；：")
                if CONFIG_NEED_RE.search(line):
                    urls.setdefault(url, {
                        "url": url,
                        "evidence": {"file": rel, "line": line_no, "text": clean[:220]},
                    })
            if CONFIG_NEED_RE.search(line):
                if (
                    NON_AUTH_TOKEN_CONTEXT_RE.search(line)
                    and not AUTH_TOKEN_CONTEXT_RE.search(line)
                    and not env_matches
                    and not cfg_matches
                ):
                    ignored_weak_signals.append({"file": rel, "line": line_no, "text": clean[:220]})
                    continue
                signal = {"file": rel, "line": line_no, "text": clean[:220]}
                signals.append(signal)
                strong_signal = bool(STRONG_CONFIG_NEED_RE.search(line))
                weak_signal = bool(WEAK_CONFIG_NEED_RE.search(line))
                has_url = bool(CONFIG_URL_RE.search(line))
                missing_explicit_artifact = line_missing_env or line_missing_config
                should_require = False
                if not negated:
                    if missing_explicit_artifact or strong_signal:
                        should_require = True
                    elif weak_signal and (EXPLICIT_SETUP_RE.search(line) or (has_external_code_signal and has_url)):
                        should_require = True
                if should_require:
                    unresolved_external_signals.append(signal)
                elif weak_signal and not strong_signal and not missing_explicit_artifact:
                    ignored_weak_signals.append(signal)

    missing_env_vars = [item for item in env_vars.values() if not item.get("configured")]
    missing_config_files = [item for item in config_files.values() if not item.get("exists")]
    required = bool(missing_env_vars or missing_config_files or unresolved_external_signals)
    instructions = []
    if env_vars:
        names = ", ".join(sorted(env_vars))
        missing = ", ".join(sorted(item["name"] for item in missing_env_vars)) or "none"
        instructions.append(f"Set required environment variables before functional testing: {names}. Missing now: {missing}.")
    if missing_config_files:
        cfgs = ", ".join(sorted(item["path"] for item in missing_config_files))
        instructions.append(f"Create or populate the documented config file(s) before continuing: {cfgs}.")
    if urls:
        instructions.append("Use the official setup/console URL(s) referenced by the skill to obtain credentials, then rerun the functional stage.")
    if unresolved_external_signals and not instructions:
        instructions.append("Complete the documented login/auth/MCP/account setup, then rerun the functional stage.")

    notes = []
    if ignored_weak_signals and not has_external_code_signal:
        notes.append(
            "Weak config words such as MCP/login/auth/config were seen in docs, but no external-service code or explicit credential/config artifact was found; they were not treated as blocking config requirements."
        )
    elif ignored_weak_signals:
        notes.append(
            "Some weak config words were recorded as non-blocking because they lacked explicit missing credential/config evidence."
        )

    return {
        "required_for_complete_functional_test": required,
        "has_external_service_signals": bool(unresolved_external_signals or missing_env_vars or missing_config_files or external_code_signals),
        "has_config_text_signals": bool(signals),
        "unresolved_external_signals": unresolved_external_signals[:20],
        "missing_env_vars": missing_env_vars,
        "env_vars": sorted(env_vars.values(), key=lambda x: x["name"]),
        "missing_config_files": sorted(missing_config_files, key=lambda x: x["path"]),
        "config_files": sorted(config_files.values(), key=lambda x: x["path"]),
        "credential_urls": sorted(urls.values(), key=lambda x: x["url"]),
        "signals": signals[:20],
        "external_code_signals": external_code_signals[:20],
        "ignored_weak_signals": ignored_weak_signals[:20],
        "config_scan_notes": notes,
        "instructions": instructions,
    }
