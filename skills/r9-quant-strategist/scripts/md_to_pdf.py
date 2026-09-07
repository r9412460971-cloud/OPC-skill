#!/usr/bin/env python3
"""
将 Markdown 报告转换为 PDF
用法：
    python md_to_pdf.py <markdown文件> [--output pdf路径]
示例：
    python md_to_pdf.py /tmp/r9-test/备案追踪_501210_2026Q1.md
"""

import argparse
import os
import tempfile
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright


def parse_args():
    parser = argparse.ArgumentParser(description="Markdown 转 PDF")
    parser.add_argument("md_file", help="Markdown 文件路径")
    parser.add_argument("--output", default=None, help="输出 PDF 路径，默认与 md 文件同名")
    return parser.parse_args()


def get_font_css():
    """生成中文字体 CSS"""
    # 优先使用系统已安装的中文字体
    font_family = "'PingFang SC', 'Noto Sans CJK SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'STHeiti', sans-serif"

    return """
    <style>
        body {
            font-family: """ + font_family + """;
            font-size: 11pt;
            line-height: 1.6;
            color: #1a1a1a;
            max-width: 210mm;
            margin: 20mm auto;
            padding: 0 15mm;
        }
        h1 {
            font-size: 20pt;
            color: #0f172a;
            border-bottom: 2px solid #1e40af;
            padding-bottom: 8px;
            margin-top: 24pt;
        }
        h2 {
            font-size: 15pt;
            color: #1e3a8a;
            margin-top: 20pt;
            border-left: 4px solid #3b82f6;
            padding-left: 10px;
        }
        h3 {
            font-size: 13pt;
            color: #334155;
            margin-top: 16pt;
        }
        table {
            border-collapse: collapse;
            width: 100%;
            margin: 12pt 0;
            font-size: 9.5pt;
        }
        th, td {
            border: 1px solid #cbd5e1;
            padding: 6px 8px;
            text-align: left;
        }
        th {
            background-color: #f1f5f9;
            font-weight: 600;
        }
        tr:nth-child(even) {
            background-color: #f8fafc;
        }
        code {
            background-color: #f1f5f9;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: 'SF Mono', Monaco, monospace;
        }
        blockquote {
            border-left: 4px solid #3b82f6;
            margin: 12pt 0;
            padding: 8px 16px;
            background-color: #f8fafc;
            color: #475569;
        }
        ul, ol {
            margin: 8pt 0;
            padding-left: 20pt;
        }
        li {
            margin: 4pt 0;
        }
        strong {
            color: #0f172a;
        }
        .page-break {
            page-break-after: always;
        }
    </style>
    """


def md_to_pdf(md_file: str, output_path: str = None):
    md_path = Path(md_file)
    if output_path is None:
        output_path = md_path.with_suffix(".pdf")
    else:
        output_path = Path(output_path)

    if not md_path.exists():
        raise FileNotFoundError(f"Markdown 文件不存在：{md_path}")

    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    # Markdown 转 HTML
    html_body = markdown.markdown(md_content, extensions=["tables", "fenced_code"])

    # 构建完整 HTML
    html = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        {get_font_css()}
    </head>
    <body>
        {html_body}
    </body>
    </html>
    """

    # 临时 HTML 文件
    with tempfile.NamedTemporaryFile("w", suffix=".html", encoding="utf-8", delete=False) as tmp:
        tmp.write(html)
        tmp_html = tmp.name

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file://{tmp_html}", wait_until="networkidle")
            page.pdf(
                path=str(output_path),
                format="A4",
                margin={"top": "15mm", "bottom": "15mm", "left": "15mm", "right": "15mm"},
                print_background=True,
            )
            browser.close()
    finally:
        os.unlink(tmp_html)

    print(f"PDF 已生成：{output_path}")


def main():
    args = parse_args()
    md_to_pdf(args.md_file, args.output)


if __name__ == "__main__":
    main()
