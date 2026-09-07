#!/usr/bin/env python3
"""
横纵分析法报告 Markdown → PDF 转换脚本 (Playwright 备选版)
当 WeasyPrint 因缺少系统库(pango)无法使用时，可用此脚本替代。

用法: python md_to_pdf_playwright.py input.md output.pdf [--title "报告标题"] [--author "作者"]

依赖: pip install markdown playwright
      playwright install chromium
"""

import sys
import os
import re
import argparse
import markdown


def md_to_pdf(md_path: str, pdf_path: str, title: str = None, author: str = "R9（资产配置研习社）"):
    """将Markdown文件转换为PDF"""
    
    # 读取Markdown
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()
    
    # 转换为HTML
    md = markdown.Markdown(extensions=['tables', 'fenced_code', 'toc'])
    html_body = md.convert(md_text)
    
    # 提取第一个h1作为封面标题
    h1_match = re.search(r'<h1>(.*?)</h1>', html_body)
    cover_title = h1_match.group(1) if h1_match else (title or "横纵分析报告")
    # 移除正文中的第一个h1（用于封面）
    html_body_for_content = re.sub(r'<h1>.*?</h1>', '', html_body, count=1)
    
    # 构建CSS
    css = """
    @page {
        size: A4;
        margin: 25mm 20mm 20mm 20mm;
    }
    
    body {
        font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "WenQuanYi Micro Hei", "Droid Sans Fallback", sans-serif;
        font-size: 10.5pt;
        line-height: 1.75;
        color: #2c3e50;
        text-align: justify;
    }
    
    .cover {
        text-align: center;
        padding-top: 120px;
        page-break-after: always;
    }
    .cover h1 {
        font-size: 28pt;
        color: #1a5276;
        margin-bottom: 20px;
        line-height: 1.3;
    }
    .cover .subtitle {
        font-size: 16pt;
        color: #5b2c6f;
        margin-bottom: 40px;
    }
    .cover .meta {
        font-size: 11pt;
        color: #666;
        margin-top: 60px;
    }
    .cover .divider {
        width: 80px;
        height: 3px;
        background: #1a5276;
        margin: 30px auto;
    }
    
    h1 {
        font-size: 20pt;
        color: #1a5276;
        margin-top: 40px;
        margin-bottom: 20px;
        page-break-before: always;
    }
    h1:first-of-type {
        page-break-before: auto;
    }
    h2 {
        font-size: 15pt;
        color: #1e8449;
        margin-top: 30px;
        margin-bottom: 15px;
    }
    h3 {
        font-size: 12pt;
        color: #2e86c1;
        margin-top: 20px;
        margin-bottom: 10px;
    }
    h4 {
        font-size: 11pt;
        color: #5b2c6f;
        margin-top: 15px;
        margin-bottom: 8px;
    }
    
    p {
        margin: 10px 0;
        text-indent: 0;
    }
    
    blockquote {
        border-left: 3pt solid #1a5276;
        background: #f8f9f9;
        padding: 10px 15px;
        margin: 15px 0;
        color: #555;
    }
    blockquote p {
        margin: 5px 0;
    }
    
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 15px 0;
        font-size: 9.5pt;
    }
    th {
        background: #1a5276;
        color: white;
        padding: 8px;
        text-align: left;
    }
    td {
        padding: 8px;
        border-bottom: 1px solid #ddd;
    }
    tr:nth-child(even) {
        background: #f8f9f9;
    }
    
    ul, ol {
        margin: 10px 0;
        padding-left: 25px;
    }
    li {
        margin: 5px 0;
    }
    
    strong {
        color: #1a5276;
    }
    
    .toc {
        page-break-after: always;
    }
    .toc h2 {
        text-align: center;
        color: #1a5276;
    }
    .toc ul {
        list-style: none;
        padding-left: 0;
    }
    .toc li {
        padding: 5px 0;
        border-bottom: 1px dotted #ddd;
    }
    """
    
    # 生成目录
    headings = re.findall(r'<h([2-3])>(.*?)</h[2-3]>', html_body_for_content)
    toc_items = []
    for level, text in headings:
        indent = "&nbsp;&nbsp;&nbsp;&nbsp;" if level == "3" else ""
        toc_items.append(f"<li>{indent}{text}</li>")
    toc_html = "<div class='toc'><h2>目录</h2><ul>" + "".join(toc_items) + "</ul></div>" if toc_items else ""
    
    # 提取元信息（如存在）
    meta_match = re.search(r'<blockquote>\s*<p>研究时间：(.*?)</p>\s*</blockquote>', html_body_for_content)
    meta_info = meta_match.group(1) if meta_match else ""
    
    study_time = ""
    if "研究时间" in meta_info:
        study_time = re.search(r'研究时间：([^|]+)', meta_info)
        study_time = study_time.group(1).strip() if study_time else ""
    
    html = f"""<!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <title>{cover_title}</title>
    <style>{css}</style>
    </head>
    <body>
    <div class="cover">
        <h1>{cover_title}</h1>
        <div class="subtitle">横纵分析法深度研究报告</div>
        <div class="divider"></div>
        <div class="meta">
            作者：{author}<br>
            {f'研究时间：{study_time}' if study_time else ''}
        </div>
    </div>
    {toc_html}
    {html_body_for_content}
    </body>
    </html>
    """
    
    html_path = md_path.replace(".md", "_playwright.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"[OK] HTML已生成: {html_path}")
    
    # 用Playwright生成PDF
    from playwright.sync_api import sync_playwright
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"file://{os.path.abspath(html_path)}")
        page.wait_for_load_state("networkidle")
        page.pdf(
            path=pdf_path,
            format="A4",
            margin={"top": "25mm", "right": "20mm", "bottom": "20mm", "left": "20mm"},
            print_background=True,
            display_header_footer=True,
            header_template=f'<div style="font-size:8px; color:#95a5a6; width:100%; text-align:center; padding:0 20mm; border-bottom:0.5pt solid #ecf0f1; padding-bottom:3mm;">{cover_title} | 横纵分析法深度研究报告</div>',
            footer_template='<div style="font-size:9px; color:#666; width:100%; text-align:center; padding:0 20mm;"><span class="pageNumber"></span> / <span class="totalPages"></span></div>'
        )
        browser.close()
    
    print(f"[OK] PDF已生成: {pdf_path}")


def main():
    parser = argparse.ArgumentParser(
        description="横纵分析法报告 Markdown → PDF 转换 (Playwright版)",
        epilog="当 WeasyPrint 不可用时使用此备选方案"
    )
    parser.add_argument("input", help="输入Markdown文件路径")
    parser.add_argument("output", help="输出PDF文件路径")
    parser.add_argument("--title", "-t", default=None, help="报告标题")
    parser.add_argument("--author", "-a", default="R9（资产配置研习社）", help="作者名称")
    
    args = parser.parse_args()
    
    md_to_pdf(args.input, args.output, args.title, args.author)


if __name__ == "__main__":
    main()
