#!/usr/bin/env python3
"""生成 OPC 内部辩论/沟通会会议纪要 PDF（统一模板风格）。"""

from pathlib import Path
from datetime import datetime
from opc_pdf_base import OPCPDF, COLOR_PRIMARY, COLOR_TEXT

OPC_ROOT = Path('/Users/r9/OPC')


def generate_debate_minutes(data, output_path=None):
    if output_path is None:
        date_str = datetime.now().strftime('%Y%m%d')
        title = data.get('theme', '沟通会')[:20]
        output_path = OPC_ROOT / f'00_公司治理/会议纪要/{date_str}_会议纪要_{title}_v1.pdf'
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pdf = OPCPDF(
        title='OPC 内部沟通会纪要',
        subtitle=f'——{data.get("theme", "内部沟通")}——',
        author='Luce · OPC CEO',
        header_text=f'OPC 内部沟通会纪要 · {data.get("theme", "")}'
    )
    pdf.cover()

    pdf.h1(data['theme'])
    if data.get('subtitle'):
        pdf.h2(data['subtitle'])

    pdf.info_block([
        ('会议时间', data['date']),
        ('参会人员', data['participants']),
        ('会议地点', data.get('location', 'OPC 内部会议室')),
    ])

    if 'background' in data:
        pdf.h2('一、议题背景')
        for para in data['background']:
            pdf.paragraph(para)

    if 'debates' in data:
        pdf.h2('二、双方观点陈述')
        for debate in data['debates']:
            pdf.h3(debate['title'])
            for point in debate['points']:
                pdf.bullet(point)

    if 'clash' in data:
        pdf.h2('三、交锋焦点')
        for item in data['clash']:
            pdf.h3(item['topic'])
            for q in item['exchanges']:
                speaker = q['speaker']
                content = q['content']
                # 发言人名称加粗效果：先输出名称
                pdf.set_font('Hei', '', 11)
                pdf.set_text_color(*COLOR_PRIMARY)
                pdf.cell(25, 6.2, f'{speaker}：', new_x='RIGHT', new_y='TOP')
                # 内容正文
                pdf.set_font('Song', '', 10.5)
                pdf.set_text_color(*COLOR_TEXT)
                pdf.multi_cell(pdf.w - pdf.l_margin - pdf.r_margin - 25, 6.2, content)
                pdf.ln(1.5)
                pdf.set_text_color(0, 0, 0)

    pdf.h2('四、核心结论')
    if data.get('conclusions'):
        for c in data['conclusions']:
            pdf.bullet(c)
    else:
        pdf.paragraph('（本次讨论未形成明确结论性表述）')

    pdf.h2('五、决议事项')
    if data.get('decisions'):
        for d in data['decisions']:
            pdf.bullet(d)
    else:
        pdf.paragraph('（本次讨论未形成正式决议）')

    pdf.h2('六、待办任务')
    if data.get('todos'):
        for t in data['todos']:
            pdf.bullet(t)
    else:
        pdf.paragraph('（暂无新增待办）')

    pdf.output(str(output_path))
    return output_path


if __name__ == '__main__':
    sample = {
        'theme': '弹性资产加仓 vs 客户持有体验',
        'subtitle': 'Mercury（投研策略部） vs Evan（投顾服务部）',
        'date': '2026年06月20日',
        'participants': 'R9、Luce、Mercury（投研策略部·行业研究员）、Evan（投顾服务部·客户陪伴专家）、Atlas、Mira',
        'location': 'OPC 内部会议室',
        'background': [
            '基于投研策略部《风格切换持续性专题简报》（2026-06-12 初稿），当前市场处于“高切低”再平衡早期。',
            'Mercury 认为 AI 产业链中期景气度仍在，建议继续加大弹性资产配置；Evan 基于 10 年高净值客户服务经验，认为当前成长风格波动已严重损害客户持有体验，主张防御再平衡。'
        ],
        'debates': [
            {
                'title': 'Mercury：继续加大弹性资产配置',
                'points': [
                    'AI 产业趋势未终结，7 月业绩预告或将再次验证景气。',
                    '当前调整为获利了结与估值再平衡，而非产业趋势逆转。',
                    '应聚焦有真实业绩支撑的核心品种，抛弃纯题材标的。'
                ]
            },
            {
                'title': 'Evan：当前风格已不适合客户后续持有体验',
                'points': [
                    '创业板指 20 日波动率 34.49%，客户实际回撤感受远大于指数。',
                    '10 年客户服务经验表明，多数客户无法承受 20% 以上回撤。',
                    '再平衡到红利/银行/高股息，是改善持有体验的最优解。'
                ]
            }
        ],
        'clash': [
            {
                'topic': '焦点一：AI 是否涨多了？',
                'exchanges': [
                    {'speaker': 'Mercury', 'content': 'AI 没有普涨式泡沫，只是内部分化。'},
                    {'speaker': 'Evan', 'content': '对客户来说，区分“真 AI”和“假 AI”没有意义。'}
                ]
            }
        ],
        'conclusions': [
            '短期继续维持“核心成长 + 卫星价值红利”的再平衡结构。',
            'AI 板块内部进入“去伪存真”阶段。',
            '客户侧以 L2/L3 高权益客户为重点，完成一轮再平衡沟通。'
        ],
        'decisions': [
            'Mercury 输出 AI 产业链业绩可验证标的清单。',
            'Evan 整理高权益客户波动期沟通话术 2.0。'
        ],
        'todos': [
            'Mercury：输出 AI 白名单',
            'Evan：整理沟通话术'
        ]
    }
    path = generate_debate_minutes(sample)
    print(f"沟通会纪要已生成：{path}")
