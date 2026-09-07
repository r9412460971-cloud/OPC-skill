#!/usr/bin/env python3
"""Compatibility wrapper for the shared skill workflow log utilities."""

from __future__ import annotations

import sys
import importlib.util
import json
import os
from pathlib import Path


def _module_from_base(base: str | Path | None) -> Path | None:
    if not base:
        return None
    root = Path(base).expanduser()
    if root.is_file() and root.name == "workflow_log_util.py":
        return root
    for rel in (
        Path("workflow_log_util.py"),
        Path("workflow-common") / "workflow_log_util.py",
        Path("_workflow_common") / "workflow_log_util.py",
        Path(".workbuddy") / "skill-marketplace" / "workflow-common" / "workflow_log_util.py",
    ):
        candidate = root / rel
        if candidate.exists():
            return candidate
    return None


def _module_from_workspace_config(base: str | Path | None) -> Path | None:
    if not base:
        return None
    config_path = Path(base).expanduser() / ".workbuddy" / "skill-marketplace" / "config.json"
    if not config_path.exists():
        return None
    try:
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    workspace_root = config.get("workspace_root")
    return _module_from_base(workspace_root)


def _find_common_module() -> Path:
    here = Path(__file__).resolve()
    for env_name in ("SKILL_WORKFLOW_COMMON_DIR", "SKILL_MARKETPLACE_WORKSPACE"):
        candidate = _module_from_base(os.environ.get(env_name, ""))
        if candidate:
            return candidate
    for parent in [Path.cwd(), *Path.cwd().parents, *here.parents]:
        candidate = _module_from_workspace_config(parent)
        if candidate:
            return candidate
    for parent in [Path.cwd(), *Path.cwd().parents]:
        candidate = _module_from_base(parent)
        if candidate:
            return candidate
    for parent in here.parents:
        candidate = _module_from_base(parent)
        if candidate:
            return candidate
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    candidate = _module_from_base(codex_home / "skills")
    if candidate:
        return candidate
    raise ModuleNotFoundError(
        "Cannot locate workflow_log_util.py from "
        f"{here}; set SKILL_WORKFLOW_COMMON_DIR, run from a workspace with "
        ".workbuddy/skill-marketplace/workflow-common, or install the shared workflow utilities."
    )

COMMON_MODULE = _find_common_module()
COMMON_DIR = COMMON_MODULE.parent
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))
spec = importlib.util.spec_from_file_location("workflow_log_util", COMMON_MODULE)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load workflow_log_util from {COMMON_MODULE}")
_workflow_log_util = importlib.util.module_from_spec(spec)
sys.modules["workflow_log_util"] = _workflow_log_util
spec.loader.exec_module(_workflow_log_util)

globals().update({
    name: value
    for name, value in vars(_workflow_log_util).items()
    if not name.startswith("__")
})


if __name__ == "__main__":
    _workflow_log_util.main()
