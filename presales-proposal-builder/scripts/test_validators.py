from __future__ import annotations

import unittest

from validate_customer_facing_text import PATTERNS
from validate_proposal_manifest import validate


def base_manifest(status: str = "draft") -> dict:
    return {
        "schema_version": "1.1",
        "status": status,
        "project_name": "某项目",
        "proposal_type": "construction-plan",
        "audience": ["决策人"],
        "purpose": "确定建设范围",
        "carrier": "docx",
        "source_mode": "summary-first",
        "requirements_provided": True,
        "sources": [{"id": "S1", "type": "summary", "location": "summaries/a.md", "usage": "需求"}],
        "confirmed_facts": ["已有需求摘要"],
        "product_mapping": [],
        "assumptions": [],
        "open_questions": [],
        "business_outcomes": ["形成可验收结果"],
        "exclusions": ["第三方改造待确认"],
        "sections": [{"id": "1", "title": "建设背景", "decision_question": "为什么建设"}],
        "claim_policy": "conservative",
    }


def matching_labels(text: str) -> list[str]:
    return [label for label, pattern in PATTERNS if pattern.search(text)]


class ProposalValidatorTests(unittest.TestCase):
    def test_normal_english_skills_is_allowed(self) -> None:
        self.assertEqual(matching_labels("The program develops digital skills for archive staff."), [])

    def test_internal_skill_wording_is_rejected(self) -> None:
        self.assertIn("skill implementation detail", matching_labels("请按本 Skill 要求生成方案。"))
        self.assertIn("skill implementation detail", matching_labels(r"参考 .codex\skills\demo-data-builder。"))

    def test_draft_empty_mapping_warns(self) -> None:
        errors, warnings = validate(base_manifest("draft"))
        self.assertEqual(errors, [])
        self.assertTrue(any("product_mapping" in warning for warning in warnings))

    def test_ready_empty_mapping_fails(self) -> None:
        errors, _ = validate(base_manifest("ready"))
        self.assertTrue(any("product_mapping" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
