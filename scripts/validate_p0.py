#!/usr/bin/env python3
"""
P0 修复验证脚本

验证 OPC-skill 仓库的 P0 级别修复是否生效：
1. 所有 skill 目录都有 SKILL.md
2. 所有 SKILL.md 都有合法 frontmatter（至少包含 name 和 description）
3. 目录名与 frontmatter name 一致
4. 没有硬编码 /Users/r9/ 路径
5. README 分类列表覆盖全部 skill
6. r9-workbench 路由表覆盖全部 skill
7. version 字段应为字符串（避免 3.10 被解析为 3.1）

用法：
    python3 scripts/validate_p0.py
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
README = ROOT / "README.md"
WORKBENCH = SKILLS_DIR / "r9-workbench" / "SKILL.md"

EXPECTED_SKILL_COUNT = 93


def get_skill_dirs() -> list[Path]:
    """返回所有 skill 目录，按名称排序。"""
    return sorted([d for d in SKILLS_DIR.iterdir() if d.is_dir()])


def parse_frontmatter(skill_path: Path):
    """
    解析 SKILL.md 的 YAML frontmatter。
    返回 (frontmatter_dict, content, error_message)。
    error_message 为 None 表示解析成功。
    """
    content = skill_path.read_text(encoding="utf-8")

    if not content.startswith("---"):
        return None, content, "missing frontmatter"

    # 匹配 --- ... --- 之间的内容
    match = re.search(r"^---\s*$(.*?)^---\s*$", content, re.MULTILINE | re.DOTALL)
    if not match:
        return None, content, "invalid frontmatter format"

    fm_text = match.group(1)
    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError as e:
        return None, content, f"YAML parse error: {e}"

    if not isinstance(fm, dict):
        return None, content, "frontmatter is not a mapping"

    return fm, content, None


def extract_readme_skills(readme_content: str) -> set[str]:
    """从 README 的 skill 分类列表中提取 skill 名称。"""
    # 只取 "## 包含的 Skill" 与 "## 安装方式" 之间的内容
    match = re.search(
        r"## 包含的 Skill\s*(.*?)\s*## 安装方式",
        readme_content,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        return set()
    skill_section = match.group(1)
    return set(re.findall(r"^-\s+(\S+)", skill_section, re.MULTILINE))


def extract_workbench_skills(wb_content: str, valid_skills: set[str]) -> set[str]:
    """从 r9-workbench 的路由表中提取 skill 名称。"""
    # workbench 中 skill 以 **skill-name** 加粗形式出现
    candidates = set(re.findall(r"\*\*(\S+?)\*\*", wb_content))
    return candidates & valid_skills


def validate() -> int:
    errors = []
    warnings = []

    skill_dirs = get_skill_dirs()
    skill_names = {d.name for d in skill_dirs}
    actual_count = len(skill_dirs)

    print(f"📁 发现 {actual_count} 个 skill 目录")
    if actual_count != EXPECTED_SKILL_COUNT:
        warnings.append(
            f"skill 数量 ({actual_count}) 与预期 ({EXPECTED_SKILL_COUNT}) 不一致"
        )

    # 1. 检查每个 skill 都有 SKILL.md
    for d in skill_dirs:
        skill_md = d / "SKILL.md"
        if not skill_md.exists():
            errors.append(f"{d.name}: 缺少 SKILL.md")

    # 2. 解析 frontmatter、检查 name/description、version 类型、硬编码路径
    for d in skill_dirs:
        skill_md = d / "SKILL.md"
        if not skill_md.exists():
            continue

        fm, content, err = parse_frontmatter(skill_md)
        if err:
            errors.append(f"{d.name}: {err}")
            continue

        if "name" not in fm:
            errors.append(f"{d.name}: frontmatter 缺少 'name'")
        elif fm["name"] != d.name:
            errors.append(
                f"{d.name}: frontmatter name '{fm['name']}' 与目录名 '{d.name}' 不一致"
            )

        if "description" not in fm:
            errors.append(f"{d.name}: frontmatter 缺少 'description'")

        if "version" in fm and not isinstance(fm["version"], str):
            warnings.append(
                f"{d.name}: version 值 {fm['version']!r} 不是字符串，"
                f"建议改为 '{fm['version']}'"
            )

        if "/Users/r9/" in content:
            errors.append(f"{d.name}: 包含硬编码 /Users/r9/ 路径")

    # 3. 检查 README 覆盖
    readme_content = README.read_text(encoding="utf-8")
    readme_skills = extract_readme_skills(readme_content)
    missing_in_readme = skill_names - readme_skills
    extra_in_readme = readme_skills - skill_names
    if missing_in_readme:
        errors.append(f"README 缺少 skill: {sorted(missing_in_readme)}")
    if extra_in_readme:
        errors.append(f"README 包含不存在的 skill: {sorted(extra_in_readme)}")

    # 4. 检查 r9-workbench 覆盖
    wb_content = WORKBENCH.read_text(encoding="utf-8")
    wb_skills = extract_workbench_skills(wb_content, skill_names)
    missing_in_wb = skill_names - wb_skills
    if missing_in_wb:
        errors.append(f"r9-workbench 缺少 skill: {sorted(missing_in_wb)}")

    # 输出结果
    covered_by_readme = len(readme_skills & skill_names)
    covered_by_wb = len(wb_skills)
    print(f"📋 README 覆盖: {covered_by_readme}/{actual_count}")
    print(f"🧭 r9-workbench 覆盖: {covered_by_wb}/{actual_count}")

    if warnings:
        print(f"\n⚠️  Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"  - {w}")

    if errors:
        print(f"\n❌ P0 验证失败，共 {len(errors)} 个错误：")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\n✅ 所有 P0 检查通过！")
    print(f"   - {actual_count} 个 skill 已验证")
    print("   - 所有 SKILL.md 都有合法 frontmatter")
    print("   - 目录名与 frontmatter name 一致")
    print("   - 未发现硬编码 /Users/r9/ 路径")
    print("   - README 与 r9-workbench 覆盖全部 skill")
    return 0


if __name__ == "__main__":
    sys.exit(validate())
