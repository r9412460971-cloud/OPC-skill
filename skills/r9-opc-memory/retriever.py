#!/usr/bin/env python3
"""OPC 记忆检索：结合向量语义检索与关键词匹配检索历史信息。"""

import json
import re
import sys
from pathlib import Path

OPC_ROOT = Path('/Users/r9/OPC')
SKILL_DIR = Path('/Users/r9/.kimi/skills/r9-opc-memory')
INDEX_FILE = SKILL_DIR / 'memory_index.json'
RAG_API = Path('/Users/r9/.kimi/skills/r9-rag-engine/scripts/rag_api.py')


def load_index():
    if INDEX_FILE.exists():
        with open(INDEX_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('items', [])
    return []


def tokenize(text):
    """分词：中文单字、英文单词、连续数字、下划线分隔。"""
    text = str(text).lower()
    tokens = []
    tokens.extend(re.findall(r'[\u4e00-\u9fa5]', text))
    for part in re.findall(r'[a-z0-9_]+', text):
        for sub in part.split('_'):
            for sub2 in re.findall(r'[a-z]+|[0-9]+', sub):
                if len(sub2) >= 2 or sub2.isdigit():
                    tokens.append(sub2)
    return tokens


def compact(text):
    """去掉所有非字母数字字符，形成紧凑字符串。"""
    return re.sub(r'[^a-z0-9\u4e00-\u9fa5]', '', str(text).lower())


def keyword_search(query, top_n=5):
    """基于关键词/文件名的传统检索。"""
    items = load_index()
    query_tokens = tokenize(query)
    query_compact = compact(query)
    if not query_tokens and not query_compact:
        return []

    results = []
    for item in items:
        score = 0
        filename = item.get('filename', '')
        category = item.get('category', '')
        keywords = ' '.join(item.get('keywords', []))
        summary = item.get('summary', '')

        searchable_text = ' '.join([filename, category, keywords, summary])
        searchable_tokens = tokenize(searchable_text)

        for token in query_tokens:
            if token in searchable_tokens:
                score += 1

        if query_compact and query_compact in compact(filename):
            score += 3

        if query_compact and query_compact in compact(summary + keywords):
            score += 1

        if score > 0:
            results.append((score, item))

    results.sort(key=lambda x: (-x[0], x[1].get('date', '')))
    return results[:top_n]


def vector_search(query, top_n=5):
    """基于 r9-rag-engine 的向量语义检索，返回 OPC 相关 chunk。"""
    if not RAG_API.exists():
        return []

    venv_python = RAG_API.parent.parent / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return []

    try:
        import subprocess
        script = f"""
import sys
sys.path.insert(0, "{RAG_API.parent}")
from rag_api import search
import json
results = search({query!r}, top_k={top_n * 2})
opc_results = [r for r in results if r.get('source', '').startswith('OPC/')]
print(json.dumps(opc_results[:{top_n}], ensure_ascii=False))
"""
        result = subprocess.run(
            [str(venv_python), "-c", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"[vector_search warning] {result.stderr}", file=sys.stderr)
            return []
        return json.loads(result.stdout)
    except Exception as e:
        print(f"[vector_search warning] {e}", file=sys.stderr)
        return []


def search(query, top_n=5):
    """综合检索：优先返回向量语义结果，再补充关键词匹配结果。"""
    vec_results = vector_search(query, top_n=top_n)
    kw_results = keyword_search(query, top_n=top_n)

    # Merge: vector results first, then keyword results not already included
    seen_ids = set()
    merged = []

    for r in vec_results:
        source = r.get('source', '')
        if source not in seen_ids:
            seen_ids.add(source)
            merged.append(('vector', r))

    for score, item in kw_results:
        item_id = item.get('id', '') or item.get('filename', '')
        path = item.get('path', '')
        if path not in seen_ids and item_id not in seen_ids:
            seen_ids.add(path)
            seen_ids.add(item_id)
            merged.append(('keyword', (score, item)))

    return merged[:top_n]


def answer_question(question):
    """回答历史检索问题。"""
    results = search(question, top_n=5)
    if not results:
        return "未在 OPC 本地归档中找到相关信息。请检查关键词或确认该内容已被归档。"

    lines = []
    lines.append("——检索结果——")
    for i, (source_type, payload) in enumerate(results, 1):
        if source_type == 'vector':
            r = payload
            source = r.get('source', '未知来源')
            title = r.get('title', Path(source).name)
            score = r.get('score', 0.0)
            text = r.get('text', '')[:120]
            full_path = OPC_ROOT.parent / source
            lines.append(f"{i}. [向量匹配，相关度 {score:.4f}] {title}")
            lines.append(f"   摘要：{text}...")
            lines.append(f"   路径：{full_path}")
        else:
            score, item = payload
            date = item.get('date', '未知日期')
            title = item.get('filename', '未命名')
            category = item.get('category', '')
            summary = item.get('summary', '')[:80]
            full_path = OPC_ROOT.parent / item.get('path', '')
            lines.append(f"{i}. [关键词匹配，得分 {score}] [{date}] {title}（{category}）")
            lines.append(f"   摘要：{summary}...")
            lines.append(f"   路径：{full_path}")
        lines.append('')

    return '\n'.join(lines)


if __name__ == '__main__':
    query = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else '风格切换'
    print(answer_question(query))
