#!/usr/bin/env python3
"""生成 OPC 董事长指令跟踪表 PDF（统一模板风格）。"""

from pathlib import Path
from datetime import datetime
import json
from opc_pdf_base import OPCPDF, COLOR_PRIMARY, COLOR_TEXT, COLOR_TABLE_LINE

OPC_ROOT = Path('/Users/r9/OPC')
DESKTOP = Path('/Users/r9/Desktop')
TRACKER_JSON = Path('/Users/r9/.kimi/skills/r9-opc-memory/tracker_data.json')


def load_items():
    if TRACKER_JSON.exists():
        with open(TRACKER_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('items', [])
    return []


def generate_tracker_pdf(output_path=None):
    if output_path is None:
        output_path = OPC_ROOT / '00_公司治理/OPC_董事长指令跟踪表.pdf'
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    items = load_items()
    pdf = OPCPDF(
        title='OPC 董事长指令跟踪表',
        subtitle='公司治理 · 指令交办 · 执行跟踪',
        author='Luce · OPC CEO',
        header_text='OPC 董事长指令跟踪表'
    )
    pdf.cover()

    pdf.h1('OPC 董事长指令跟踪表')
    pdf.paragraph(f'更新日期：{datetime.now().strftime("%Y年%m月%d日")}')
    pdf.paragraph('本表自动维护董事长 R9 交办指令，跟踪负责人、截止时间、状态、交付物与备注。')

    # 表头
    headers = ['序号', '指令内容', '负责人', '截止时间', '状态', '交付物', '备注']
    col_widths = [12, 70, 25, 25, 22, 45, 45]

    # 自定义表格渲染
    pdf.set_font('Hei', '', 9)
    pdf.set_fill_color(*COLOR_PRIMARY)
    pdf.set_text_color(255, 255, 255)
    pdf.set_draw_color(*COLOR_TABLE_LINE)
    for h, w in zip(headers, col_widths):
        pdf.cell(w, 8, h, border=1, fill=True, align='C')
    pdf.ln()

    status_colors = {
        '已完成': (200, 255, 200),
        '进行中': (255, 255, 200),
        '待启动': (240, 240, 240),
        '待决策': (255, 220, 200),
    }

    pdf.set_font('Hei', '', 8.5)
    pdf.set_text_color(*COLOR_TEXT)
    for item in items:
        row = [
            str(item.get('id', '')),
            item.get('content', ''),
            item.get('owner', ''),
            item.get('deadline', ''),
            item.get('status', ''),
            item.get('deliverable', ''),
            item.get('note', ''),
        ]
        status = item.get('status', '')
        fill_color = status_colors.get(status, (255, 255, 255))
        pdf.set_fill_color(*fill_color)

        # 计算行高
        max_lines = 1
        for text, w in zip(row, col_widths):
            lines = len(str(text)) / max(1, (w / 2.2)) + 1
            max_lines = max(max_lines, lines)
        row_h = max(7, min(max_lines * 4.5, 20))

        x_start = pdf.get_x()
        y_start = pdf.get_y()
        for text, w in zip(row, col_widths):
            pdf.multi_cell(w, row_h / max_lines, str(text), border=1, fill=True, align='L')
            x_start += w
            pdf.set_xy(x_start, y_start)
        pdf.ln(row_h)

    pdf.output(str(output_path))

    # 同时备份桌面
    desktop_path = DESKTOP / 'OPC_董事长指令跟踪表.pdf'
    pdf.output(str(desktop_path))

    return output_path, desktop_path


if __name__ == '__main__':
    paths = generate_tracker_pdf()
    print(f"指令跟踪表已生成：\n  {paths[0]}\n  {paths[1]}")
