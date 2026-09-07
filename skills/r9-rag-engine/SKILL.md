---
name: r9-rag-engine
description: R9 投研工作台的本地向量检索引擎。对所有 skill 的 SKILL.md、references、课程知识库和 OPC 公司记忆做语义分块、embedding 和 FAISS 索引，供其他 skill 在回答问题时检索相关知识片段。当用户问题需要查找 skill 使用方法、课程材料、公司历史决策、话术模板等分散知识时触发。
---

# r9-rag-engine

R9 投研工作台的本地向量 RAG 引擎。把分散在 94 个 skill、课程知识库和 OPC 记忆中的知识做语义索引，让 Agent 不用加载整篇 reference 也能召回最相关的片段。

## 触发条件

当其他 skill 或 routing agent 需要查找以下知识时调用本 skill：

- 某个 skill 的具体用法、输出格式、判断规则
- R9 课程中的框架、案例、话术、数据
- OPC 公司历史会议纪要、决策记录、指令跟踪
- 分散在多个 skill references 中的交叉知识

## 核心能力

### 1. 语义检索

输入自然语言问题，返回最相关的文本片段（chunk），包含来源路径和相关度分数。

```python
from scripts.rag_api import search, format_results

results = search("客户基金回撤安抚话术", top_k=5)
print(format_results(results))
```

### 2. 已索引内容

- `~/.kimi/skills/*/SKILL.md` — 所有 skill 主文档
- `~/.kimi/skills/*/references/*` — skill 参考资料
- `~/OPC/**/*.{pdf,docx}` — OPC 公司记忆归档文件

### 3. 本地运行

- Embedding 模型：`BAAI/bge-small-zh-v1.5`（中英双语，约 100MB）
- 向量索引：FAISS（`IndexFlatIP`，本地文件）
- 无需 API Key，数据不出本机

## 使用方式

### 命令行检索

```bash
python3 /Users/r9/.kimi/skills/r9-rag-engine/scripts/search.py "固收+基金回撤安抚话术"
```

### 重新构建索引

当新增/修改 skill、references 或 OPC 归档文件后运行：

```bash
python3 /Users/r9/.kimi/skills/r9-rag-engine/scripts/build_index.py
```

### 其他 skill 调用

`rag_api.py` 依赖 venv 中的 `faiss` 和 `sentence-transformers`，必须在隔离环境里运行。推荐两种方式：

**方式 A：子进程调用（适合 system python 环境）**

```python
import json
import subprocess

query = "投顾组合再平衡方法"
result = subprocess.run(
    [
        "/Users/r9/.kimi/skills/r9-rag-engine/.venv/bin/python",
        "-c",
        f"""
import sys
sys.path.insert(0, "/Users/r9/.kimi/skills/r9-rag-engine/scripts")
from rag_api import search
import json
print(json.dumps(search({query!r}, top_k=3), ensure_ascii=False))
"""
    ],
    capture_output=True,
    text=True,
    timeout=120,
)
results = json.loads(result.stdout)
```

**方式 B：在 venv 内直接 import**

```bash
/Users/r9/.kimi/skills/r9-rag-engine/.venv/bin/python your_script.py
```

脚本内：

```python
from rag_api import search
results = search("投顾组合再平衡方法", top_k=3)
```

## 集成规范

其他 skill 在需要检索知识时，优先按以下流程：

1. 用 `rag_api.search()` 检索相关问题
2. 取 top-k 结果（建议 3-5 条）
3. 将检索到的文本片段加入 prompt 上下文
4. 基于片段生成回答，并注明来源

## 文件结构

```
r9-rag-engine/
├── SKILL.md
├── scripts/
│   ├── setup.py          # 创建 venv、安装依赖、下载模型
│   ├── build_index.py    # 构建/重建索引
│   ├── search.py         # CLI 检索
│   ├── rag_api.py        # Python API
│   ├── chunker.py        # Markdown/PDF/DOCX 分块
│   ├── embedder.py       # embedding 模型封装
│   ├── _venv_helper.py   # 自动切 venv 运行
│   └── rag_config.py     # 共享配置
└── data/
    ├── config.json       # 索引配置
    ├── index.faiss       # FAISS 向量索引
    └── metadata.jsonl    # chunk 元数据
```

## 维护责任

- **Vega（运营技术）**：定期运行 `build_index.py`，确保索引与 skill 内容同步。
- **Luce（CEO）**：审核检索质量，决定是否扩展索引范围。

*版本：v1.0*
