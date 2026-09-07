#!/usr/bin/env python3
"""生成 R9 向量 RAG 介绍 PDF。"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path('/Users/r9/.kimi/skills/r9-opc-memory')))
from opc_pdf_base import OPCPDF


def main():
    output_path = Path('/Users/r9/Desktop/R9_向量RAG与Skill体系介绍.pdf')

    pdf = OPCPDF(
        title='R9 向量 RAG 与 Skill 体系',
        subtitle='从"整篇加载"到"语义检索"的 Agent 升级指南',
        author='Vega · OPC 交易运营部',
        header_text='R9 向量 RAG 与 Skill 体系',
    )
    pdf.cover()

    # 1. 一句话定位
    pdf.h1('一、一句话定位')
    pdf.paragraph(
        'R9 向量 RAG（r9-rag-engine）是投研工作台的「知识外挂」。'
        '它把分散在 95 个 skill、课程知识库和 OPC 公司记忆中的文本做语义索引，'
        '让 Agent 在回答问题时不再靠「硬背整本说明书」，而是像查资料一样精准召回最相关的片段。'
    )

    # 2. 没有 RAG 之前的问题
    pdf.h1('二、没有 RAG 之前：三种「装不下」')

    pdf.h2('1. Skill 说明书太长')
    pdf.paragraph(
        '每个 skill 的 SKILL.md 动辄几千字。路由 Agent 虽然只加载被触发 skill 的完整指令，'
        '但一旦任务需要跨 skill 查资料（例如写基金话术时要同时查课程材料和 OPC 纪要），'
        '上下文很快就被撑满，模型容易丢三落四。'
    )

    pdf.h2('2. 课程知识库靠「读全文件」')
    pdf.paragraph(
        'r9-course-knowledge 之前是按主题把 PDF/PPT 提取成 markdown reference，'
        '使用时先读目录再读整篇文件。问题是 reference 文件本身很长（如基金研究主题约 1.5 万行），'
        '真正用到的往往只有其中几页，却要整篇加载。'
    )

    pdf.h2('3. OPC 记忆只能靠关键词')
    pdf.paragraph(
        'r9-opc-memory 之前靠文件名、摘要、关键词做 token 匹配。'
        '如果用户问"上次风格切换的结论"，必须命中"风格切换"这个词；'
        '问"高切低怎么看"就很可能检索不到。'
    )

    # 3. RAG 做了什么改变
    pdf.h1('三、RAG 做了什么改变')
    pdf.paragraph(
        'RAG 的核心只做三件事：分块（Chunk）→ 向量化（Embedding）→ 语义检索（Search）。'
        '把知识切成小段、转成向量、存入 FAISS，查询时用自然语言找最相关的片段。'
    )

    pdf.h2('1. 只加载最相关的片段')
    pdf.paragraph(
        '例如用户问"客户基金回撤怎么安抚"，RAG 会召回 fund-market-volatility-script 的话术要点、'
        '课程中售后陪伴的话术举例、固收+回撤控制卖点话术等 3-5 个片段，而不是把 95 个 skill 全读一遍。'
    )

    pdf.h2('2. 自然语言提问，跨文件关联')
    pdf.paragraph(
        '用户问"高切低怎么看"，向量检索能把它和"风格切换持续性判断""价值/红利短期占优"等语义相近的内容关联起来，'
        '即使查询词和原文用词不完全一致也能召回。'
    )

    pdf.h2('3. 课程、Skill、OPC 记忆统一检索')
    pdf.paragraph(
        'r9-rag-engine 的索引范围同时覆盖：'
    )
    pdf.bullet('所有 skill 的 SKILL.md 主文档')
    pdf.bullet('所有 skill 的 references/ 参考资料')
    pdf.bullet('r9-course-knowledge 课程知识库')
    pdf.bullet('~/OPC/ 目录下的 PDF/DOCX 公司记忆')
    pdf.ln(2)

    # 4. 技术架构
    pdf.h1('四、技术架构')
    pdf.paragraph('')
    pdf.quote(
        '用户问题\n'
        '    ↓\n'
        'BAAI/bge-small-zh-v1.5（中英双语 Embedding，512 维）\n'
        '    ↓\n'
        'FAISS IndexFlatIP（本地向量索引）\n'
        '    ↓\n'
        'Top-K 相关文本片段（带来源路径和相关度分数）\n'
        '    ↓\n'
        '注入 Prompt 上下文 → Agent 生成回答'
    )

    pdf.info_block([
        ('索引文件', '/Users/r9/.kimi/skills/r9-rag-engine/data/index.faiss'),
        ('元数据文件', '/Users/r9/.kimi/skills/r9-rag-engine/data/metadata.jsonl'),
        ('当前规模', '206 个文件，6898 个 chunk'),
        ('模型', 'BAAI/bge-small-zh-v1.5（约 100MB，本地运行）'),
        ('运行环境', '/Users/r9/.kimi/skills/r9-rag-engine/.venv'),
    ])

    # 5. 与现有 Skill 的关系
    pdf.h1('五、与现有 Skill 的关系')
    pdf.paragraph(
        'RAG 不是替代现有 skill，而是给它们装上「记忆力」和「资料库」。'
    )

    rows = [
        ['r9-workbench', '路由前先用 RAG 检索，判断用户问题涉及哪个 skill 或需要哪些背景知识'],
        ['r9-course-knowledge', '从「读全文件」改为「向量检索 + 按需精读相关片段」'],
        ['r9-opc-memory', '关键词检索升级为「向量语义检索 + 关键词兜底」'],
        ['fund-market-volatility-script', '可直接检索课程和 OPC 中的相关话术，生成更贴合 R9 风格的安抚内容'],
        ['fund-advisor-strategy', '检索资产配置、组合再平衡、定投等课程框架后再做方案'],
        ['initiating-coverage / dcf-model', '检索模型说明、估值方法论 reference，减少误用框架'],
    ]
    pdf.table(['Skill', 'RAG 如何增强它'], rows, col_widths=[50, 100])

    # 6. 如何用好 RAG 做好 Agent
    pdf.h1('六、如何用好 RAG 做好 Agent')

    pdf.h2('模式 1：路由前检索（减少误判）')
    pdf.paragraph(
        '当用户输入模糊时，先用 RAG 检索相关片段。'
        '例如用户说"客户亏了怎么沟通"，检索结果会集中出现在 fund-market-volatility-script、'
        '课程售后陪伴、固收+话术等方向，Agent 可以据此精准路由。'
    )

    pdf.h2('模式 2：执行中检索（补充背景）')
    pdf.paragraph(
        'Agent 在执行某个 skill 时，如果涉及跨领域知识，可以实时检索。'
        '例如写基金深度研报时，同时检索 R9Alpha 评价框架、Brinson 归因说明、课程中的基金评价案例。'
    )

    pdf.h2('模式 3：生成内容时检索（保证口径一致）')
    pdf.paragraph(
        '写客户话术、公众号文章、会议纪要时，先检索 R9 课程和 OPC 历史材料中的类似表述，'
        '确保输出风格、术语、框架与组织知识一致。'
    )

    pdf.h2('模式 4：记忆恢复时检索（上下文续接）')
    pdf.paragraph(
        '新对话开始时，用户说"接着聊"或"上次那个方案"，用 RAG 检索 OPC 会议纪要、指令跟踪表，'
        '快速恢复上下文，不用让用户重复背景。'
    )

    # 7. 使用命令
    pdf.h1('七、常用命令')
    pdf.quote(
        '# 向量检索\n'
        'python3 /Users/r9/.kimi/skills/r9-rag-engine/scripts/search.py "基金回撤客户安抚话术"\n\n'
        '# 重建索引（skill/reference/OPC 文件更新后）\n'
        'python3 /Users/r9/.kimi/skills/r9-rag-engine/scripts/build_index.py\n\n'
        '# 在 Python 中调用（需通过 venv 子进程）\n'
        'subprocess.run([\n'
        '    "/Users/r9/.kimi/skills/r9-rag-engine/.venv/bin/python",\n'
        '    "-c",\n'
        '    "from rag_api import search; print(search(...)"\n'
        '])'
    )

    # 8. 维护建议
    pdf.h1('八、维护建议')
    pdf.bullet('每次新增/修改 skill 或 reference 后，重新运行 build_index.py')
    pdf.bullet('课程课件更新后，先运行 r9-course-knowledge/scripts/update_rag.py，再运行 build_index.py')
    pdf.bullet('OPC 新归档 PDF/DOCX 会自动被索引覆盖，无需额外操作')
    pdf.bullet('定期抽查检索质量，对召回不好的主题可在 SKILL.md 或 reference 中增加关键词和同义表述')
    pdf.ln(2)

    pdf.h1('九、下一步可做的事')
    pdf.bullet('为高频检索主题（话术、框架、模型）单独建立「精华片段」reference，提升 Top-K 密度')
    pdf.bullet('在 r9-workbench 中固化「先 RAG 后路由」的默认流程')
    pdf.bullet('把检索结果自动注入各 skill 的 prompt 模板，减少重复调用代码')
    pdf.bullet('建立检索日志，分析哪些问题经常搜不到，反向优化索引内容')
    pdf.ln(2)

    pdf.output(str(output_path))
    print(f'PDF 已生成：{output_path}')


if __name__ == '__main__':
    main()
