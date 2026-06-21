#!/usr/bin/env python3
"""生成 OPC 会议纪要 PDF（统一模板风格）。"""

from pathlib import Path
from datetime import datetime
from opc_pdf_base import OPCPDF

OPC_ROOT = Path('/Users/r9/OPC')


def generate_minutes_pdf(elements, output_path=None):
    """生成会议纪要 PDF。"""
    if output_path is None:
        date_str = datetime.now().strftime('%Y%m%d')
        title = elements.get('theme', '会议')[:20]
        output_path = OPC_ROOT / f'00_公司治理/会议纪要/{date_str}_会议纪要_{title}_v1.pdf'
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    participants = elements.get('participants', ['R9、Luce 及 OPC 各 Agent 角色'])
    if isinstance(participants, list):
        participants = '、'.join(participants)

    pdf = OPCPDF(
        title='OPC 会议纪要',
        subtitle=f'——{elements.get("theme", "OPC 工作会议")}——',
        author='Luce · OPC CEO',
        header_text=f'OPC 会议纪要 · {elements.get("theme", "工作会议")}'
    )
    pdf.cover()

    pdf.h1(elements.get('theme', 'OPC 工作会议'))
    pdf.info_block([
        ('会议时间：', elements.get('date', datetime.now().strftime('%Y年%m月%d日'))),
        ('参会人员：', participants),
    ])

    pdf.h2('一、核心结论')
    conclusions = elements.get('conclusions', [])
    if conclusions:
        for c in conclusions:
            pdf.bullet(c)
    else:
        pdf.paragraph('（本次讨论未形成明确结论性表述）')

    pdf.h2('二、决议事项')
    decisions = elements.get('decisions', [])
    if decisions:
        for d in decisions:
            pdf.bullet(d)
    else:
        pdf.paragraph('（本次讨论未形成正式决议）')

    pdf.h2('三、待办任务')
    todos = elements.get('todos', [])
    if todos:
        for t in todos:
            pdf.bullet(t)
    else:
        pdf.paragraph('（暂无新增待办）')

    pdf.output(str(output_path))
    return output_path


if __name__ == '__main__':
    sample = {
        'theme': '风格切换与资产配置讨论',
        'date': '2026年06月13日',
        'participants': ['R9', 'Luce', 'Atlas', 'Mira'],
        'conclusions': [
            '当前处于高切低再平衡早期，尚未构成全面风格反转。',
            '有色金属受供给约束+弱美元+资金切低估值共振驱动，短期情绪过热不建议追涨。'
        ],
        'decisions': [
            'Atlas 在 6/13 收盘后生成风格切换简报终版。',
            'Mira 牵头 L2 客户集中再平衡。'
        ],
        'todos': [
            'Atlas 生成风格切换简报终版（6/13 收盘后）',
            'Mira 组织 L2 客户再平衡（6/20 前）',
            'Vega 推进数据接入 L3 自动化（7/11 前）'
        ]
    }
    path = generate_minutes_pdf(sample)
    print(f"会议纪要已生成：{path}")
