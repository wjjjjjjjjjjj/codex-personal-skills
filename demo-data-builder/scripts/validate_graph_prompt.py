from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any


REQUIRED_HEADINGS = [
    "# 角色",
    "# 实体识别规则",
    "## 实体处理约束",
    "# 关系抽取规则",
    "## 实体-关系-实体",
    "# 输出格式",
    "# 完整示例",
    "# 执行指令",
]

DEFAULT_ENTITY_FIELDS = ["name", "type"]
DEFAULT_RELATION_FIELDS = ["source", "target", "relation_type", "relation_time", "evidence"]
DATE_TOKEN_RE = re.compile(r"^\d{4}(?:-\d{2})?(?:-\d{2})?$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="校验知识图谱抽取提示词的系统兼容性")
    parser.add_argument("prompt", type=Path, help="提示词 Markdown 文件")
    parser.add_argument("--types", nargs="+", required=True, help="允许的实体类型原始值")
    parser.add_argument("--max-chars", type=int, default=5000, help="最大字符数，默认5000")
    parser.add_argument("--entity-fields", nargs="+", default=DEFAULT_ENTITY_FIELDS)
    parser.add_argument("--relation-fields", nargs="+", default=DEFAULT_RELATION_FIELDS)
    parser.add_argument("--name-field", default="name")
    parser.add_argument("--type-field", default="type")
    parser.add_argument("--source-field", default="source")
    parser.add_argument("--target-field", default="target")
    parser.add_argument("--time-field", default="relation_time")
    parser.add_argument("--evidence-field", default="evidence")
    return parser.parse_args()


def add_check(checks: list[tuple[str, bool, str]], name: str, passed: bool, detail: str) -> None:
    checks.append((name, passed, detail))


def heading_positions(text: str) -> dict[str, list[int]]:
    return {
        heading: [match.start() for match in re.finditer(rf"(?m)^{re.escape(heading)}[ \t]*$", text)]
        for heading in REQUIRED_HEADINGS
    }


def parse_date_token(value: str) -> tuple[int, ...] | None:
    if not DATE_TOKEN_RE.fullmatch(value):
        return None
    parts = tuple(int(part) for part in value.split("-"))
    try:
        if len(parts) == 1:
            if not 1 <= parts[0] <= 9999:
                return None
        elif len(parts) == 2:
            date(parts[0], parts[1], 1)
        else:
            date(parts[0], parts[1], parts[2])
    except ValueError:
        return None
    return parts


def valid_time(value: Any) -> bool:
    if not isinstance(value, str) or value != value.strip():
        return False
    if value == "none":
        return True
    tokens = value.split("至")
    if len(tokens) not in {1, 2}:
        return False
    parsed = [parse_date_token(token) for token in tokens]
    if any(item is None for item in parsed):
        return False
    if len(parsed) == 2:
        start, end = parsed
        return len(start) == len(end) and start <= end
    return True


def print_result(checks: list[tuple[str, bool, str]]) -> int:
    for name, passed, detail in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}：{detail}")
    passed_all = all(item[1] for item in checks)
    print(f"RESULT={'PASS' if passed_all else 'FAIL'}")
    return 0 if passed_all else 1


def main() -> int:
    args = parse_args()
    checks: list[tuple[str, bool, str]] = []
    try:
        text = args.prompt.read_text(encoding="utf-8-sig")
    except Exception as exc:
        print(f"[FAIL] 文件读取：{exc}")
        return 1

    add_check(checks, "字符数", len(text) <= args.max_chars, f"{len(text)}/{args.max_chars}")

    position_map = heading_positions(text)
    missing = [heading for heading, positions in position_map.items() if not positions]
    duplicate = [heading for heading, positions in position_map.items() if len(positions) > 1]
    unique_positions = [position_map[heading][0] for heading in REQUIRED_HEADINGS if len(position_map[heading]) == 1]
    headings_ok = not missing and not duplicate and unique_positions == sorted(unique_positions)
    detail_parts = []
    if missing:
        detail_parts.append("缺失=" + "、".join(missing))
    if duplicate:
        detail_parts.append("重复=" + "、".join(duplicate))
    add_check(checks, "固定章节及顺序", headings_ok, "；".join(detail_parts) or "章节唯一、齐全且顺序正确")

    add_check(checks, "档案原文占位符", "{{档案原文}}" in text, "必须保留{{档案原文}}")
    compact_lower = re.sub(r"\s+", "", text).lower()
    runtime_output_ok = "直接输出合法json" in compact_lower and "禁止使用markdown包裹" in compact_lower
    add_check(checks, "运行时仅输出JSON", runtime_output_ok, "需包含直接输出合法JSON及禁止Markdown包裹")

    if not headings_ok:
        return print_result(checks)

    example_start = position_map["# 完整示例"][0]
    example_end = position_map["# 执行指令"][0]
    example_section = text[example_start:example_end]

    all_blocks = re.findall(r"```json\s*(.*?)\s*```", text, re.S | re.I)
    example_blocks = re.findall(r"```json\s*(.*?)\s*```", example_section, re.S | re.I)
    json_errors: list[str] = []
    for idx, raw in enumerate(all_blocks, start=1):
        try:
            json.loads(raw)
        except json.JSONDecodeError as exc:
            json_errors.append(f"第{idx}块：{exc.msg}@{exc.lineno}:{exc.colno}")
    json_ok = len(all_blocks) >= 2 and bool(example_blocks) and not json_errors
    add_check(
        checks,
        "JSON示例可解析",
        json_ok,
        f"JSON块={len(all_blocks)}，完整示例块={len(example_blocks)}" + ("；" + "；".join(json_errors) if json_errors else ""),
    )
    if not json_ok:
        return print_result(checks)

    try:
        example = json.loads(example_blocks[-1])
    except json.JSONDecodeError as exc:
        add_check(checks, "完整示例JSON", False, str(exc))
        return print_result(checks)

    root_ok = isinstance(example, dict) and isinstance(example.get("entities"), list) and isinstance(example.get("relations"), list)
    add_check(checks, "示例根结构", root_ok, "必须包含entities和relations数组")
    if not root_ok:
        return print_result(checks)

    entities = example["entities"]
    relations = example["relations"]
    nonempty_ok = bool(entities) and bool(relations)
    add_check(checks, "完整示例非空", nonempty_ok, f"entities={len(entities)}，relations={len(relations)}")

    entity_fields = set(args.entity_fields)
    relation_fields = set(args.relation_fields)
    entity_fields_ok = all(isinstance(item, dict) and set(item) == entity_fields for item in entities)
    relation_fields_ok = all(isinstance(item, dict) and set(item) == relation_fields for item in relations)
    add_check(checks, "实体字段集合", entity_fields_ok, f"期望：{sorted(entity_fields)}")
    add_check(checks, "关系字段集合", relation_fields_ok, f"期望：{sorted(relation_fields)}")

    allowed_types = set(args.types)
    types_ok = entity_fields_ok and all(
        isinstance(item.get(args.type_field), str) and item.get(args.type_field) in allowed_types
        for item in entities
    )
    add_check(checks, "实体类型原样匹配", types_ok, "允许：" + "、".join(args.types))

    names = [item.get(args.name_field) if isinstance(item, dict) else None for item in entities]
    names_are_strings = all(isinstance(name, str) and bool(name) and name == name.strip() for name in names)
    normalized_names = [name for name in names if isinstance(name, str)]
    names_unique = names_are_strings and len(normalized_names) == len(set(normalized_names))
    add_check(
        checks,
        "实体名称非空且唯一",
        names_unique,
        f"实体数={len(names)}，有效字符串={len(normalized_names)}，唯一名称={len(set(normalized_names))}",
    )

    name_set = set(normalized_names) if names_are_strings else set()
    endpoints_ok = relation_fields_ok and names_unique and all(
        isinstance(item.get(args.source_field), str)
        and isinstance(item.get(args.target_field), str)
        and item.get(args.source_field) in name_set
        and item.get(args.target_field) in name_set
        for item in relations
    )
    add_check(checks, "关系端点完整", endpoints_ok, "source和target必须匹配entities.name")

    time_ok = relation_fields_ok and all(valid_time(item.get(args.time_field)) for item in relations)
    add_check(checks, "关系时间有效", time_ok, "允许none、有效YYYY/YYYY-MM/YYYY-MM-DD或同粒度且不逆序的区间")

    relation_strings_ok = relation_fields_ok and all(
        isinstance(item.get("relation_type"), str) and bool(item.get("relation_type", "").strip())
        for item in relations
    )
    add_check(checks, "关系类型非空", relation_strings_ok, "relation_type必须为非空字符串")

    input_match = re.search(r"输入文档[：:]\s*(.*?)\s*输出[：:]", example_section, re.S)
    sample_input = input_match.group(1) if input_match else ""
    evidence_ok = relation_fields_ok and bool(sample_input.strip()) and all(
        isinstance(item.get(args.evidence_field), str)
        and bool(item[args.evidence_field].strip())
        and item[args.evidence_field] in sample_input
        for item in relations
    )
    add_check(checks, "示例证据逐字命中", evidence_ok, "每条evidence必须存在于完整示例的输入文档")

    return print_result(checks)


if __name__ == "__main__":
    sys.exit(main())
