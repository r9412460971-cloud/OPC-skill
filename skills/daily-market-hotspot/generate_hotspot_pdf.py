#!/usr/bin/env python3
"""生成每日市场热点点评 PDF（R9 风格）。"""

import re
from pathlib import Path
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, ListFlowable, ListItem
)

OUTPUT_DIR = Path('/Users/r9/OPC/01_投研策略/研究报告')

# 注册中文字体（macOS 系统自带 TrueType 轮廓）
pdfmetrics.registerFont(TTFont('STHeiti', '/System/Library/Fonts/STHeiti Light.ttc'))
pdfmetrics.registerFont(TTFont('STHeiti-Bold', '/System/Library/Fonts/STHeiti Medium.ttc'))


def build_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='DocTitle',
        fontName='STHeiti-Bold',
        fontSize=22,
        leading=28,
        textColor=colors.HexColor('#003366'),
        alignment=1,  # center
        spaceAfter=16,
    ))
    styles.add(ParagraphStyle(
        name='R9Subtitle',
        fontName='STHeiti',
        fontSize=12,
        leading=18,
        textColor=colors.HexColor('#666666'),
        alignment=1,
        spaceAfter=24,
    ))
    styles.add(ParagraphStyle(
        name='R9H1',
        fontName='STHeiti-Bold',
        fontSize=18,
        leading=26,
        textColor=colors.HexColor('#003366'),
        spaceBefore=18,
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name='R9H2',
        fontName='STHeiti-Bold',
        fontSize=15,
        leading=22,
        textColor=colors.HexColor('#006699'),
        spaceBefore=14,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name='R9H3',
        fontName='STHeiti-Bold',
        fontSize=12,
        leading=18,
        textColor=colors.HexColor('#006699'),
        spaceBefore=10,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name='R9Body',
        fontName='STHeiti',
        fontSize=11,
        leading=19,
        spaceAfter=8,
        firstLineIndent=22,
    ))
    styles.add(ParagraphStyle(
        name='R9Bullet',
        fontName='STHeiti',
        fontSize=11,
        leading=19,
        leftIndent=22,
        bulletIndent=8,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name='R9Divider',
        fontName='STHeiti',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#999999'),
        alignment=1,
        spaceBefore=6,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name='R9Footer',
        fontName='STHeiti',
        fontSize=9,
        leading=14,
        textColor=colors.HexColor('#888888'),
        spaceBefore=20,
    ))
    return styles


def clean_text(text: str) -> str:
    """转义 XML 特殊字符。"""
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))


def generate_pdf(output_path=None):
    if output_path is None:
        output_path = OUTPUT_DIR / f'OPC_每日市场热点点评_{datetime.now().strftime("%Y%m%d")}_v1.pdf'
    output_path.parent.mkdir(parents=True, exist_ok=True)

    styles = build_styles()
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    story = []

    # 封面信息
    story.append(Spacer(1, 2 * cm))
    story.append(Paragraph('每日市场热点点评', styles['DocTitle']))
    story.append(Paragraph(f'{datetime.now().strftime("%Y年%m月%d日")}', styles['R9Subtitle']))
    story.append(Spacer(1, 1 * cm))

    # 文章正文
    story.append(PageBreak())
    story.append(Paragraph('机器人嗨了。', styles['R9H1']))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph('今日聚焦', styles['R9H2']))

    story.append(Paragraph('市场综述', styles['R9H3']))
    story.append(Paragraph(
        '7月3日，A股三大指数集体收红。沪指涨0.37%，深成指涨0.64%，创业板指涨0.07%。'
        '科创50跌0.59%，有点掉队。全市场超3800只个股上涨，160只涨停，赚钱效应还在。'
        '成交额约3.18万亿元，比前一交易日缩量2680亿。量能虽然缩了，但热点非常明确。',
        styles['R9Body']
    ))

    story.append(Paragraph('核心矛盾', styles['R9H3']))
    story.append(Paragraph(
        '今天市场的关键词就两个：机器人和黄金。',
        styles['R9Body']
    ))
    story.append(Paragraph(
        '机器人概念全面爆发，四十多只成分股涨停。催化很简单：宇树科技IPO注册获批了。'
        '从3月20日获受理到7月1日注册生效，只用了104天，创下科创板预先审阅机制最快纪录。'
        '这意味着A股"人形机器人第一股"真的要来了，产业链上下游都跟着嗨。',
        styles['R9Body']
    ))
    story.append(Paragraph(
        '另一边，贵金属板块强势领涨。COMEX黄金一度冲上4200美元/盎司。'
        '直接原因是美国6月非农只新增了5.7万个岗位，远低于预期，市场加息预期一下子降温，'
        '美元走弱，黄金自然就弹了。',
        styles['R9Body']
    ))
    story.append(Paragraph(
        '科技成长内部在分化。半导体、光刻胶、氟化工这些前期涨得猛的方向今天挨打了。'
        '多氟多、立昂微跌停，说明资金在科技内部也在做高低切。',
        styles['R9Body']
    ))

    story.append(Paragraph('—' * 30, styles['R9Divider']))

    story.append(Paragraph('重点新闻', styles['R9H3']))
    story.append(Paragraph(
        '机器人产业链今天是最靓的仔。宇树科技IPO获批不只是一只股票的事，'
        '它相当于给整个人形机器人板块打了一针强心剂。中信证券直接说，这标志着2026年人形机器人商业化元年正式开启。'
        '上游减速器、传感器、伺服电机这些核心零部件，被视为最先受益的环节。',
        styles['R9Body']
    ))
    story.append(Paragraph(
        '黄金股今天也集体暴走。招金黄金、赤峰黄金2连板，西部黄金、四川黄金等多股涨停。'
        '金价站上4200美元的背景下，黄金股的弹性被彻底激活。说白了，前期黄金板块调整了一段时间，'
        '今天借非农数据反弹，资金回流明显。',
        styles['R9Body']
    ))
    story.append(Paragraph(
        '不过另一边，半导体材料板块震荡下挫。光刻胶、电子特气方向领跌，多氟多触及跌停，'
        '容大感光、南大光电、华特气体大跌。这说明科技成长内部不再是齐涨齐跌，'
        '资金开始挑业绩、挑估值、挑位置。',
        styles['R9Body']
    ))
    story.append(Paragraph(
        '军工装备板块也表现活跃。商业航天概念集体爆发，铖昌科技4分钟封死涨停。'
        '军工板块上半年跌幅明显，目前估值已跌到相对低位，主题情绪一旦有催化，反弹力度会比较大。',
        styles['R9Body']
    ))
    story.append(Paragraph(
        '还有一个政策细节值得注意：7月6日起，沪深两市主板ST、*ST股票涨跌幅将由5%调整至10%。'
        '这个规则变化会影响ST股的交易生态，短期可能加大波动。',
        styles['R9Body']
    ))

    story.append(Paragraph('—' * 30, styles['R9Divider']))

    story.append(Paragraph('明日前瞻', styles['R9H3']))
    story.append(Paragraph(
        '下周一（7月6日），A股交易新规正式实施，主板ST/*ST涨跌幅限制扩至10%。'
        '另外，关注周末是否有新的政策或地缘消息。眼下市场处于科技股调整后的再平衡阶段，'
        '新主线的持续性还要观察。',
        styles['R9Body']
    ))

    story.append(Paragraph('—' * 30, styles['R9Divider']))

    story.append(Paragraph('全球市场', styles['R9H3']))
    story.append(Paragraph(
        '美股7月3日因独立日假期提前休市。港股恒指收涨1.28%，机器人、贵金属板块大涨，'
        '来福谐波涨近45%，赤峰黄金港股涨超19%。',
        styles['R9Body']
    ))

    story.append(Paragraph('数据来源：东方财富、财联社、同花顺', styles['R9Footer']))

    doc.build(story)
    return output_path


if __name__ == '__main__':
    path = generate_pdf()
    print(f"PDF 已生成：{path}")
