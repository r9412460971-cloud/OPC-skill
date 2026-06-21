# 字体目录

本目录用于放置 `NotoSansCJKsc-Regular.otf` 和 `NotoSansCJKsc-Bold.otf` 字体文件。

由于字体文件较大（每个约 16MB），未纳入 Git 版本控制。请从以下途径获取：

1. 从本地 `~/.opc_fonts/` 目录复制；
2. 从 Google Noto Fonts 官方仓库下载：https://github.com/googlefonts/noto-cjk
3. 从其他合法渠道获取思源黑体（Source Han Sans / Noto Sans CJK SC）OTF 版本。

放置后，`scripts/chinese_pdf.py` 会自动从本目录加载；若本目录不存在字体，则回退到 `~/.opc_fonts/`。
