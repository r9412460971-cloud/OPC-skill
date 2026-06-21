#!/usr/bin/env python3
"""生成 OPC 投顾公司员工介绍报告 PDF（统一模板风格）。"""

import json
from pathlib import Path
from datetime import datetime
from opc_pdf_base import OPCPDF

OUTPUT_DIR = Path('/Users/r9/OPC/05_人力资源/员工档案')
DATA_FILE = Path('/Users/r9/.kimi/skills/r9-opc-memory/employee_data.json')


def load_data():
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def add_member(pdf, member):
    pdf.h2(f"{member['id']}. {member['name']} · {member['title']}")

    pdf.info_block([
        ('年龄', f"{member['age']}岁"),
        ('学历', member['education']),
        ('履历', member['experience']),
        ('性格', member['personality']),
        ('职责', member['responsibility']),
        ('KPI', member['kpi']),
    ])


def generate(output_path=None):
    if output_path is None:
        output_path = OUTPUT_DIR / f'OPC_员工介绍报告_v2.pdf'
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = load_data()
    total_members = sum(len(d['members']) for d in data['departments'])

    pdf = OPCPDF(
        title='OPC 投顾公司员工介绍报告',
        subtitle='含性格、履历、职责与KPI',
        author=data.get('author', 'Luce · OPC CEO'),
        header_text='OPC 投顾公司员工介绍报告'
    )
    pdf.cover()

    pdf.h1('编制说明')
    pdf.paragraph(
        f"本报告为OPC投顾公司全体员工的统一介绍材料，涵盖公司治理层、投研策略部、投顾服务部共{total_members}位核心成员。"
        "每位成员的介绍包括基本情况、教育背景、职业履历、性格特征、当前主要职责以及关键绩效指标（KPI）建议。"
    )
    pdf.paragraph(
        "KPI制定原则：以公司战略为核心，兼顾过程指标与结果指标；定量为主、定性为辅；强调跨部门协同与客户价值创造。"
    )
    pdf.paragraph('内部资料，仅供 R9 董事长查阅')

    for dept in data['departments']:
        pdf.h1(dept['name'])
        for member in dept['members']:
            add_member(pdf, member)

    pdf.h1('协同与考核机制')
    for idx, note in enumerate(data['notes'], 1):
        pdf.paragraph(f'{idx}. {note}')

    pdf.output(str(output_path))
    return output_path


if __name__ == '__main__':
    path = generate()
    print(f"员工介绍报告已生成：{path}")
