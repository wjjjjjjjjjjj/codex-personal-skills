#!/usr/bin/env python3
"""Validate a quotation contract and allocate every system budget exactly."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from pathlib import Path
from typing import Any


CENT = Decimal("0.01")
ALLOWED_MODES = {"weighted_leaf_items"}
ALLOWED_STATUS = {"draft", "formal"}


class ContractError(ValueError):
    pass


def money(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ContractError(f"{field} 必须是非负十进制金额字符串")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ContractError(f"{field} 不是有效十进制金额：{value!r}") from None
    if not result.is_finite() or result < 0 or result.quantize(CENT) != result:
        raise ContractError(f"{field} 必须为非负且最多两位小数：{value!r}")
    return result


def weight(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ContractError(f"{field} 不是有效权重：{value!r}") from None
    if not result.is_finite() or result <= 0:
        raise ContractError(f"{field} 必须大于 0")
    return result


def require_text(obj: dict[str, Any], key: str, scope: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ContractError(f"{scope}.{key} 必须是不带首尾空格的非空字符串")
    return value


def allocate_exact(total: Decimal, items: list[dict[str, Any]], scope: str) -> dict[str, Decimal]:
    if not items:
        if total == 0:
            return {}
        raise ContractError(f"{scope} 有待分配金额 {total}，但没有叶子功能")
    weights = [(require_text(item, "item_id", scope), weight(item.get("weight", "1"), f"{scope}.{item.get('item_id', '?')}.weight")) for item in items]
    total_weight = sum((item_weight for _, item_weight in weights), Decimal("0"))
    raw = [(item_id, total * item_weight / total_weight) for item_id, item_weight in weights]
    floors = {item_id: amount.quantize(CENT, rounding=ROUND_DOWN) for item_id, amount in raw}
    remaining_cents = int(((total - sum(floors.values(), Decimal("0"))) / CENT).to_integral_exact())
    order = sorted(raw, key=lambda pair: (-(pair[1] - floors[pair[0]]), pair[0]))
    for item_id, _ in order[:remaining_cents]:
        floors[item_id] += CENT
    if sum(floors.values(), Decimal("0")) != total:
        raise ContractError(f"{scope} 尾差分配失败")
    return floors


def process(config: dict[str, Any]) -> dict[str, Any]:
    if config.get("schema_version") != "1.0":
        raise ContractError("schema_version 必须为 1.0")
    status = config.get("status")
    if status not in ALLOWED_STATUS:
        raise ContractError("status 必须为 draft 或 formal")
    require_text(config, "currency", "config")
    require_text(config, "unit", "config")
    if status == "formal" and not isinstance(config.get("tax_included"), bool):
        raise ContractError("formal 状态必须明确 tax_included=true 或 false")
    if config.get("allocation_mode") not in ALLOWED_MODES:
        raise ContractError("allocation_mode 仅支持 weighted_leaf_items")

    systems = config.get("systems")
    if not isinstance(systems, list) or not systems:
        raise ContractError("systems 必须是非空数组")

    source_sections = config.get("source_sections")
    if not isinstance(source_sections, list) or not source_sections:
        raise ContractError("source_sections 必须是从源表提取的非空数组")
    source_map: dict[str, str] = {}
    for index, section in enumerate(source_sections, start=1):
        if not isinstance(section, dict):
            raise ContractError(f"source_sections[{index}] 必须是对象")
        key = require_text(section, "section_key", f"source_sections[{index}]")
        title = require_text(section, "section_title", f"source_sections[{index}]")
        if key in source_map:
            raise ContractError(f"source_sections section_key 重复：{key}")
        source_map[key] = title

    seen_section_keys: set[str] = set()
    seen_item_ids: set[str] = set()
    system_results: list[dict[str, Any]] = []
    project_system_total = Decimal("0")
    configured_map: dict[str, str] = {}

    for index, system in enumerate(systems, start=1):
        if not isinstance(system, dict):
            raise ContractError(f"systems[{index}] 必须是对象")
        scope = f"systems[{index}]"
        section_key = require_text(system, "section_key", scope)
        section_title = require_text(system, "section_title", scope)
        if section_key in seen_section_keys:
            raise ContractError(f"section_key 重复：{section_key}")
        seen_section_keys.add(section_key)
        configured_map[section_key] = section_title
        budget = money(system.get("budget"), f"{scope}.budget")
        project_system_total += budget

        fixed_items = system.get("fixed_items", [])
        items = system.get("items", [])
        if not isinstance(fixed_items, list) or not isinstance(items, list):
            raise ContractError(f"{scope}.fixed_items/items 必须是数组")

        fixed_total = Decimal("0")
        fixed_result: list[dict[str, str]] = []
        for item in fixed_items:
            if not isinstance(item, dict):
                raise ContractError(f"{scope}.fixed_items 包含非对象")
            item_id = require_text(item, "item_id", f"{scope}.fixed_items")
            require_text(item, "name", f"{scope}.{item_id}")
            if item_id in seen_item_ids:
                raise ContractError(f"item_id 重复：{item_id}")
            seen_item_ids.add(item_id)
            amount = money(item.get("amount"), f"{scope}.{item_id}.amount")
            fixed_total += amount
            fixed_result.append({"item_id": item_id, "amount": f"{amount:.2f}"})
        if fixed_total > budget:
            raise ContractError(f"{scope} 固定项 {fixed_total} 超过系统预算 {budget}")

        for item in items:
            if not isinstance(item, dict):
                raise ContractError(f"{scope}.items 包含非对象")
            item_id = require_text(item, "item_id", f"{scope}.items")
            require_text(item, "name", f"{scope}.{item_id}")
            if item_id in seen_item_ids:
                raise ContractError(f"item_id 重复：{item_id}")
            seen_item_ids.add(item_id)

        allocatable = budget - fixed_total
        allocations = allocate_exact(allocatable, items, scope)
        item_result = [
            {
                "item_id": item["item_id"],
                "weight": str(weight(item.get("weight", "1"), f"{scope}.{item['item_id']}.weight")),
                "amount": f"{allocations[item['item_id']]:.2f}",
            }
            for item in items
        ]
        allocated_total = fixed_total + sum(allocations.values(), Decimal("0"))
        if allocated_total != budget:
            raise ContractError(f"{scope} 对账失败：{allocated_total} != {budget}")
        system_results.append(
            {
                "section_key": section_key,
                "section_title": section_title,
                "configured_budget": f"{budget:.2f}",
                "fixed_items": fixed_result,
                "items": item_result,
                "allocated_total": f"{allocated_total:.2f}",
                "difference": "0.00",
            }
        )

    if configured_map != source_map:
        missing_budget = sorted(set(source_map) - set(configured_map))
        unknown_config = sorted(set(configured_map) - set(source_map))
        title_conflicts = sorted(
            key for key in set(configured_map) & set(source_map) if configured_map[key] != source_map[key]
        )
        details = []
        if missing_budget:
            details.append("源表系统未配置预算=" + ",".join(missing_budget))
        if unknown_config:
            details.append("配置系统未在源表找到=" + ",".join(unknown_config))
        if title_conflicts:
            details.append("系统标题冲突=" + ",".join(title_conflicts))
        raise ContractError("；".join(details))

    project_fixed_items = config.get("fixed_items", [])
    if not isinstance(project_fixed_items, list):
        raise ContractError("fixed_items 必须是数组")
    project_fixed_total = Decimal("0")
    project_fixed_result: list[dict[str, str]] = []
    for item in project_fixed_items:
        if not isinstance(item, dict):
            raise ContractError("fixed_items 包含非对象")
        item_id = require_text(item, "item_id", "fixed_items")
        require_text(item, "name", f"fixed_items.{item_id}")
        if item_id in seen_item_ids:
            raise ContractError(f"item_id 重复：{item_id}")
        seen_item_ids.add(item_id)
        amount = money(item.get("amount"), f"fixed_items.{item_id}.amount")
        project_fixed_total += amount
        project_fixed_result.append({"item_id": item_id, "amount": f"{amount:.2f}"})

    project_total = project_system_total + project_fixed_total
    expected = config.get("expected_project_total")
    if expected is not None and money(expected, "expected_project_total") != project_total:
        raise ContractError(f"项目总价不一致：配置期望 {expected}，实际 {project_total:.2f}")

    return {
        "valid": True,
        "schema_version": "1.0",
        "status": status,
        "currency": config["currency"],
        "unit": config["unit"],
        "tax_included": config.get("tax_included"),
        "source_section_count": len(source_map),
        "systems": system_results,
        "fixed_items": project_fixed_result,
        "system_budget_total": f"{project_system_total:.2f}",
        "project_fixed_total": f"{project_fixed_total:.2f}",
        "project_total": f"{project_total:.2f}",
        "difference": "0.00",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8-sig"))
        if not isinstance(config, dict):
            raise ContractError("配置根节点必须是对象")
        result = process(config)
        exit_code = 0
    except (OSError, json.JSONDecodeError, ContractError) as exc:
        result = {"valid": False, "errors": [str(exc)]}
        exit_code = 1

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
