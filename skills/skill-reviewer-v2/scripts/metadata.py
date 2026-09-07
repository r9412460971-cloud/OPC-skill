"""Source metadata helpers for review workflow decisions."""

from __future__ import annotations

import json
from pathlib import Path

from log_util import CACHE_DIR, api_request, load_pending_review


def _load_source_metadata(skill_dir: Path, skill_name: str, fm: dict) -> dict:
    """从 pending-review.json / _fetch-meta.json / frontmatter 汇总来源元数据。"""
    metadata = {}

    # 1) pending-review.json 是 fetcher → reviewer 队列态的主要来源
    try:
        pending = load_pending_review()
        skill_dir_resolved = str(skill_dir.resolve())
        items = pending.get("items", [])
        # 优先精确匹配 cache_path，避免同名历史 blocked 条目污染当前审查。
        for item in items:
            item_cache = item.get("cache_path") or item.get("skill_dir") or ""
            if item_cache and str(Path(item_cache).resolve()) == skill_dir_resolved:
                metadata.update(item)
                break
        if not metadata:
            for item in items:
                item_name = item.get("skill_name") or item.get("name")
                if item_name == skill_name:
                    metadata.update(item)
                    break
    except Exception:
        pass

    # 2) 兼容历史 _fetch-meta.json
    for meta_path in [skill_dir / "_fetch-meta.json", skill_dir.parent / "_fetch-meta.json"]:
        if meta_path.exists():
            try:
                file_meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
                metadata.update({k: v for k, v in file_meta.items() if v not in (None, "", [])})
                break
            except Exception:
                pass

    # 3) 兜底：frontmatter 中如显式写了来源字段，也纳入判断
    for key in ["source_type", "data_channel", "clawhub_slug", "skillhub_slug", "git_url"]:
        if fm.get(key) and not metadata.get(key):
            metadata[key] = fm.get(key)

    return metadata


def _is_new_upload(skill_name: str, source_meta: dict) -> bool | None:
    """判断是否首次上架。True=new，False=update，None=无法确定。"""
    upload_type = (source_meta.get("upload_type") or "").strip().lower()
    if upload_type == "new":
        return True
    if upload_type == "update":
        return False

    try:
        from urllib.parse import quote
        resp = api_request("GET", f"/skills?keyword={quote(skill_name)}&lifecycle_status=published&page=1&page_size=5")
        items = resp.get("data", {}).get("items") or []
        for item in items:
            if item.get("name") == skill_name:
                return False
        return True
    except RuntimeError:
        return None
