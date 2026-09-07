#!/usr/bin/env python3
"""
Skill-Zero 全量评估脚本
扫描 .kimi/skills/ 和 .claude/skills/ 下的所有 skill，
输出一份 PDF 评估报告到 ~/Skill_Zero_Audit_Report.pdf
"""

import os
import re
import glob
from datetime import datetime
from collections import Counter

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# --------------------------- 字体注册 ---------------------------
FONT_DIR = "/Users/r9/.opc_fonts"
# reportlab 仅支持 TrueType 轮廓字体；本机可用中文字体为楷体
pdfmetrics.registerFont(TTFont("Kaiti", os.path.join(FONT_DIR, "KaitiSC-Regular.ttf")))

# --------------------------- 扫描目录 ---------------------------
SKILL_DIRS = [
    "/Users/r9/.kimi/skills",
    "/Users/r9/.claude/skills",
]

INFRA_SKILLS = {
    "china-market-data", "r9-rag-engine", "xlsx-author", "pptx-author",
    "skill-creator", "r9-workbench", "r9-opc-memory", "skill-zero",
}


def parse_frontmatter(text):
    """解析 YAML frontmatter，返回 {name, description, raw_frontmatter, body}"""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    fm = parts[1].strip()
    body = parts[2].strip()
    name = None
    desc = None
    for line in fm.splitlines():
        if line.lower().startswith("name:"):
            name = line.split(":", 1)[1].strip()
        elif line.lower().startswith("description:"):
            desc = line.split(":", 1)[1].strip()
    return {"name": name, "description": desc, "raw_frontmatter": fm, "body": body}


def count_chinese(text):
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def count_english_words(text):
    return len(re.findall(r"[a-zA-Z]+", text))


def extract_trigger_phrases(desc):
    """粗略估计触发词/短语数量：引号内内容 + 常见触发动词后的短语"""
    quoted = re.findall(r'["""]([^"""]+)["""]', desc)
    return len(quoted)


def has_workflow(body):
    return bool(re.search(r"^#{1,3}\s*(workflow|step \d|工作流程|步骤|流程)", body, re.M | re.I))


def has_examples(body):
    return bool(re.search(r"```|##\s*example|###\s*example|举例|示例", body, re.I))


def has_redundant_files(skill_path):
    redundant = {"README.md", "INSTALLATION_GUIDE.md", "QUICK_REFERENCE.md", "CHANGELOG.md"}
    found = []
    for root, dirs, files in os.walk(skill_path):
        # 排除 .skill 打包文件
        for f in files:
            if f in redundant or f.endswith(".skill"):
                found.append(f)
    return found


def references_infra(body, name):
    refs = [s for s in INFRA_SKILLS if s != name and s in body]
    return refs


def evaluate_skill(skill_path):
    skill_name = os.path.basename(os.path.normpath(skill_path))
    skill_md = os.path.join(skill_path, "SKILL.md")

    result = {
        "name": skill_name,
        "path": skill_path,
        "scope": ".kimi" if ".kimi/skills" in skill_path else ".claude",
        "has_skill_md": os.path.exists(skill_md),
        "frontmatter_ok": False,
        "name_in_fm": None,
        "description": "",
        "desc_len": 0,
        "desc_ch": 0,
        "desc_en": 0,
        "body_lines": 0,
        "body_words": 0,
        "h2_h3_count": 0,
        "trigger_phrases": 0,
        "has_workflow": False,
        "has_examples": False,
        "has_references": os.path.isdir(os.path.join(skill_path, "references")),
        "has_scripts": os.path.isdir(os.path.join(skill_path, "scripts")),
        "has_assets": os.path.isdir(os.path.join(skill_path, "assets")),
        "redundant_files": [],
        "infra_refs": [],
        "scores": {},
        "total": 0.0,
        "rank": 0,
    }

    if not result["has_skill_md"]:
        return result

    with open(skill_md, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    fm = parse_frontmatter(text)
    if not fm:
        return result

    result["frontmatter_ok"] = bool(fm["name"] and fm["description"])
    result["name_in_fm"] = fm["name"]
    result["description"] = fm["description"][:200]
    result["desc_len"] = len(fm["description"])
    result["desc_ch"] = count_chinese(fm["description"])
    result["desc_en"] = count_english_words(fm["description"])
    result["body_lines"] = len(fm["body"].splitlines())
    result["body_words"] = count_chinese(fm["body"]) + count_english_words(fm["body"])
    result["h2_h3_count"] = len(re.findall(r"^#{2,3}\s", fm["body"], re.M))
    result["trigger_phrases"] = extract_trigger_phrases(fm["description"])
    result["has_workflow"] = has_workflow(fm["body"])
    result["has_examples"] = has_examples(fm["body"])
    result["redundant_files"] = has_redundant_files(skill_path)
    result["infra_refs"] = references_infra(fm["body"], skill_name)

    # --------------------- 评分 ---------------------
    desc = fm["description"]
    body = fm["body"]

    # 1. 触发设计 (20%)
    s_trigger = 3
    if result["desc_len"] > 80:
        s_trigger += 1
    if result["trigger_phrases"] >= 3:
        s_trigger += 0.5
    if result["frontmatter_ok"]:
        s_trigger += 0.5
    s_trigger = min(5, max(1, s_trigger))

    # 2. 功能价值 (25%)
    s_value = 3
    if result["desc_len"] > 60 and ("用于" in desc or "Use when" in desc or "Triggers" in desc):
        s_value += 1
    if result["body_lines"] > 30:
        s_value += 0.5
    if result["scope"] == ".kimi" and skill_name in INFRA_SKILLS:
        s_value += 0.5
    s_value = min(5, max(1, s_value))

    # 3. 内容质量 (25%)
    s_content = 3
    if result["body_lines"] > 50:
        s_content += 0.5
    if result["body_lines"] > 120:
        s_content += 0.5
    if result["has_workflow"]:
        s_content += 0.5
    if result["has_examples"]:
        s_content += 0.5
    if result["h2_h3_count"] >= 3:
        s_content += 0.5
    s_content = min(5, max(1, s_content))

    # 4. 结构规范 (15%)
    s_struct = 3
    if result["frontmatter_ok"]:
        s_struct += 1
    if not result["redundant_files"]:
        s_struct += 0.5
    else:
        s_struct -= 1
    if result["has_references"] or result["has_scripts"] or result["has_assets"]:
        s_struct += 0.5
    s_struct = min(5, max(1, s_struct))

    # 5. 依赖与可维护性 (10%)
    s_maint = 3
    if result["has_scripts"]:
        s_maint += 0.5
    if "pip install" in body or "API Key" in body:
        s_maint -= 0.5
    if result["body_lines"] < 500:
        s_maint += 0.5
    s_maint = min(5, max(1, s_maint))

    # 6. 体系协同 (5%)
    s_eco = 3
    if result["infra_refs"]:
        s_eco += 1
    if skill_name in INFRA_SKILLS:
        s_eco += 0.5
    s_eco = min(5, max(1, s_eco))

    result["scores"] = {
        "触发设计": s_trigger,
        "功能价值": s_value,
        "内容质量": s_content,
        "结构规范": s_struct,
        "依赖维护": s_maint,
        "体系协同": s_eco,
    }
    weights = {"触发设计": 0.20, "功能价值": 0.25, "内容质量": 0.25,
               "结构规范": 0.15, "依赖维护": 0.10, "体系协同": 0.05}
    result["total"] = round(sum(result["scores"][k] * weights[k] for k in weights), 2)

    return result


def discover_skills():
    skills = []
    for base in SKILL_DIRS:
        if not os.path.isdir(base):
            continue
        for entry in sorted(os.listdir(base)):
            full = os.path.join(base, entry)
            if os.path.isdir(full) and os.path.exists(os.path.join(full, "SKILL.md")):
                skills.append(full)
    return skills


def score_to_color(score):
    if score >= 4.2:
        return colors.HexColor("#d4edda")
    elif score >= 3.5:
        return colors.HexColor("#fff3cd")
    elif score >= 2.5:
        return colors.HexColor("#ffeeba")
    else:
        return colors.HexColor("#f8d7da")


def build_pdf(results, output_path):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ChineseTitle", fontName="Kaiti", fontSize=22,
                              leading=28, alignment=1, spaceAfter=16))
    styles.add(ParagraphStyle(name="ChineseHeading", fontName="Kaiti", fontSize=14,
                              leading=20, spaceAfter=8, spaceBefore=12))
    styles.add(ParagraphStyle(name="ChineseBody", fontName="Kaiti", fontSize=10,
                              leading=15, spaceAfter=6))
    styles.add(ParagraphStyle(name="ChineseSmall", fontName="Kaiti", fontSize=8,
                              leading=12))
    styles.add(ParagraphStyle(name="ChineseTiny", fontName="Kaiti", fontSize=7,
                              leading=10))

    story = []

    # 封面
    story.append(Spacer(1, 4 * cm))
    story.append(Paragraph("Skill-Zero 全量 Skill 评估报告", styles["ChineseTitle"]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(f"评估时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["ChineseBody"]))
    story.append(Paragraph(f"评估范围：.kimi/skills/ + .claude/skills/", styles["ChineseBody"]))
    story.append(Paragraph(f"Skill 总数：{len(results)}", styles["ChineseBody"]))
    story.append(PageBreak())

    # 执行摘要
    story.append(Paragraph("一、执行摘要", styles["ChineseHeading"]))
    totals = [r["total"] for r in results if r["total"] > 0]
    avg = round(sum(totals) / len(totals), 2) if totals else 0
    top3 = sorted(results, key=lambda x: x["total"], reverse=True)[:3]
    bottom3 = sorted(results, key=lambda x: x["total"])[:3]

    summary = f"""
    本次共评估 {len(results)} 个 skill，平均得分 <b>{avg}/5</b>。<br/>
    评分基于 SKILL.md 的 frontmatter、正文结构、触发设计、示例完整性、基础设施引用等可量化指标，<br/>
    未做深度功能测试，结果供批量筛查与优先级排序参考。
    """
    story.append(Paragraph(summary, styles["ChineseBody"]))

    top3_str = ", ".join([f"{r['name']}({r['total']})" for r in top3])
    bottom3_str = ", ".join([f"{r['name']}({r['total']})" for r in bottom3])
    story.append(Paragraph(f"前三名：{top3_str}", styles["ChineseBody"]))
    story.append(Paragraph(f"后三名：{bottom3_str}", styles["ChineseBody"]))

    # 主要发现
    story.append(Paragraph("二、主要发现", styles["ChineseHeading"]))
    no_fm = [r["name"] for r in results if not r["frontmatter_ok"]]
    redundant = [r["name"] for r in results if r["redundant_files"]]
    no_workflow = [r["name"] for r in results if not r["has_workflow"]]
    no_examples = [r["name"] for r in results if not r["has_examples"]]
    no_infra = [r["name"] for r in results if r["scope"] == ".kimi" and not r["infra_refs"] and r["name"] not in INFRA_SKILLS]

    findings = [
        f"frontmatter 完整：{len(results) - len(no_fm)} / {len(results)}",
        f"包含 workflow：{len(results) - len(no_workflow)} / {len(results)}",
        f"包含示例/代码块：{len(results) - len(no_examples)} / {len(results)}",
        f"引用基础设施 skill：{len(results) - len(no_infra)} / {len([r for r in results if r['scope'] == '.kimi'])}",
        f"存在冗余文件：{len(redundant)} 个",
    ]
    for f in findings:
        story.append(Paragraph(f"• {f}", styles["ChineseBody"]))

    story.append(PageBreak())

    # 完整评分表
    story.append(Paragraph("三、完整评分表", styles["ChineseHeading"]))
    story.append(Paragraph("按总分降序排列；颜色越深表示得分越高。", styles["ChineseSmall"]))
    story.append(Spacer(1, 0.3 * cm))

    data = [["排名", "Skill", "触发", "价值", "内容", "结构", "维护", "协同", "总分", "Scope"]]
    for idx, r in enumerate(sorted(results, key=lambda x: x["total"], reverse=True), 1):
        s = r["scores"]
        if s:
            row = [
                str(idx), r["name"],
                f"{s['触发设计']:.1f}", f"{s['功能价值']:.1f}", f"{s['内容质量']:.1f}",
                f"{s['结构规范']:.1f}", f"{s['依赖维护']:.1f}", f"{s['体系协同']:.1f}",
                f"{r['total']:.2f}", r["scope"],
            ]
        else:
            row = [str(idx), r["name"], "—", "—", "—", "—", "—", "—", "N/A", r["scope"]]
        data.append(row)

    col_widths = [0.8 * cm, 4.0 * cm, 1.1 * cm, 1.1 * cm, 1.1 * cm, 1.1 * cm, 1.1 * cm, 1.1 * cm, 1.3 * cm, 1.2 * cm]
    table = Table(data, colWidths=col_widths, repeatRows=1)

    style_cmds = [
        ("FONTNAME", (0, 0), (-1, 0), "Kaiti"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9ecef")),
    ]
    for i, row in enumerate(data[1:], start=1):
        total_str = row[8]
        try:
            total = float(total_str)
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), score_to_color(total)))
        except ValueError:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f8d7da")))
    table.setStyle(TableStyle(style_cmds))
    story.append(table)

    story.append(PageBreak())

    # 详细问题清单
    story.append(Paragraph("四、需关注的问题清单", styles["ChineseHeading"]))

    issue_groups = [
        ("Frontmatter 不完整", no_fm),
        ("缺少 Workflow/步骤说明", no_workflow),
        ("缺少示例或代码块", no_examples),
        ("存在冗余文件", [f"{n} ({', '.join(r['redundant_files'][:2])})" for r in results if r["redundant_files"] for n in [r["name"]]]),
        (".kimi skill 未引用基础设施", no_infra[:20]),
    ]

    for title, items in issue_groups:
        story.append(Paragraph(title, styles["ChineseHeading"]))
        if not items:
            story.append(Paragraph("无", styles["ChineseBody"]))
        else:
            for item in items:
                story.append(Paragraph(f"• {item}", styles["ChineseBody"]))

    doc.build(story)


def main():
    skill_paths = discover_skills()
    print(f"发现 {len(skill_paths)} 个 skill")
    results = [evaluate_skill(p) for p in skill_paths]
    results.sort(key=lambda x: x["total"], reverse=True)
    for i, r in enumerate(results, 1):
        r["rank"] = i

    output = "/Users/r9/Skill_Zero_Audit_Report.pdf"
    build_pdf(results, output)
    print(f"报告已生成：{output}")

    # 控制台摘要
    print(f"\n平均分：{round(sum(r['total'] for r in results)/len(results), 2)}")
    print("Top 5:")
    for r in results[:5]:
        print(f"  {r['rank']:>3}. {r['name']:<45} {r['total']}")
    print("Bottom 5:")
    for r in results[-5:]:
        print(f"  {r['rank']:>3}. {r['name']:<45} {r['total']}")


if __name__ == "__main__":
    main()
