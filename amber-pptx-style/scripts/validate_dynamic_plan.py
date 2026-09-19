#!/usr/bin/env python3
"""Validate an Amber PPT layout plan after content confirmation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED = ["slide_id", "role", "core_message", "content_signals", "layout_family", "layout_variant", "visual_focus", "components", "density", "layout_reason"]
GENERIC_FAMILIES = {"card", "cards", "卡片", "卡片网格", "标准内容页", "模板"}
DEFAULT_END_WORDS = ["谢谢", "thank you", "thanks"]
VALID_DENSITY = {"low", "medium", "high", "低", "中", "高"}
CONSULTING_GROUPS = [
    {"证据", "evidence", "来源", "source", "口径", "caveat"},
    {"so what", "解读", "决策", "decision"},
    {"洞察", "insight", "侧栏"},
    {"微图", "microchart", "micro chart"},
    {"图例", "legend", "注释", "annotation"},
]


def as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(as_text(v) for v in value)
    if isinstance(value, dict):
        return " ".join(f"{k} {as_text(v)}" for k, v in value.items())
    return str(value).strip()


def load_plan(path: Path) -> tuple[dict, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {}, data
    if not isinstance(data, dict):
        raise ValueError("plan must be a JSON list or an object with a slides list")
    slides = data.get("slides", [])
    if not isinstance(slides, list):
        raise ValueError("slides must be a list")
    return data, slides


def validate(slides: list[dict]) -> list[str]:
    errors: list[str] = []
    if not slides:
        return ["plan has no slides"]
    families: list[str] = []
    seen_ids: set[str] = set()
    for idx, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            errors.append(f"slide #{idx}: must be an object")
            continue
        raw_sid = slide.get("slide_id")
        sid = as_text(raw_sid) if raw_sid is not None else ""
        label = sid or f"#{idx}"
        for field in REQUIRED:
            if not as_text(slide.get(field)):
                errors.append(f"slide {label}: missing required field `{field}`")
        if sid:
            if sid in seen_ids:
                errors.append(f"slide {label}: duplicate slide_id `{sid}`")
            seen_ids.add(sid)
        for field in ("content_signals", "components"):
            value = slide.get(field)
            if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
                errors.append(f"slide {label}: `{field}` must be a non-empty list of strings")
        role = as_text(slide.get("role")).lower()
        family = as_text(slide.get("layout_family")).lower()
        reason, core = as_text(slide.get("layout_reason")), as_text(slide.get("core_message"))
        signals, visual = as_text(slide.get("content_signals")), as_text(slide.get("visual_focus"))
        components = as_text(slide.get("components"))
        density = as_text(slide.get("density")).lower()
        families.append(family)
        if family in GENERIC_FAMILIES:
            errors.append(f"slide {label}: layout_family `{slide.get('layout_family')}` is too generic")
        if len(reason) < 18:
            errors.append(f"slide {label}: layout_reason is too short")
        if len(core) < 12:
            errors.append(f"slide {label}: core_message should be a judgment sentence")
        if density not in VALID_DENSITY:
            errors.append(f"slide {label}: invalid density `{slide.get('density')}`")
        rules = [("阶段", ["流程", "路线", "时间", "roadmap"], "stage/path signal should use roadmap/process/time expression"),
                 ("层级", ["架构", "分层", "泳道", "architecture"], "layer signal should use architecture/layer expression"),
                 ("比较", ["比较", "对比", "矩阵", "matrix"], "comparison signal should use comparison/matrix expression"),
                 ("数据", ["数据", "图表", "数字", "kpi", "chart"], "data signal should make data/chart/KPI the visual focus")]
        for keyword, expected, message in rules:
            if keyword in signals and not any(word in family + visual for word in expected):
                errors.append(f"slide {label}: {message}")
        if any(word in core.lower() for word in DEFAULT_END_WORDS) and idx == len(slides):
            errors.append(f"slide {label}: closing cannot default to a thank-you page")
        consulting_text = (components + " " + visual + " " + reason).lower()
        consulting_count = sum(1 for group in CONSULTING_GROUPS if any(marker in consulting_text for marker in group))
        if density in {"high", "高"} and consulting_count < 3:
            errors.append(
                f"slide {label}: high-density consulting page needs at least 3 distinct consulting element groups "
                "such as evidence, SO WHAT, source/caveat, insight sidebar, microchart, legend, or decision box"
            )
        if any(word in signals for word in ["数据", "指标", "数字", "政策", "条款", "评分"]):
            if not any(marker in consulting_text for marker in ["来源", "source", "口径", "证据", "evidence", "解读", "so what"]):
                errors.append(f"slide {label}: data/policy/scoring page needs source/evidence/interpretation components")
    for i in range(len(families) - 2):
        if families[i] and families[i] == families[i + 1] == families[i + 2]:
            errors.append(f"slides {i + 1}-{i + 3}: same layout_family repeated three times")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan")
    parser.add_argument("--require-confirmed", action="store_true")
    args = parser.parse_args()
    try:
        meta, slides = load_plan(Path(args.plan))
        errors = validate(slides)
        if args.require_confirmed and meta.get("approval_status") not in {"confirmed", "waived_by_user"}:
            errors.insert(0, "approval_status must be `confirmed` or `waived_by_user` before PPT generation")
        if args.require_confirmed and not as_text(meta.get("content_plan_version")):
            errors.insert(0, "content_plan_version is required before PPT generation")
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 2
    if errors:
        print("INVALID dynamic layout plan:")
        print("\n".join(f"- {item}" for item in errors))
        return 1
    print(f"VALID dynamic layout plan: {len(slides)} slides checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
