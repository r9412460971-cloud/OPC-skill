#!/usr/bin/env python3
"""
R9 OPC 中文 PDF 生成模板

使用说明：
1. 本脚本使用 fpdf2 + NotoSansCJKsc（思源黑体）生成中文 PDF。
2. 已内置 emoji 清洗逻辑，避免缺字/乱码。
3. 复制本脚本到任务目录后修改内容即可。

依赖安装：
    pip install fpdf2

字体来源：
    默认从 r9-opc-operations/assets/fonts/ 加载。
    如果 Skill 路径不可用，可改为 ~/.opc_fonts/ 下的同名文件。
"""

from fpdf import FPDF
from pathlib import Path
import re
import sys


def _find_skill_dir() -> Path:
    """尝试定位 r9-opc-operations skill 目录。"""
    candidates = [
        Path.home() / ".kimi" / "skills" / "r9-opc-operations",
        Path.home() / ".agents" / "skills" / "r9-opc-operations",
    ]
    for p in candidates:
        if (p / "SKILL.md").exists():
            return p
    return Path(__file__).resolve().parents[1]


SKILL_DIR = _find_skill_dir()
ASSETS_DIR = SKILL_DIR / "assets" / "fonts"
FALLBACK_DIR = Path.home() / ".opc_fonts"


def get_font_paths():
    """返回 (regular, bold) 字体路径，优先使用 skill assets，回退到 ~/.opc_fonts。"""
    regular = ASSETS_DIR / "NotoSansCJKsc-Regular.otf"
    bold = ASSETS_DIR / "NotoSansCJKsc-Bold.otf"
    if not regular.exists():
        regular = FALLBACK_DIR / "NotoSansCJKsc-Regular.otf"
        bold = FALLBACK_DIR / "NotoSansCJKsc-Bold.otf"
    if not regular.exists():
        raise FileNotFoundError(
            "未找到 NotoSansCJKsc 字体。请从 r9-opc-operations/assets/fonts/ 或 ~/.opc_fonts/ 提供。"
        )
    return str(regular), str(bold)


def clean_text(text: str) -> str:
    r"""清洗文本：移除/替换 fpdf 不支持的 emoji 和零宽字符，避免缺字乱码。

    注意：emoji Unicode 范围必须用 \U000xxxxx（8 位）表示；\u 只支持 4 位，
    写错范围（如 \u1F000）会被 Python re 截断，导致误删 ASCII 数字/字母。
    """
    if not isinstance(text, str):
        text = str(text)

    # 1. 将常见 emoji 替换为文字描述，保留语义
    replacements = {
        '🔥': '[火]', '‼': '!!', '❗': '!', '❓': '?', '🤔': '[思考]', '🌟': '[星]',
        '🦔': '[刺猬]', '✨': '[闪]', '👏': '[鼓掌]', '💪': '[加油]', '🎉': '[庆祝]',
        '😊': '[微笑]', '😭': '[哭]', '😂': '[笑]', '🙏': '[祈祷]', '❤': '[心]',
        '⭐': '[星]', '📉': '[跌]', '📈': '[涨]', '💰': '[钱]', '🏦': '[银行]',
        '👑': '[皇冠]', '🥖': '[法棍]', '🐱': '[猫]', '🐯': '[虎]', '🤣': '[笑哭]',
        '🍰': '[蛋糕]', '🍕': '[披萨]', '😎': '[酷]', '🍗': '[鸡腿]', '🧁': '[纸杯蛋糕]',
        '🥭': '[芒果]', '🐹': '[仓鼠]', '🐰': '[兔子]', '🥪': '[三明治]', '😆': '[大笑]',
        '🐂': '[牛]', '🍓': '[草莓]', '🥦': '[西兰花]', '😷': '[口罩]', '🐶': '[狗]',
        '🤗': '[拥抱]', '🍋': '[柠檬]', '🐼': '[熊猫]', '🦄': '[独角兽]', '🌺': '[花]',
        '🍀': '[四叶草]', '💋': '[唇]', '🌙': '[月亮]', '⚡': '[闪电]', '💛': '[黄心]',
        '🎧': '[耳机]', '🎶': '[音符]', '🎵': '[音符]', '✅': '[对勾]',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # 2. 移除剩余 emoji、零宽字符、变体选择符
    text = re.sub(
        r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF'
        r'\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF'
        r'\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF'
        r'\U00002600-\U000026FF\U00002700-\U000027BF\U00002B50-\U00002B55'
        r'\U0000FE00-\U0000FE0F\U0000200B-\U0000200F]+',
        '', text
    )
    return text


class ChinesePDF(FPDF):
    """预配置好中文字体的 FPDF 子类。"""

    FONT_NAME = "NotoCJK"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        regular, bold = get_font_paths()
        self.add_font(self.FONT_NAME, '', regular)
        self.add_font(self.FONT_NAME, 'B', bold)

    def text(self, txt: str, size: int = 11, bold: bool = False, align: str = 'L'):
        self.set_font(self.FONT_NAME, 'B' if bold else '', size)
        width = self.w - 2 * self.l_margin
        self.multi_cell(width, size * 0.55, clean_text(txt), align=align)
        self.ln(2)


# ============================================================
# 示例：生成一页简单的中文 PDF
# ============================================================
if __name__ == "__main__":
    pdf = ChinesePDF()
    pdf.add_page()
    pdf.text("R9 OPC 投顾公司 · 中文 PDF 生成测试", size=18, bold=True, align='C')
    pdf.text("支持中文、English、数字 12345 混合排版。")
    pdf.text("🔥 这是火焰 emoji，会被替换成 [火]；‼ 双叹号会被替换成 !!")
    pdf.text("稳稳的幸福 5508 赞 / 947 赞 / 2026-06-14")

    out = Path.home() / "Desktop" / "chinese_pdf_test.pdf"
    pdf.output(str(out))
    print(f"测试 PDF 已生成：{out}")
