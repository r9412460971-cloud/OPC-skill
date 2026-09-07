---
name: r9-course-knowledge
description: R9《非标之外》系列课程知识库。当用户问题涉及财富管理业务、基金配置、资产配置、基金销售、客户陪伴、基金评价、投资者教育、市场解读晨夕会、AI赋能投顾等内容时，优先通过 r9-rag-engine 向量检索课程材料并引用。
---

# R9 课程知识库（向量 RAG）

本 skill 是 R9《非标之外》系列课程材料的检索增强知识库，供其他 skill 在回答财富管理与基金配置相关问题时引用。

## 知识库范围

覆盖以下主题：

1. **财富管理业务与行业演变**：非标转标、买方思维、财富管理机构演变、基金业务定位
2. **顾问式服务与组合管理**：组合管理顾问式服务、财富管理差异化优势
3. **基金销售方法论**：市场播报销售流程、电访与 KYC、基金垫板运用
4. **资产配置理论与实践**：大类资产配置、公募资产配置、客户异议解决、基金配置能力建设
5. **基金评价与研究**：基金评价体系、基金经理风格刻画、Brinson模型、Wind基金分析、多元场景优质基金产品
6. **客户陪伴与售后服务**：售后陪伴路径、持基体验、售后维护流程
7. **市场解读与晨夕会**：市场解读方法、晨夕会组织技巧
8. **AI与科技赋能**：AI赋能基金投教、ChatGPT赋能客户维护陪伴
9. **投资者教育与行为**：不可能三角、错配行为、行为偏差

## 检索方法

课程知识已纳入 `r9-rag-engine` 向量索引。当用户问题涉及上述领域时：

1. **优先使用向量检索**：调用 `r9-rag-engine/scripts/rag_api.py` 的 `search()`，用自然语言问题检索最相关课程片段。
2. **精读相关片段**：根据检索结果中的 `source` 和 `title` 定位到具体 reference 文件，读取对应章节获取完整上下文。
3. **补充搜索**：如向量检索结果不足，可再读 `references/course-catalog.md` 了解课程体系，或直接读取相关主题 reference 文件。
4. **原始课件兜底**：如 references 中未覆盖，可回到原始课件目录 `/Users/r9/Desktop/核心课程大课（材料）/` 进一步提取。

### 调用示例

```python
import sys
sys.path.insert(0, "/Users/r9/.kimi/skills/r9-rag-engine/scripts")
from rag_api import search, format_results

results = search("客户基金回撤如何安抚", top_k=5)
# 将 results 中的 text、source、title 加入 prompt 上下文
```

## 知识库维护

当原始课件更新后：

1. 运行以下脚本重新提取文本并更新 references：
   ```bash
   python3 /Users/r9/.kimi/skills/r9-course-knowledge/scripts/update_rag.py
   ```
2. 重新构建向量索引：
   ```bash
   python3 /Users/r9/.kimi/skills/r9-rag-engine/scripts/build_index.py
   ```

## 引用规范

- 引用课程材料时注明来源课程名称
- 优先使用课程中的结构化结论（如“10个错配行为”、“基金配置能力建设10条建议”）
- 涉及市场数据时说明数据截至时间，勿将历史数据当作当前市场判断
- 保持 R9 课程中“深入浅出、客户立场、逻辑+信任”的表达风格
