"""Shared parsing and JSON helpers for skill-reviewer-v2."""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path


def parse_frontmatter(content: str) -> tuple[dict | None, str, str]:
    """解析 SKILL.md 的 YAML frontmatter。"""
    match = re.match(r"^---\r?\n(.*?\r?\n)---\r?\n(.*)$", content, re.DOTALL)
    if not match:
        match = re.match(r"^---\r?\n(.*?\r?\n)---(.*)$", content, re.DOTALL)
        if not match:
            return None, content, "failed"

    fm_raw = match.group(1)
    body = match.group(2)

    # 方法一：yaml.safe_load
    try:
        import yaml
        data = yaml.safe_load(fm_raw)
        if isinstance(data, dict):
            return data, body, "yaml"
    except Exception:
        pass

    # 方法二：逐行解析（降级）
    data = {}
    current_key = None
    current_val = ""
    multiline = False

    for line in fm_raw.split("\n"):
        if multiline and (line.startswith("  ") or line.startswith("\t")):
            current_val += " " + line.strip()
            continue

        if not line.strip():
            continue

        if multiline and current_key:
            data[current_key] = current_val.strip().strip("\"'")
            multiline = False
            current_key = None

        kv = re.match(r"^([\w][\w-]*):\s*(.*)", line)
        if kv:
            current_key = kv.group(1)
            val = kv.group(2).strip()
            if val in [">-", "|", ">", "|-", ">+", "|+"]:
                multiline = True
                current_val = ""
                continue
            if val == "":
                multiline = True
                current_val = ""
                continue
            if val and val[0] in "\"'" and val[-1] == val[0]:
                val = val[1:-1]
            data[current_key] = val
            current_key = None

    if multiline and current_key:
        data[current_key] = current_val.strip().strip("\"'")

    if data:
        return data, body, "fallback"
    return None, content, "failed"

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

def _default_json(obj):
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

def _write_stage_json(output_dir: Path, filename: str, data: dict) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=_default_json), encoding="utf-8-sig")
    return str(path)


def _split_checks(review_result: dict, ids: set[str]) -> list[dict]:
    return [c for c in review_result.get("checks", []) if c.get("id") in ids]

def _load_json_if_exists(path: str | Path | None) -> dict:
    if not path:
        return {}
    p = Path(path)
    if not p.exists() or not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"status": "invalid", "error": f"{type(exc).__name__}: {str(exc)[:300]}", "path": str(p)}
