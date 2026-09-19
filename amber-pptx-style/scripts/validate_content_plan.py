#!/usr/bin/env python3
"""Validate Amber PPT pre-generation content plans."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_DECK = ["content_plan_version", "approval_status", "deck_context", "slides"]
REQUIRED_SLIDE = ["slide_id", "title", "page_question", "problem_explanation", "arguments", "core_message", "transition"]
VALID_STATUS = {"draft", "pending", "confirmed", "waived_by_user", "superseded"}
VALID_SOURCES = {"sourced", "user_input", "industry_assumption", "pending"}


def text(value: object) -> str:
    return "" if value is None else str(value).strip()


def missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return not value
    return False


def load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("content plan must be a JSON object")
    return data


def validate(plan: dict, require_confirmed: bool) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_DECK:
        if field not in plan or missing(plan.get(field)):
            errors.append(f"missing required field `{field}`")
    status = text(plan.get("approval_status"))
    if status and status not in VALID_STATUS:
        errors.append(f"invalid approval_status `{status}`")
    if require_confirmed and status not in {"confirmed", "waived_by_user"}:
        errors.append("approval_status must be `confirmed` or `waived_by_user` before PPT generation")
    context = plan.get("deck_context", {})
    if not isinstance(context, dict):
        errors.append("deck_context must be an object")
    else:
        for field in ("audience", "objective", "core_thesis"):
            if not text(context.get(field)):
                errors.append(f"deck_context missing `{field}`")
    slides = plan.get("slides", [])
    if not isinstance(slides, list) or not slides:
        return errors + ["slides must be a non-empty list"]
    seen_ids: set[str] = set()
    for index, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            errors.append(f"slide #{index} must be an object")
            continue
        raw_sid = slide.get("slide_id")
        sid = text(raw_sid) if raw_sid is not None else ""
        label = sid or f"#{index}"
        for field in REQUIRED_SLIDE:
            if field not in slide or missing(slide.get(field)):
                errors.append(f"slide {label}: missing `{field}`")
        if sid:
            if sid in seen_ids:
                errors.append(f"slide {label}: duplicate slide_id `{sid}`")
            seen_ids.add(sid)
        for field in ("title", "page_question", "problem_explanation", "core_message", "transition"):
            if field in slide and not isinstance(slide.get(field), str):
                errors.append(f"slide {label}: `{field}` must be a string")
        if len(text(slide.get("page_question"))) < 8:
            errors.append(f"slide {label}: page_question is too short")
        if len(text(slide.get("problem_explanation"))) < 16:
            errors.append(f"slide {label}: problem_explanation is too short")
        arguments = slide.get("arguments", [])
        if not isinstance(arguments, list) or not arguments:
            errors.append(f"slide {label}: arguments must be a non-empty list")
        else:
            for arg_index, argument in enumerate(arguments, start=1):
                if not isinstance(argument, dict) or not text(argument.get("claim")):
                    errors.append(f"slide {label}: argument {arg_index} missing claim")
                    continue
                if not isinstance(argument.get("claim"), str):
                    errors.append(f"slide {label}: argument {arg_index} claim must be a string")
                source = text(argument.get("source_status"))
                if source not in VALID_SOURCES:
                    errors.append(f"slide {label}: argument {arg_index} has invalid source_status `{source}`")
                if source == "sourced" and not text(argument.get("evidence_id")):
                    errors.append(f"slide {label}: sourced argument {arg_index} requires evidence_id")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan")
    parser.add_argument("--require-confirmed", action="store_true")
    args = parser.parse_args()
    try:
        errors = validate(load(Path(args.plan)), args.require_confirmed)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 2
    if errors:
        print("INVALID content plan:")
        print("\n".join(f"- {item}" for item in errors))
        return 1
    print("VALID content plan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
