from __future__ import annotations

import random
import unittest
from decimal import Decimal

from allocate_quotation import ContractError, process


def config_for(weights: list[int], budget: str = "1.00") -> dict:
    return {
        "schema_version": "1.0",
        "status": "draft",
        "currency": "CNY",
        "unit": "万元",
        "tax_included": None,
        "allocation_mode": "weighted_leaf_items",
        "source_sections": [{"section_key": "SYS-01", "section_title": "测试系统"}],
        "systems": [
            {
                "section_key": "SYS-01",
                "section_title": "测试系统",
                "budget": budget,
                "fixed_items": [],
                "items": [
                    {"item_id": f"ITEM-{index:03d}", "name": f"功能{index}", "weight": str(item_weight)}
                    for index, item_weight in enumerate(weights, start=1)
                ],
            }
        ],
        "fixed_items": [],
        "expected_project_total": budget,
    }


class AllocationTests(unittest.TestCase):
    def test_one_divided_by_three_is_exact(self) -> None:
        result = process(config_for([1, 1, 1]))
        amounts = [Decimal(item["amount"]) for item in result["systems"][0]["items"]]
        self.assertEqual(sum(amounts), Decimal("1.00"))
        self.assertEqual(amounts, [Decimal("0.34"), Decimal("0.33"), Decimal("0.33")])

    def test_random_weights_reconcile(self) -> None:
        rng = random.Random(20260810)
        for _ in range(100):
            weights = [rng.randint(1, 9) for _ in range(rng.randint(1, 40))]
            budget = Decimal(rng.randint(1, 100000)) / Decimal("100")
            result = process(config_for(weights, f"{budget:.2f}"))
            amounts = [Decimal(item["amount"]) for item in result["systems"][0]["items"]]
            self.assertEqual(sum(amounts), budget)

    def test_formal_requires_tax_basis(self) -> None:
        config = config_for([1])
        config["status"] = "formal"
        with self.assertRaises(ContractError):
            process(config)

    def test_fixed_items_cannot_exceed_budget(self) -> None:
        config = config_for([1])
        config["systems"][0]["fixed_items"] = [{"item_id": "FIX-01", "name": "固定项", "amount": "1.01"}]
        with self.assertRaises(ContractError):
            process(config)

    def test_duplicate_item_id_is_rejected(self) -> None:
        config = config_for([1, 1])
        config["systems"][0]["items"][1]["item_id"] = "ITEM-001"
        with self.assertRaises(ContractError):
            process(config)

    def test_missing_system_budget_is_rejected(self) -> None:
        config = config_for([1])
        config["source_sections"].append({"section_key": "SYS-02", "section_title": "未报价系统"})
        with self.assertRaises(ContractError):
            process(config)

    def test_section_title_conflict_is_rejected(self) -> None:
        config = config_for([1])
        config["source_sections"][0]["section_title"] = "源表标题"
        with self.assertRaises(ContractError):
            process(config)


if __name__ == "__main__":
    unittest.main()
