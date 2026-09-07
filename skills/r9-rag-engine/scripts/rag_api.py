#!/usr/bin/env python3
"""Python API for searching the RAG index."""

import json
from pathlib import Path
from typing import List, Optional

import faiss
import numpy as np

from embedder import encode_query
from rag_config import CONFIG_PATH, INDEX_PATH, METADATA_PATH


def load_metadata() -> List[dict]:
    if not METADATA_PATH.exists():
        return []
    lines = METADATA_PATH.read_text(encoding="utf-8").strip().split("\n")
    return [json.loads(line) for line in lines if line.strip()]


def load_index():
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"Index not found: {INDEX_PATH}. Run build_index.py first.")
    return faiss.read_index(str(INDEX_PATH))


def search(query: str, top_k: int = 5) -> List[dict]:
    """Search the vector index and return top-k matching chunks."""
    metadata = load_metadata()
    if not metadata:
        return []

    index = load_index()
    query_vector = encode_query(query).reshape(1, -1).astype(np.float32)

    scores, indices = index.search(query_vector, min(top_k, len(metadata)))

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(metadata):
            continue
        item = metadata[idx].copy()
        item["score"] = float(score)
        results.append(item)

    return results


def format_results(results: List[dict], max_text_len: int = 600) -> str:
    if not results:
        return "未找到相关结果。"

    lines = [f"找到 {len(results)} 条相关结果：\n"]
    for i, r in enumerate(results, 1):
        source = r.get("source", "未知来源")
        title = r.get("title", "")
        score = r.get("score", 0.0)
        text = r.get("text", "")[:max_text_len]
        if len(r.get("text", "")) > max_text_len:
            text += "..."

        lines.append(f"[{i}] {source}")
        if title:
            lines.append(f"    标题：{title}")
        lines.append(f"    相关度：{score:.4f}")
        lines.append(f"    内容：{text}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "基金回撤安抚话术"
    results = search(query, top_k=5)
    print(format_results(results))
