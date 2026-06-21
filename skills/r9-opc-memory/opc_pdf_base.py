#!/usr/bin/env python3
"""
OPC 统一 PDF 模板基础类（恢复使用 STHeiti + Songti 稳定字体）
在原有 PDF 风格基础上做统一，避免 TTC 字体子集化导致的显示问题。
"""

from fpdf import FPDF
from pathlib import Path
from datetime import datetime

FONT_HEI = '/System/Library/Fonts/STHeiti Light.ttc'
FONT_SONG = '/System/Library/Fonts/Supplemental/Songti.ttc'

# 原有 OPC 风格配色
COLOR_PRIMARY = (26, 82, 118)      # #1a5276 深蓝
COLOR_SECONDARY = (30, 132, 73)    # #1e8449 绿色
COLOR_TERTIARY = (46, 134, 193)    # #2e86c1 浅蓝
COLOR_TEXT = (44, 62, 80)          # #2c3e50 正文深灰
COLOR_GRAY = (128, 128, 128)       # #808080 灰色
COLOR_LIGHT_BG = (248, 249, 250)   # #f8f9fa 浅灰背景
COLOR_TABLE_HEADER = (26, 82, 118) # #1a5276 表头深蓝
COLOR_TABLE_LINE = (189, 195, 199) # #bdc3c7 表格线


class OPCPDF(FPDF):
    """OPC 统一风格 PDF 基础类。"""

    def __init__(self, title='', subtitle='', author='', header_text=''):
        super().__init__(unit='mm', format='A4')
        self.report_title = title
        self.report_subtitle = subtitle
        self.report_author = author
        self.header_text = header_text or title
        self.add_font('Hei', '', FONT_HEI)
        self.add_font('Song', '', FONT_SONG)
        self.set_auto_page_break(True, margin=20)
        self.set_margins(18, 18, 18)
        self.alias_nb_pages()
        self.add_page()

    def cover(self):
        """生成封面。"""
        self.set_y(90)
        self.set_font('Hei', '', 22)
        self.set_text_color(*COLOR_PRIMARY)
        self.cell(0, 14, self.report_title, new_x='LMARGIN', new_y='NEXT', align='C')
        self.set_text_color(*COLOR_GRAY)
        self.set_font('Hei', '', 13)
        self.cell(0, 8, self.report_subtitle, new_x='LMARGIN', new_y='NEXT', align='C')
        # 分隔线
        self.set_draw_color(*COLOR_PRIMARY)
        self.set_line_width(0.6)
        line_x = self.w / 2 - 40
        self.line(line_x, self.get_y() + 5, line_x + 80, self.get_y() + 5)
        self.ln(10)
        # 作者/日期
        self.set_font('Song', '', 10)
        if self.report_author:
            self.cell(0, 6, f'作者：{self.report_author}', new_x='LMARGIN', new_y='NEXT', align='C')
        self.cell(0, 6, f'日期：{datetime.now().strftime("%Y年%m月%d日")}', new_x='LMARGIN', new_y='NEXT', align='C')
        self.set_text_color(0, 0, 0)
        self.add_page()

    def header(self):
        """页眉：报告名。"""
        if self.page_no() == 1:
            return
        self.set_y(10)
        self.set_font('Song', '', 8)
        self.set_text_color(*COLOR_GRAY)
        self.cell(0, 5, self.header_text, new_x='LMARGIN', new_y='NEXT', align='C')
        self.set_draw_color(220, 220, 220)
        self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_text_color(0, 0, 0)

    def footer(self):
        """页脚：第 X 页。"""
        if self.page_no() == 1:
            return
        self.set_y(-15)
        self.set_draw_color(*COLOR_PRIMARY)
        self.set_line_width(0.6)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)
        self.set_font('Song', '', 8)
        self.set_text_color(*COLOR_GRAY)
        self.cell(0, 5, f'第 {self.page_no()} 页', align='C')
        self.set_text_color(0, 0, 0)

    def h1(self, title):
        """一级标题。"""
        self.set_font('Hei', '', 17)
        self.set_text_color(*COLOR_PRIMARY)
        self.cell(0, 11, title, new_x='LMARGIN', new_y='NEXT')
        self.set_draw_color(*COLOR_PRIMARY)
        self.set_line_width(0.6)
        y = self.get_y()
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.ln(3)
        self.set_text_color(0, 0, 0)

    def h2(self, title):
        """二级标题。"""
        self.set_font('Hei', '', 13)
        self.set_text_color(*COLOR_SECONDARY)
        self.cell(0, 8, title, new_x='LMARGIN', new_y='NEXT')
        self.ln(1)
        self.set_text_color(0, 0, 0)

    def h3(self, title):
        """三级标题。"""
        self.set_font('Hei', '', 11)
        self.set_text_color(*COLOR_TERTIARY)
        self.cell(0, 7, title, new_x='LMARGIN', new_y='NEXT')
        self.ln(0.5)
        self.set_text_color(0, 0, 0)

    def paragraph(self, text, indent=0):
        """正文段落。"""
        self.set_x(self.l_margin + indent)
        self.set_font('Song', '', 10.5)
        self.set_text_color(*COLOR_TEXT)
        self.multi_cell(self.w - self.l_margin - self.r_margin - indent, 6.0, text)
        self.ln(1.5)
        self.set_text_color(0, 0, 0)

    def bullet(self, text, indent=5):
        """项目符号列表。"""
        self.set_x(self.l_margin + indent)
        self.set_font('Song', '', 10.5)
        self.set_text_color(*COLOR_TEXT)
        self.multi_cell(self.w - self.l_margin - self.r_margin - indent, 6.0, f'· {text}')
        self.ln(0.5)
        self.set_text_color(0, 0, 0)

    def quote(self, text):
        """引用块。"""
        self.set_fill_color(*COLOR_LIGHT_BG)
        self.set_draw_color(*COLOR_PRIMARY)
        self.set_line_width(0.6)
        self.set_x(self.l_margin + 3)
        y_start = self.get_y()
        self.set_font('Song', '', 9.5)
        self.set_text_color(*COLOR_TEXT)
        self.multi_cell(self.w - self.l_margin - self.r_margin - 8, 5.5, text)
        y_end = self.get_y()
        self.line(self.l_margin + 3, y_start, self.l_margin + 3, y_end)
        self.ln(2)
        self.set_text_color(0, 0, 0)

    def info_block(self, items):
        """信息块。"""
        for label, value in items:
            self.set_font('Hei', '', 10.5)
            self.set_text_color(*COLOR_PRIMARY)
            self.cell(25, 6, label, new_x='RIGHT', new_y='TOP')
            self.set_font('Song', '', 10.5)
            self.set_text_color(*COLOR_TEXT)
            self.multi_cell(self.w - self.l_margin - self.r_margin - 25, 6, str(value))
            self.ln(0.5)
        self.ln(2)
        self.set_text_color(0, 0, 0)

    def table(self, headers, rows, col_widths=None):
        """表格。"""
        if col_widths is None:
            col_widths = [(self.w - self.l_margin - self.r_margin) / len(headers)] * len(headers)

        self.set_font('Hei', '', 9)
        self.set_fill_color(*COLOR_TABLE_HEADER)
        self.set_text_color(255, 255, 255)
        self.set_draw_color(*COLOR_TABLE_LINE)
        self.set_line_width(0.3)
        for h, w in zip(headers, col_widths):
            self.cell(w, 7, str(h), border=1, fill=True, align='C')
        self.ln()

        self.set_font('Song', '', 9)
        self.set_text_color(*COLOR_TEXT)
        for i, row in enumerate(rows):
            if i % 2 == 1:
                self.set_fill_color(*COLOR_LIGHT_BG)
            else:
                self.set_fill_color(255, 255, 255)
            max_h = 7
            x_start = self.get_x()
            y_start = self.get_y()
            for text, w in zip(row, col_widths):
                lines = max(1, len(str(text)) / max(1, w / 2.3) + 0.5)
                h = min(lines * 4.5, 20)
                max_h = max(max_h, h)
            for text, w in zip(row, col_widths):
                self.multi_cell(w, max_h / max(1, len(str(text)) / max(1, w / 2.3) + 0.5), str(text), border=1, fill=True, align='L')
                x_start += w
                self.set_xy(x_start, y_start)
            self.ln(max_h)
        self.set_text_color(0, 0, 0)
        self.ln(2)
