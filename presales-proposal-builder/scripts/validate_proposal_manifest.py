#!/usr/bin/env python3
"""Validate proposal_manifest.json using only the Python standard library."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROPOSAL_TYPES = {
    "decision-report",
    "marketing-solution",
    "construction-plan",
    "short-brief",
    "revision",
}
PRODUCT_FITS = {"standard", "extension", "gap", "third-party"}
CARRIERS = {"content", "markdown", "docx", "pptx-manuscript"}
SOURCE_MODES = {
    "summary-first",
    "provided-extract",
    "user-authorized-original",
    "mixed",
}
STATUSES = {"draft", "ready"}


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def nonempty_string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(nonempty_string(item) for item in value)
    )


def load_manifest(path_text: str) -> dict[str, Any]:
    if path_text == "-":
        payload = sys.stdin.read()
    else:
        payload = Path(path_text).read_text(encoding="utf-8-sig")
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("manifest root must be a JSON object")
    return value


def validate(manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if manifest.get("schema_version") != "1.1":
        errors.append("schema_version must be '1.1'")

    status = manifest.get("status")
    if status not in STATUSES:
        errors.append("status must be draft or ready")

    for field in ("project_name", "purpose"):
        if not nonempty_string(manifest.get(field)):
            errors.append(f"{field} must be a non-empty string")

    proposal_type = manifest.get("proposal_type")
    if proposal_type not in PROPOSAL_TYPES:
        errors.append(
            "proposal_type must be one of: " + ", ".join(sorted(PROPOSAL_TYPES))
        )

    if not nonempty_string_list(manifest.get("audience")):
        errors.append("audience must be a non-empty list of roles")

    carrier = manifest.get("carrier")
    if carrier not in CARRIERS:
        errors.append("carrier must be one of: " + ", ".join(sorted(CARRIERS)))

    source_mode = manifest.get("source_mode")
    if source_mode not in SOURCE_MODES:
        errors.append(
            "source_mode must be one of: " + ", ".join(sorted(SOURCE_MODES))
        )

    if manifest.get("claim_policy") != "conservative":
        errors.append("claim_policy must be 'conservative'")

    requirements_provided = manifest.get("requirements_provided")
    if not isinstance(requirements_provided, bool):
        errors.append("requirements_provided must be a boolean")

    list_fields = (
        "sources",
        "confirmed_facts",
        "product_mapping",
        "assumptions",
        "open_questions",
        "business_outcomes",
        "exclusions",
        "sections",
    )
    for field in list_fields:
        if not isinstance(manifest.get(field), list):
            errors.append(f"{field} must be a list")

    sources = manifest.get("sources")
    if isinstance(sources, list):
        source_ids: set[str] = set()
        for index, source in enumerate(sources, start=1):
            prefix = f"sources[{index}]"
            if not isinstance(source, dict):
                errors.append(f"{prefix} must be an object")
                continue
            for field in ("id", "type", "location", "usage"):
                if not nonempty_string(source.get(field)):
                    errors.append(f"{prefix}.{field} must be a non-empty string")
            source_id = source.get("id")
            if nonempty_string(source_id):
                if source_id in source_ids:
                    errors.append(f"duplicate source id: {source_id}")
                source_ids.add(source_id)

    sections = manifest.get("sections")
    if isinstance(sections, list):
        section_ids: set[str] = set()
        for index, section in enumerate(sections, start=1):
            prefix = f"sections[{index}]"
            if not isinstance(section, dict):
                errors.append(f"{prefix} must be an object")
                continue
            for field in ("id", "title", "decision_question"):
                if not nonempty_string(section.get(field)):
                    errors.append(f"{prefix}.{field} must be a non-empty string")
            section_id = section.get("id")
            if nonempty_string(section_id):
                if section_id in section_ids:
                    errors.append(f"duplicate section id: {section_id}")
                section_ids.add(section_id)

    product_mapping = manifest.get("product_mapping")
    if isinstance(product_mapping, list):
        for index, item in enumerate(product_mapping, start=1):
            prefix = f"product_mapping[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{prefix} must be an object")
                continue
            for field in (
                "requirement",
                "amber_product",
                "verified_capability",
                "writing_treatment",
            ):
                if not nonempty_string(item.get(field)):
                    errors.append(f"{prefix}.{field} must be a non-empty string")
            if item.get("fit") not in PRODUCT_FITS:
                errors.append(
                    f"{prefix}.fit must be one of: "
                    + ", ".join(sorted(PRODUCT_FITS))
                )

    for field in (
        "confirmed_facts",
        "assumptions",
        "open_questions",
        "business_outcomes",
        "exclusions",
    ):
        value = manifest.get(field)
        if isinstance(value, list) and not all(nonempty_string(item) for item in value):
            errors.append(f"{field} must contain only non-empty strings")

    if status == "ready":
        required_nonempty_lists = (
            "sources",
            "confirmed_facts",
            "business_outcomes",
            "exclusions",
            "sections",
        )
        for field in required_nonempty_lists:
            if isinstance(manifest.get(field), list) and not manifest[field]:
                errors.append(f"{field} must not be empty when status is ready")
        if isinstance(manifest.get("open_questions"), list) and manifest["open_questions"]:
            warnings.append(
                "ready manifest still has open_questions; confirm none changes route, "
                "price, scope, or responsibility"
            )
        if (
            requirements_provided is True
            and isinstance(product_mapping, list)
            and not product_mapping
        ):
            errors.append(
                "product_mapping must not be empty when requirements_provided is true"
            )
    elif (
        status == "draft"
        and requirements_provided is True
        and isinstance(product_mapping, list)
        and not product_mapping
    ):
        warnings.append(
            "draft manifest has requirements but product_mapping is empty; complete it before ready"
        )

    if carrier == "pptx-manuscript":
        warnings.append(
            "PPT generation requires page-by-page content approval under "
            "amber-pptx-style before creating slides"
        )

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="Path to JSON manifest, or - for stdin")
    args = parser.parse_args()

    try:
        manifest = load_manifest(args.manifest)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    errors, warnings = validate(manifest)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")

    if errors:
        print(f"INVALID: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1

    print(f"VALID: 0 error(s), {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
