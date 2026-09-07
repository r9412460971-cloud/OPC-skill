#!/usr/bin/env python3
"""
Skill-Zero 深度评估报告生成器
对指定 skill 按 evaluation-framework 的 6 维度做人工评判，输出 PDF。
"""
import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_DIR = "/Users/r9/.opc_fonts"
pdfmetrics.registerFont(TTFont("Kaiti", os.path.join(FONT_DIR, "KaitiSC-Regular.ttf")))

# --------------------------- 评估数据 ---------------------------
CRITERIA = {
    "触发设计": {
        "weight": 0.20,
        "desc": "触发词是否覆盖真实用户表达；description 是否让路由准确识别；是否易与其他 skill 混淆或漏触发。",
    },
    "功能价值": {
        "weight": 0.25,
        "desc": "解决的问题是否明确具体；在 R9 体系内是否有独特价值；是否存在可被替代或合并的冗余。",
    },
    "内容质量": {
        "weight": 0.25,
        "desc": "SKILL.md 指令是否清晰可执行；示例是否充分贴近真实场景；是否给出足够判断标准和边界条件。",
    },
    "结构规范": {
        "weight": 0.15,
        "desc": "是否符合 skill-creator 目录与 frontmatter 规范；是否遵循渐进式披露；是否有冗余文件。",
    },
    "依赖维护": {
        "weight": 0.10,
        "desc": "外部依赖是否最小化；脚本是否经过测试；更新成本是否可控。",
    },
    "体系协同": {
        "weight": 0.05,
        "desc": "与上下游 skill 衔接是否自然；是否引用基础设施 skill；是否避免能力重复或真空。",
    },
}

SKILLS = [
    {
        "name": "roll-forward",
        "scope": ".kimi",
        "scores": {"触发设计": 4.0, "功能价值": 4.0, "内容质量": 3.5, "结构规范": 4.0, "依赖维护": 4.0, "体系协同": 2.5},
        "strengths": [
            "问题定义极清晰：给出余额滚动的标准公式 X+A+B−C−D+E+F=Y。",
            "输出要求明确：必须 foot，不能 plug，体现审计级严谨。",
            "结构极简，符合渐进式披露。",
        ],
        "weaknesses": [
            "缺少完整示例：没有给出一个带数字的 roll-forward 样例。",
            "未引用 R9 基础设施：如 xlsx-author 可用于输出表格。",
            "未说明如何处理多币种、多 entity、合并报表等边界。",
        ],
        "opportunities": [
            "增加一个示例（含 Beginning/Additions/Accruals/Reversals/Payments 等真实数字）。",
            "与 gl-recon、accrual-schedule 形成链接，构建月结工具链。",
        ],
        "risks": [
            "用户首次使用时不知道如何提供输入，可能产生大量反问。",
        ],
    },
    {
        "name": "fund-advisor-assistant",
        "scope": ".kimi",
        "scores": {"触发设计": 4.0, "功能价值": 4.0, "内容质量": 4.0, "结构规范": 4.0, "依赖维护": 3.5, "体系协同": 4.5},
        "strengths": [
            "角色定义、工作流、配置规则、话术模板、决策树一应俱全。",
            "明确映射到 R9 现有能力：china-market-data、fund-r9alpha-evaluation 等。",
            "补全 frontmatter 后触发场景清晰。",
        ],
        "weaknesses": [
            "与 fund-advisor-strategy、post-investment-companion 等功能边界不够清晰。",
            "话术模板较通用，缺少高净值客户、老年客户等细分场景。",
            "决策树是 ASCII 图，可读性一般，建议改为表格或流程描述。",
        ],
        "opportunities": [
            "与 fund-advisor-strategy 做能力拆分说明，避免重复触发。",
            "增加 2–3 个完整对话示例（客户画像 → 方案 → 风险揭示）。",
        ],
        "risks": [
            "功能范围过宽，容易与多个 fund 相关 skill 产生路由竞争。",
        ],
    },
    {
        "name": "r9-channel-router",
        "scope": ".kimi",
        "scores": {"触发设计": 5.0, "功能价值": 5.0, "内容质量": 4.5, "结构规范": 4.0, "依赖维护": 4.0, "体系协同": 4.5},
        "strengths": [
            "description 触发词覆盖极广，四大渠道信号词详尽。",
            "跨渠道优先级规则清晰，模糊需求有默认处理。",
            "明确列出通用基础设施 skill，协同设计好。",
        ],
        "weaknesses": [
            "description 使用 YAML 多行字符串，对路由模型可能不如单行稳定。",
            "缺少一个真实的用户输入 → 路由决策 → 子 skill 调用的完整示例。",
            "与 r9-workbench 的关系未充分说明。",
        ],
        "opportunities": [
            "将 description 改为单行，提升路由稳定性。",
            "增加一个「用户说…→ 识别到…→ 调用…」的端到端示例。",
            "说明与 r9-workbench 的调用关系。",
        ],
        "risks": [
            "若 r9-workbench 同时触发，可能出现双重路由冲突。",
        ],
    },
    {
        "name": "variance-commentary",
        "scope": ".kimi",
        "scores": {"触发设计": 4.0, "功能价值": 4.0, "内容质量": 3.0, "结构规范": 4.0, "依赖维护": 4.0, "体系协同": 2.0},
        "strengths": [
            "给出了清晰的阈值规则和「driver explains why, not what」原则。",
            "输出格式明确：commentary table + narrative。",
            "结构简洁，易于快速加载。",
        ],
        "weaknesses": [
            "没有示例：缺少一个真实科目的 commentary 样例。",
            "未说明如何与内部 GL MCP 交互，也没有引用相关 skill。",
            "对「always comment」列表的维护未做说明。",
        ],
        "opportunities": [
            "增加 1–2 个完整示例（如 Revenue、Cloud spend）。",
            "链接 gl-recon、break-trace 等基金运营 skill。",
        ],
        "risks": [
            "没有示例导致首次使用质量不稳定。",
        ],
    },
    {
        "name": "grill-me",
        "scope": ".claude",
        "scores": {"触发设计": 2.0, "功能价值": 2.0, "内容质量": 1.0, "结构规范": 3.0, "依赖维护": 3.0, "体系协同": 1.0},
        "strengths": [
            "有 frontmatter，且声明 disable-model-invocation。",
        ],
        "weaknesses": [
            "description 只有一句话，没有触发词。",
            "正文只有 4 个单词「Run a /grilling session.」，没有任何执行指导。",
            "未说明 /grilling session 是什么、何时使用、输出什么。",
            "与 R9 体系无关联。",
        ],
        "opportunities": [
            "重写 description，增加触发词如「挑战我的想法」「压力测试方案」「拷问我的计划」。",
            "补充会话流程、提问策略、终止条件、输出格式。",
            "如与 R9 无关，建议迁移到个人 skill 区或补充 OPC 战略评审场景。",
        ],
        "risks": [
            "当前状态下几乎无法被有效触发和使用，属于僵尸 skill。",
        ],
    },
]


def calc_total(skill):
    return round(sum(skill["scores"][k] * CRITERIA[k]["weight"] for k in CRITERIA), 2)


# --------------------------- PDF 生成 ---------------------------
def md_to_para(text, style):
    """简单 markdown → reportlab Paragraph 标签"""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # 加粗
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # 代码
    text = re.sub(r"`(.+?)`", r"<font face='Courier' size=8>\1</font>", text)
    return Paragraph(text, style)


def build_pdf(output_path):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=1.8 * cm,
        leftMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ChineseTitle", fontName="Kaiti", fontSize=20, leading=26, alignment=1, spaceAfter=14))
    styles.add(ParagraphStyle(name="H1", fontName="Kaiti", fontSize=16, leading=22, spaceAfter=10, spaceBefore=14, textColor=colors.HexColor("#1a5276")))
    styles.add(ParagraphStyle(name="H2", fontName="Kaiti", fontSize=13, leading=18, spaceAfter=8, spaceBefore=12, textColor=colors.HexColor("#2874a6")))
    styles.add(ParagraphStyle(name="Body", fontName="Kaiti", fontSize=10, leading=15, spaceAfter=6))
    styles.add(ParagraphStyle(name="Small", fontName="Kaiti", fontSize=9, leading=13, spaceAfter=4))
    styles.add(ParagraphStyle(name="TableHeader", fontName="Kaiti", fontSize=9, leading=13, alignment=1, textColor=colors.white))

    story = []

    # 封面
    story.append(Spacer(1, 5 * cm))
    story.append(Paragraph("Skill-Zero 深度评估报告", styles["ChineseTitle"]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(f"评估对象：5 个低分 Skill", styles["Body"]))
    story.append(Paragraph(f"评估时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Body"]))
    story.append(Paragraph("评估标准：Skill-Zero 六维度评估框架", styles["Body"]))
    story.append(PageBreak())

    # 评价标准
    story.append(Paragraph("一、评价标准", styles["H1"]))
    story.append(Paragraph("本报告基于 Skill-Zero 评估框架，从六个维度对每个 skill 进行 1–5 分评分。", styles["Body"]))
    story.append(Spacer(1, 0.3 * cm))

    data = [["维度", "权重", "说明"]]
    for k, v in CRITERIA.items():
        data.append([k, f"{v['weight']:.0%}", v["desc"]])
    table = Table(data, colWidths=[3 * cm, 2 * cm, 10.5 * cm], repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Kaiti"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2874a6")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (1, -1), "CENTER"),
        ("ALIGN", (2, 1), (2, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("LEFTPADDING", (2, 0), (2, -1), 6),
        ("RIGHTPADDING", (2, 0), (2, -1), 6),
    ]))
    story.append(table)

    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("评分口径：5 分标杆、4 分优秀、3 分合格、2 分需明显改进、1 分存在结构性缺陷。", styles["Small"]))
    story.append(PageBreak())

    # 横向对比表
    story.append(Paragraph("二、横向评分总览", styles["H1"]))
    data = [["Skill", "触发", "价值", "内容", "结构", "维护", "协同", "总分"]]
    for s in SKILLS:
        sc = s["scores"]
        data.append([
            s["name"],
            f"{sc['触发设计']:.1f}", f"{sc['功能价值']:.1f}", f"{sc['内容质量']:.1f}",
            f"{sc['结构规范']:.1f}", f"{sc['依赖维护']:.1f}", f"{sc['体系协同']:.1f}",
            f"{calc_total(s):.2f}",
        ])
    table = Table(data, colWidths=[4 * cm] + [1.7 * cm] * 7, repeatRows=1)
    style_cmds = [
        ("FONTNAME", (0, 0), (-1, 0), "Kaiti"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2874a6")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 1), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
    ]
    for i, row in enumerate(data[1:], start=1):
        total = float(row[7])
        if total >= 4.2:
            bg = colors.HexColor("#d4edda")
        elif total >= 3.5:
            bg = colors.HexColor("#fff3cd")
        elif total >= 2.5:
            bg = colors.HexColor("#ffeeba")
        else:
            bg = colors.HexColor("#f8d7da")
        style_cmds.append(("BACKGROUND", (0, i), (-1, i), bg))
    table.setStyle(TableStyle(style_cmds))
    story.append(table)
    story.append(PageBreak())

    # 每个 skill 的详细评估
    story.append(Paragraph("三、逐 Skill 深度评估", styles["H1"]))

    for s in SKILLS:
        story.append(Paragraph(f"{s['name']}", styles["H2"]))
        story.append(Paragraph(f"Scope: {s['scope']} | 总分: {calc_total(s):.2f}/5", styles["Body"]))

        # 评分条
        sc = s["scores"]
        data2 = [["维度", "得分"]]
        for k in CRITERIA:
            data2.append([k, f"{sc[k]:.1f}"])
        t2 = Table(data2, colWidths=[3 * cm, 2 * cm])
        t2.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Kaiti"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d5dbdb")),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ]))
        story.append(t2)
        story.append(Spacer(1, 0.3 * cm))

        for sec, title in [("strengths", "优势"), ("weaknesses", "劣势"), ("opportunities", "机会"), ("risks", "风险")]:
            story.append(Paragraph(title, styles["H2"]))
            for item in s[sec]:
                story.append(Paragraph(f"• {item}", styles["Body"]))
        story.append(Spacer(1, 0.5 * cm))

    story.append(PageBreak())

    # 优先级改进清单
    story.append(Paragraph("四、优先级改进清单", styles["H1"]))
    actions = [
        ("【高】grill-me 重写", "description 和正文几乎为空，需补充触发词、流程、输出格式，否则建议下线或移出 .kimi/.claude skills。"),
        ("【高】roll-forward / variance-commentary 补示例", "两个 skill 都缺少带数字的完整示例，导致首次使用质量不稳定。"),
        ("【中】fund-advisor-assistant 边界说明", "明确与 fund-advisor-strategy、post-investment-companion 的分工，避免路由竞争。"),
        ("【中】r9-channel-router 说明与 r9-workbench 关系", "避免双重路由冲突；description 建议改为单行。"),
        ("【低】运营类 skill 体系化链接", "roll-forward、variance-commentary 可与 gl-recon、break-trace、accrual-schedule 形成月结工具链互引。"),
    ]
    for title, detail in actions:
        story.append(Paragraph(title, styles["H2"]))
        story.append(Paragraph(detail, styles["Body"]))

    doc.build(story)


if __name__ == "__main__":
    import re
    out = "/Users/r9/Skill_Zero_Deep_Evaluation_Report.pdf"
    build_pdf(out)
    print(f"报告已生成：{out}")
