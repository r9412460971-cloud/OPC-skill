#!/usr/bin/env python3
"""
主动管理基金调仓有效性验证报告 Markdown → PDF 转换脚本 (WeasyPrint版)
用法: python md_to_pdf.py input.md output.pdf [--title "报告标题"] [--author "作者"]

依赖: pip install weasyprint markdown --break-system-packages
"""

import sys
import os
import re
import argparse
import markdown

# ── CSS 样式 ──
CSS_TEMPLATE = """
@page {
    size: A4;
    margin: 25mm 20mm 20mm 20mm;

    @top-center {
        content: "HEADER_TEXT";
        font-family: "Droid Sans Fallback", Helvetica, Arial, sans-serif;
        font-size: 8pt;
        color: #95a5a6;
        border-bottom: 0.5pt solid #ecf0f1;
        padding-bottom: 3mm;
    }

    @bottom-center {
        content: "第 " counter(page) " 页";
        font-family: "Droid Sans Fallback", Helvetica, Arial, sans-serif;
        font-size: 8pt;
        color: #95a5a6;
        border-top: 0.8pt solid #1a5276;
        padding-top: 2mm;
    }
}

@page :first {
    @top-center { content: none; }
    @bottom-center { content: none; }
}

body {
    font-family: "Droid Sans Fallback", Helvetica, Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.75;
    color: #2c3e50;
    text-align: justify;
}

/* 封面 */
.cover {
    page-break-after: always;
    text-align: center;
    padding-top: 40%;
}
.cover h1 {
    font-size: 26pt;
    color: #1a5276;
    margin-bottom: 8mm;
    font-weight: bold;
    letter-spacing: 1pt;
}
.cover .subtitle {
    font-size: 13pt;
    color: #95a5a6;
    margin-bottom: 6mm;
}
.cover .meta {
    font-size: 10.5pt;
    color: #95a5a6;
    margin-bottom: 4mm;
}
.cover .divider {
    width: 60%;
    margin: 8mm auto;
    border: none;
    border-top: 1.5pt solid #1a5276;
}

/* 一级标题 */
h1 {
    font-size: 18pt;
    color: #1a5276;
    margin-top: 14mm;
    margin-bottom: 6mm;
    padding-bottom: 3mm;
    border-bottom: 2pt solid #1a5276;
    page-break-before: always;
    font-weight: bold;
}

/* 二级标题 */
h2 {
    font-size: 13pt;
    color: #1e8449;
    margin-top: 9mm;
    margin-bottom: 4mm;
    font-weight: bold;
}

/* 三级标题 */
h3 {
    font-size: 11.5pt;
    color: #2e86c1;
    margin-top: 6mm;
    margin-bottom: 3mm;
    font-weight: bold;
}

h4 {
    font-size: 10.5pt;
    color: #5b2c6f;
    margin-top: 5mm;
    margin-bottom: 2mm;
    font-weight: bold;
}

/* 段落 */
p {
    margin-top: 1.5mm;
    margin-bottom: 1.5mm;
    orphans: 3;
    widows: 3;
}

/* 引用块 */
blockquote {
    margin: 4mm 0;
    padding: 4mm 4mm 4mm 10mm;
    background: #f8f9fa;
    border-left: 3pt solid #1a5276;
    color: #5d6d7e;
    font-size: 10pt;
}
blockquote p {
    margin: 1mm 0;
}

/* 粗体 */
strong, b {
    font-weight: bold;
    color: #1a252f;
}

/* 行内代码 */
code {
    font-family: "Courier New", Courier, monospace;
    background: #fdf2e9;
    color: #c0392b;
    padding: 0.5mm 1.5mm;
    border-radius: 2pt;
    font-size: 9.5pt;
}

/* 表格 */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 4mm 0;
    font-size: 9pt;
}
thead th {
    background: #1a5276;
    color: white;
    padding: 2.5mm;
    text-align: left;
    font-weight: bold;
}
tbody td {
    padding: 2mm 2.5mm;
    border-bottom: 0.5pt solid #bdc3c7;
}
tbody tr:nth-child(even) {
    background: #f8f9fa;
}

/* 分隔线 */
hr {
    border: none;
    border-top: 0.5pt solid #bdc3c7;
    margin: 4mm 0;
}

/* 列表 */
ul, ol {
    margin: 2mm 0;
    padding-left: 8mm;
}
li {
    margin-bottom: 1mm;
}

/* 链接 */
a {
    color: #2e86c1;
    text-decoration: none;
}
"""


def md_to_html(md_text, title="调仓有效性验证报告",
               subtitle="主动管理基金调仓有效性验证",
               meta_line="", author="R9（资产配置研习社）"):
    """将 Markdown 转为带封面的 HTML"""

    # 用 markdown 库转换正文
    html_body = markdown.markdown(
        md_text,
        extensions=['tables', 'fenced_code', 'nl2br'],
        output_format='html5'
    )

    # 移除正文中的第一个 h1（会用在封面上）
    first_h1_match = re.search(r'<h1>(.*?)</h1>', html_body)
    if first_h1_match:
        extracted_title = first_h1_match.group(1)
        if not title or title == "调仓有效性验证报告":
            title = extracted_title
        html_body = html_body.replace(first_h1_match.group(0), '', 1)

    # 替换 CSS 中的页眉占位符
    css = CSS_TEMPLATE.replace("HEADER_TEXT", f"{title}  |  主动管理基金调仓有效性验证")

    # 构建封面
    cover_html = f"""
    <div class="cover">
        <h1 style="page-break-before: avoid; border: none;">{title}</h1>
        <div class="subtitle">{subtitle}</div>
        {"<div class='meta'>" + meta_line + "</div>" if meta_line else ""}
        <hr class="divider">
        <div class="meta">作者: {author}</div>
    </div>
    """

    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <style>{css}</style>
</head>
<body>
{cover_html}
{html_body}
</body>
</html>"""

    return full_html


def main():
    parser = argparse.ArgumentParser(description="调仓有效性验证报告 Markdown → PDF")
    parser.add_argument("input", help="输入的 Markdown 文件路径")
    parser.add_argument("output", help="输出的 PDF 文件路径")
    parser.add_argument("--title", default=None, help="报告标题")
    parser.add_argument("--author", default="R9（资产配置研习社）", help="作者名")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        md_text = f.read()

    # 提取元信息
    meta_line = ""
    for line in md_text.split("\n"):
        stripped = line.strip().lstrip(">").strip()
        if "基金代码" in stripped or "研究时间" in stripped or "分析窗口" in stripped:
            meta_line = stripped
            break

    html = md_to_html(
        md_text,
        title=args.title or "调仓有效性验证报告",
        meta_line=meta_line,
        author=args.author
    )

    # 保存中间 HTML（便于调试）
    html_path = args.output.replace('.pdf', '.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[OK] HTML 已生成: {html_path}")

    # 转 PDF
    try:
        from weasyprint import HTML
        HTML(string=html).write_pdf(args.output)
    except Exception as e:
        print(f"[ERROR] WeasyPrint 转 PDF 失败: {e}")
        print("[提示] macOS 用户可尝试安装 Playwright 版本: scripts/md_to_pdf_playwright.py")
        sys.exit(1)

    size_kb = os.path.getsize(args.output) / 1024
    print(f"[OK] PDF 已生成: {args.output} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
