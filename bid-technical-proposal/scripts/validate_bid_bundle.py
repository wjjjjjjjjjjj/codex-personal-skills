#!/usr/bin/env python3
"""Validate the traceability bundle used by bid-technical-proposal.

Only the Python standard library is required.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPORT_VERSION = "1.1"

SOURCE_TYPES = {
    "tender",
    "amendment",
    "requirements",
    "scoring",
    "product",
    "user_confirmation",
    "standard",
    "other",
}
SOURCE_STATUSES = {
    "active",
    "partially_superseded",
    "superseded",
    "pending_confirmation",
}
SOURCE_LEVELS = {"A", "B", "C", "D", "E"}
HASH_REQUIRED_SOURCE_LEVELS = {"A", "B", "C"}
PROCUREMENT_SOURCE_TYPES = {"tender", "amendment", "requirements", "scoring"}
CAPABILITY_EVIDENCE_SOURCE_TYPES = {"product", "user_confirmation", "other"}
REQUIREMENT_TYPES = {
    "否决项",
    "强制项",
    "评分项",
    "功能",
    "非功能",
    "集成",
    "数据",
    "实施",
    "验收",
    "服务",
    "交付物",
    "格式",
    "证明材料",
    "其他",
}
APPLICABILITY_VALUES = {"适用", "不适用待确认", "不适用已确认"}
CAPABILITY_STATUSES = {
    "已具备",
    "条件具备",
    "定制实现",
    "第三方依赖",
    "不支持",
    "待核验",
}
RESPONSE_PROGRESS_VALUES = {
    "未处理",
    "已拆解",
    "已起草",
    "待证据/待确认",
    "已复核",
    "已锁定",
}
EVIDENCE_STATUSES = {
    "已核验可引用",
    "已取得待核验",
    "待补证",
    "证据失配",
    "无证据",
    "不适用",
}
DEVIATION_STATUSES = {
    "无偏离",
    "正偏离",
    "条件响应",
    "负偏离",
    "待澄清",
}
REVIEW_STATUSES = {"未复核", "内容复核通过", "证据复核通过", "已锁定"}
COMMITMENT_TYPES = {
    "能力",
    "性能",
    "进度",
    "SLA",
    "资源",
    "兼容性",
    "服务",
    "费用",
    "验收",
    "合规",
    "其他",
    # English aliases are retained for machine-generated legacy bundles.
    "sla",
    "performance",
    "compatibility",
    "security",
    "certification",
    "delivery",
    "scope",
    "commercial",
    "other",
}
CONFIRMATION_STATUSES = {
    "无需新增承诺",
    "沿用采购要求",
    "已审批",
    "待审批",
    "禁止承诺",
}
CONFLICT_STATUSES = {"无冲突", "有冲突", "待核验"}
DISPOSITIONS = {"保留", "收窄", "改为条件承诺", "删除", "升级确认"}
MARKER_VALUES = {"无", "★", "▲", "#", "*"}
MANDATORY_VALUES = {"是", "否"}
SCORE_METHODS = {"客观计分", "分档评分", "横向评审", "主观评审", "否决关联"}

SOURCE_FIELDS = {
    "source_id",
    "source_level",
    "title",
    "source_type",
    "publisher",
    "file",
    "version",
    "effective_date",
    "received_at",
    "priority",
    "hash_sha256",
    "location",
    "scope",
    "status",
    "supersedes",
    "registered_by",
    "notes",
}
SOURCE_REQUIREMENT_FIELDS = {
    "requirement_id",
    "parent_id",
    "source_ref",
    "requirement_text",
    "requirement_type",
    "marker",
    "mandatory",
    "score_id",
    "score_text",
    "score_max",
    "score_method",
    "full_score_action",
    "full_score_content",
    "full_score_evidence",
    "full_score_format",
    "score_threshold",
    "deduction_triggers",
    "acceptance_evidence_requirement",
    "notes",
}
BASELINE_MATCH_FIELDS = (
    "parent_id",
    "source_ref",
    "requirement_text",
    "requirement_type",
    "marker",
)
TRACE_FIELDS = {
    "requirement_id",
    "parent_id",
    "source_ref",
    "requirement_text",
    "requirement_type",
    "marker",
    "action",
    "object_scope",
    "constraints",
    "acceptance_evidence_requirement",
    "response_section",
    "applicability",
    "capability_status",
    "capability_confirmer",
    "capability_confirmed_at",
    "response_progress",
    "evidence_refs",
    "evidence_status",
    "commitment_refs",
    "deviation_status",
    "deviation_note",
    "owner",
    "review_status",
    "notes",
}
COMMITMENT_FIELDS = {
    "commitment_id",
    "commitment_type",
    "original_text",
    "final_text",
    "requirement_refs",
    "response_section",
    "source_ref",
    "evidence_refs",
    "quantified_value",
    "conditions",
    "owner",
    "confirmation_status",
    "approver",
    "approval_date",
    "conflict_check",
    "disposition",
    "notes",
}

PLACEHOLDER_PATTERNS = (
    re.compile(r"【\s*(?:待|需)[^】]{0,40}】"),
    re.compile(r"\[\s*(?:待|需)[^\]]{0,40}\]"),
    re.compile(r"\b(?:TBD|TODO|FIXME)\b", re.IGNORECASE),
    re.compile(r"_{4,}"),
    re.compile(r"\{\{[^{}]{1,80}\}\}"),
    re.compile(r"<\s*(?:待|需)[^>]{0,40}>"),
)
QUANTIFIED_CLAIM_RE = re.compile(
    r"\d|%|％|小时|分钟|秒|天|日|工作日|个月|年|并发|QPS|TPS|GB|TB|PB",
    re.IGNORECASE,
)
ABSOLUTE_CLAIM_RE = re.compile(
    r"(?:终身|永久|免费|不限(?:次数|期限|数量)?|无条件|无需(?:任何)?前置条件|"
    r"全部(?:包含|支持|覆盖)?|任何情况下|所有(?:环境|场景|版本)|"
    r"不受[^，。；;]{0,30}约束|零故障|零停机|自主可控|"
    r"无缝兼容|国内领先|百分之百|100\s*[%％])",
    re.IGNORECASE,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def find_placeholders(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    found: list[str] = []
    for pattern in PLACEHOLDER_PATTERNS:
        found.extend(match.group(0) for match in pattern.finditer(value))
    return found


def split_refs(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[;；\n]+", value or "") if part.strip()]


def parse_ref(value: str) -> tuple[str, str]:
    """Return (source_id, locator) from SRC-001#page=12 or SRC-001@section."""
    parts = re.split(r"[#@]", value.strip(), maxsplit=1)
    source_id = parts[0].strip()
    locator = parts[1].strip() if len(parts) == 2 else ""
    return source_id, locator


class Report:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.issues: list[dict[str, Any]] = []

    def add(
        self,
        severity: str,
        code: str,
        message: str,
        *,
        file: str = "",
        record: str = "",
        field: str = "",
        match: str = "",
    ) -> None:
        issue: dict[str, Any] = {
            "severity": severity,
            "code": code,
            "message": message,
        }
        for key, value in {
            "file": file,
            "record": record,
            "field": field,
            "match": match,
        }.items():
            if value:
                issue[key] = value
        self.issues.append(issue)

    def gate(self) -> str:
        return "warning" if self.mode == "draft" else "error"

    def summary(self) -> dict[str, int]:
        return {
            "errors": sum(i["severity"] == "error" for i in self.issues),
            "warnings": sum(i["severity"] == "warning" for i in self.issues),
            "info": sum(i["severity"] == "info" for i in self.issues),
        }


def load_json(path: Path, report: Report) -> Any:
    if not path.is_file():
        report.add("error", "FILE_MISSING", "Required file does not exist.", file=str(path))
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        report.add(
            "error",
            "JSON_INVALID",
            f"Cannot read valid JSON: {exc}",
            file=str(path),
        )
        return None


def load_csv(path: Path, required: set[str], report: Report) -> list[dict[str, str]]:
    if not path.is_file():
        report.add("error", "FILE_MISSING", "Required file does not exist.", file=str(path))
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            blank_headers = [index + 1 for index, name in enumerate(fieldnames) if not name]
            if blank_headers:
                report.add(
                    "error",
                    "CSV_BLANK_HEADER",
                    "Blank column names at positions: "
                    + ", ".join(str(index) for index in blank_headers),
                    file=str(path),
                )
            duplicate_headers = sorted(
                {name for name in fieldnames if name and fieldnames.count(name) > 1}
            )
            if duplicate_headers:
                report.add(
                    "error",
                    "CSV_DUPLICATE_HEADER",
                    "Duplicate column names: " + ", ".join(duplicate_headers),
                    file=str(path),
                )
            headers = {name for name in fieldnames if name}
            missing = sorted(required - headers)
            if missing:
                report.add(
                    "error",
                    "CSV_FIELDS_MISSING",
                    "Missing required columns: " + ", ".join(missing),
                    file=str(path),
                )
            extra = sorted(headers - required)
            if extra:
                report.add(
                    "info",
                    "CSV_EXTRA_COLUMNS",
                    "Additional named columns are retained: " + ", ".join(extra),
                    file=str(path),
                )
            rows: list[dict[str, str]] = []
            for line_number, row in enumerate(reader, start=2):
                if None in row:
                    report.add(
                        "error",
                        "CSV_EXTRA_CELLS",
                        "Row has more cells than the header, often caused by an "
                        "unescaped comma.",
                        file=str(path),
                        record=f"row:{line_number}",
                    )
                missing_cells = [
                    name for name in fieldnames if name and row.get(name) is None
                ]
                if missing_cells:
                    report.add(
                        "error",
                        "CSV_MISSING_CELLS",
                        "Row has fewer cells than the header: "
                        + ", ".join(missing_cells),
                        file=str(path),
                        record=f"row:{line_number}",
                    )
                rows.append(
                    {
                        name: (row.get(name) or "").strip()
                        for name in fieldnames
                        if name
                    }
                )
            return rows
    except (OSError, UnicodeError, csv.Error) as exc:
        report.add(
            "error",
            "CSV_INVALID",
            f"Cannot read valid CSV: {exc}",
            file=str(path),
        )
        return []


def check_required_keys(
    obj: dict[str, Any],
    required: Iterable[str],
    report: Report,
    *,
    file: Path,
    record: str,
) -> None:
    for field in sorted(required):
        if field not in obj:
            report.add(
                "error",
                "FIELD_MISSING",
                "Required field is absent.",
                file=str(file),
                record=record,
                field=field,
            )


def check_placeholders(
    row: dict[str, Any],
    report: Report,
    *,
    file: Path,
    record: str,
) -> None:
    for field, value in row.items():
        for placeholder in find_placeholders(value):
            report.add(
                report.gate(),
                "PLACEHOLDER_FOUND",
                "Placeholder remains in a gated field.",
                file=str(file),
                record=record,
                field=field,
                match=placeholder,
            )


def validate_ref_cell(
    value: str,
    source_status: dict[str, str],
    report: Report,
    *,
    file: Path,
    record: str,
    field: str,
    locator_required: bool,
) -> None:
    for raw_ref in split_refs(value):
        source_id, locator = parse_ref(raw_ref)
        if source_id not in source_status:
            report.add(
                "error",
                "SOURCE_REF_UNKNOWN",
                f"Referenced source_id does not exist: {source_id}",
                file=str(file),
                record=record,
                field=field,
                match=raw_ref,
            )
            continue
        lifecycle_status = source_status[source_id]
        if lifecycle_status == "superseded":
            report.add(
                report.gate(),
                "SOURCE_REF_SUPERSEDED",
                f"Reference points to a superseded source: {source_id}",
                file=str(file),
                record=record,
                field=field,
                match=raw_ref,
            )
        elif lifecycle_status == "partially_superseded":
            report.add(
                report.gate(),
                "SOURCE_REF_PARTIALLY_SUPERSEDED",
                f"Reference points to a partially superseded source and requires "
                f"manual scope confirmation: {source_id}",
                file=str(file),
                record=record,
                field=field,
                match=raw_ref,
            )
        elif lifecycle_status == "pending_confirmation":
            report.add(
                report.gate(),
                "SOURCE_REF_PENDING_CONFIRMATION",
                f"Reference points to a source whose lifecycle status is not final: "
                f"{source_id}",
                file=str(file),
                record=record,
                field=field,
                match=raw_ref,
            )
        if locator_required and not locator:
            report.add(
                report.gate(),
                "SOURCE_LOCATOR_MISSING",
                "Source reference has no #locator or @locator.",
                file=str(file),
                record=record,
                field=field,
                match=raw_ref,
            )


def validate_sources(
    path: Path, report: Report
) -> tuple[dict[str, str], dict[str, str], int]:
    data = load_json(path, report)
    if not isinstance(data, dict):
        if data is not None:
            report.add("error", "SOURCE_ROOT_INVALID", "JSON root must be an object.", file=str(path))
        return {}, {}, 0

    check_required_keys(
        data,
        {"schema_version", "project_name", "generated_at", "sources"},
        report,
        file=path,
        record="root",
    )
    if is_blank(data.get("project_name")):
        report.add(
            report.gate(),
            "PROJECT_NAME_BLANK",
            "project_name is blank.",
            file=str(path),
            record="root",
            field="project_name",
        )
    if is_blank(data.get("generated_at")):
        report.add(
            report.gate(),
            "GENERATED_AT_BLANK",
            "generated_at is blank.",
            file=str(path),
            record="root",
            field="generated_at",
        )
    sources = data.get("sources")
    if not isinstance(sources, list):
        report.add(
            "error",
            "SOURCES_INVALID",
            "sources must be an array.",
            file=str(path),
            record="root",
            field="sources",
        )
        return {}, {}, 0
    if not sources:
        report.add(
            report.gate(),
            "SOURCES_EMPTY",
            "No source records are present.",
            file=str(path),
            record="root",
            field="sources",
        )

    source_status: dict[str, str] = {}
    source_types: dict[str, str] = {}
    supersedes_refs: list[tuple[str, str, str]] = []
    for index, source in enumerate(sources, start=1):
        record = f"sources[{index}]"
        if not isinstance(source, dict):
            report.add(
                "error",
                "SOURCE_RECORD_INVALID",
                "Source record must be an object.",
                file=str(path),
                record=record,
            )
            continue
        check_required_keys(source, SOURCE_FIELDS, report, file=path, record=record)
        source_id = str(source.get("source_id", "")).strip()
        if not source_id:
            report.add(
                "error",
                "SOURCE_ID_BLANK",
                "source_id cannot be blank.",
                file=str(path),
                record=record,
                field="source_id",
            )
        elif source_id in source_status:
            report.add(
                "error",
                "SOURCE_ID_DUPLICATE",
                f"Duplicate source_id: {source_id}",
                file=str(path),
                record=record,
                field="source_id",
            )
        source_type = str(source.get("source_type", "")).strip()
        source_level = str(source.get("source_level", "")).strip().upper()
        status = str(source.get("status", "")).strip()
        if source_type not in SOURCE_TYPES:
            report.add(
                "error",
                "SOURCE_TYPE_INVALID",
                f"Unsupported source_type: {source_type or '<blank>'}",
                file=str(path),
                record=record,
                field="source_type",
            )
        if source_level not in SOURCE_LEVELS:
            report.add(
                "error",
                "SOURCE_LEVEL_INVALID",
                f"Unsupported source_level: {source_level or '<blank>'}",
                file=str(path),
                record=record,
                field="source_level",
            )
        if status not in SOURCE_STATUSES:
            report.add(
                "error",
                "SOURCE_STATUS_INVALID",
                f"Unsupported source status: {status or '<blank>'}",
                file=str(path),
                record=record,
                field="status",
            )
        elif status == "pending_confirmation":
            report.add(
                report.gate(),
                "SOURCE_STATUS_NOT_FINAL",
                "Source lifecycle status remains pending confirmation.",
                file=str(path),
                record=record,
                field="status",
            )
        elif status == "partially_superseded" and is_blank(source.get("notes")):
            report.add(
                report.gate(),
                "PARTIAL_SUPERSESSION_SCOPE_MISSING",
                "partially_superseded requires notes describing the surviving and "
                "replaced scope.",
                file=str(path),
                record=record,
                field="notes",
            )
        priority = source.get("priority")
        if not isinstance(priority, int) or isinstance(priority, bool) or priority < 1:
            report.add(
                "error",
                "SOURCE_PRIORITY_INVALID",
                "priority must be a positive integer; lower numbers mean higher priority.",
                file=str(path),
                record=record,
                field="priority",
            )
        hash_sha256 = str(source.get("hash_sha256", "")).strip()
        if source_level in HASH_REQUIRED_SOURCE_LEVELS and not hash_sha256:
            report.add(
                report.gate(),
                "SOURCE_HASH_REQUIRED",
                "A/B/C source records require a SHA-256 file fingerprint.",
                file=str(path),
                record=record,
                field="hash_sha256",
            )
        elif hash_sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", hash_sha256):
            report.add(
                "error",
                "SOURCE_HASH_INVALID",
                "hash_sha256 must be a 64-character hexadecimal digest.",
                file=str(path),
                record=record,
                field="hash_sha256",
            )
        if not isinstance(source.get("supersedes"), list):
            report.add(
                "error",
                "SOURCE_SUPERSEDES_INVALID",
                "supersedes must be an array of source_id values.",
                file=str(path),
                record=record,
                field="supersedes",
            )
        else:
            for superseded_id in source.get("supersedes", []):
                supersedes_refs.append((source_id, str(superseded_id).strip(), record))
        for field in (
            "title",
            "publisher",
            "file",
            "version",
            "effective_date",
            "received_at",
            "location",
            "scope",
            "registered_by",
        ):
            if is_blank(source.get(field)):
                report.add(
                    report.gate(),
                    "SOURCE_FIELD_BLANK",
                    "Required source metadata is blank.",
                    file=str(path),
                    record=record,
                    field=field,
                )
        check_placeholders(source, report, file=path, record=record)
        if source_id:
            source_status.setdefault(source_id, status)
            source_types.setdefault(source_id, source_type)
    for source_id, superseded_id, record in supersedes_refs:
        if not superseded_id or superseded_id not in source_status:
            report.add(
                "error",
                "SUPERSEDES_REF_UNKNOWN",
                f"supersedes references an unknown source_id: {superseded_id or '<blank>'}",
                file=str(path),
                record=record,
                field="supersedes",
            )
        elif superseded_id == source_id:
            report.add(
                "error",
                "SUPERSEDES_SELF_REFERENCE",
                "A source cannot supersede itself.",
                file=str(path),
                record=record,
                field="supersedes",
            )
    return source_status, source_types, len(sources)


def validate_source_requirements(
    path: Path,
    source_status: dict[str, str],
    report: Report,
) -> tuple[dict[str, dict[str, str]], int]:
    """Validate the source-derived requirement/scoring baseline.

    This register is intentionally independent from technical_traceability.csv.
    The latter may enrich a requirement with response/evidence state, but it may
    not define which source requirements exist or rewrite immutable source facts.
    """

    rows = load_csv(path, SOURCE_REQUIREMENT_FIELDS, report)
    if not rows:
        report.add(
            report.gate(),
            "SOURCE_REQUIREMENTS_EMPTY",
            "No source requirement baseline rows are present.",
            file=str(path),
        )
        return {}, 0

    baseline: dict[str, dict[str, str]] = {}
    parent_links: list[tuple[str, str, str]] = []
    scoring_fields = (
        "score_text",
        "score_max",
        "score_method",
        "full_score_action",
        "full_score_content",
        "full_score_evidence",
        "full_score_format",
        "score_threshold",
        "deduction_triggers",
    )
    required_scoring_fields = (
        "score_text",
        "score_max",
        "score_method",
        "full_score_action",
        "full_score_content",
        "deduction_triggers",
    )

    for index, row in enumerate(rows, start=2):
        requirement_id = row.get("requirement_id", "")
        record = requirement_id or f"row:{index}"
        if not requirement_id:
            report.add(
                "error",
                "SOURCE_REQUIREMENT_ID_BLANK",
                "requirement_id cannot be blank in the source baseline.",
                file=str(path),
                record=record,
                field="requirement_id",
            )
        elif requirement_id in baseline:
            report.add(
                "error",
                "SOURCE_REQUIREMENT_ID_DUPLICATE",
                f"Duplicate baseline requirement_id: {requirement_id}",
                file=str(path),
                record=record,
                field="requirement_id",
            )
        else:
            baseline[requirement_id] = row

        parent_id = row.get("parent_id", "")
        if requirement_id and parent_id:
            parent_links.append((record, requirement_id, parent_id))

        for field in ("source_ref", "requirement_text", "requirement_type", "marker", "mandatory"):
            if not row.get(field):
                report.add(
                    "error",
                    "SOURCE_REQUIREMENT_FIELD_BLANK",
                    "Required source requirement field is blank.",
                    file=str(path),
                    record=record,
                    field=field,
                )

        requirement_type = row.get("requirement_type", "")
        if requirement_type not in REQUIREMENT_TYPES:
            report.add(
                "error",
                "SOURCE_REQUIREMENT_TYPE_INVALID",
                f"Unsupported requirement_type: {requirement_type or '<blank>'}",
                file=str(path),
                record=record,
                field="requirement_type",
            )
        marker = row.get("marker", "")
        if marker not in MARKER_VALUES:
            report.add(
                "error",
                "SOURCE_REQUIREMENT_MARKER_INVALID",
                f"Unsupported marker: {marker or '<blank>'}",
                file=str(path),
                record=record,
                field="marker",
            )
        mandatory = row.get("mandatory", "")
        if mandatory not in MANDATORY_VALUES:
            report.add(
                "error",
                "SOURCE_REQUIREMENT_MANDATORY_INVALID",
                f"mandatory must be 是 or 否, got: {mandatory or '<blank>'}",
                file=str(path),
                record=record,
                field="mandatory",
            )

        if row.get("source_ref"):
            validate_ref_cell(
                row["source_ref"],
                source_status,
                report,
                file=path,
                record=record,
                field="source_ref",
                locator_required=True,
            )

        score_id = row.get("score_id", "")
        has_scoring_data = bool(score_id or any(row.get(field) for field in scoring_fields))
        if requirement_type == "评分项" and not score_id:
            report.add(
                "error",
                "SCORE_ID_REQUIRED",
                "requirement_type=评分项 requires score_id and a full-score baseline.",
                file=str(path),
                record=record,
                field="score_id",
            )
        if has_scoring_data and not score_id:
            report.add(
                "error",
                "SCORE_FIELDS_WITHOUT_ID",
                "Scoring fields cannot be populated without score_id.",
                file=str(path),
                record=record,
                field="score_id",
            )
        if score_id:
            for field in required_scoring_fields:
                if not row.get(field):
                    report.add(
                        "error",
                        "SCORE_BASELINE_FIELD_BLANK",
                        "A scored requirement is missing a required scoring baseline field.",
                        file=str(path),
                        record=record,
                        field=field,
                    )
            score_max = row.get("score_max", "")
            if score_max and not re.fullmatch(r"(?:0|[1-9]\d*)(?:\.\d+)?", score_max):
                report.add(
                    "error",
                    "SCORE_MAX_INVALID",
                    "score_max must be a non-negative decimal number.",
                    file=str(path),
                    record=record,
                    field="score_max",
                    match=score_max,
                )
            score_method = row.get("score_method", "")
            if score_method and score_method not in SCORE_METHODS:
                report.add(
                    "error",
                    "SCORE_METHOD_INVALID",
                    f"Unsupported score_method: {score_method}",
                    file=str(path),
                    record=record,
                    field="score_method",
                )

        check_placeholders(row, report, file=path, record=record)

    parent_map: dict[str, str] = {}
    for record, requirement_id, parent_id in parent_links:
        if parent_id == requirement_id:
            report.add(
                "error",
                "SOURCE_REQUIREMENT_PARENT_SELF_REFERENCE",
                "A source requirement cannot be its own parent.",
                file=str(path),
                record=record,
                field="parent_id",
                match=parent_id,
            )
        elif parent_id not in baseline:
            report.add(
                "error",
                "SOURCE_REQUIREMENT_PARENT_UNKNOWN",
                f"Referenced baseline parent_id does not exist: {parent_id}",
                file=str(path),
                record=record,
                field="parent_id",
                match=parent_id,
            )
        else:
            parent_map[requirement_id] = parent_id

    reported_cycles: set[frozenset[str]] = set()
    for start in parent_map:
        chain: list[str] = []
        current = start
        while current in parent_map:
            if current in chain:
                cycle = frozenset(chain[chain.index(current) :])
                if cycle not in reported_cycles:
                    reported_cycles.add(cycle)
                    report.add(
                        "error",
                        "SOURCE_REQUIREMENT_PARENT_CYCLE",
                        "Source requirement parent links contain a cycle: "
                        + " -> ".join(chain[chain.index(current) :] + [current]),
                        file=str(path),
                        record=start,
                        field="parent_id",
                    )
                break
            chain.append(current)
            current = parent_map[current]

    return baseline, len(rows)


def validate_traceability(
    path: Path,
    source_requirements: dict[str, dict[str, str]],
    source_status: dict[str, str],
    source_types: dict[str, str],
    commitment_ids: set[str],
    commitment_requirements: dict[str, set[str]],
    usable_commitments: set[str],
    positive_deviation_commitments: set[str],
    report: Report,
) -> tuple[set[str], dict[str, set[str]], int]:
    rows = load_csv(path, TRACE_FIELDS, report)
    if not rows:
        report.add(
            report.gate(),
            "TRACEABILITY_EMPTY",
            "No traceability rows are present.",
            file=str(path),
        )
        return set(), {}, 0

    seen: set[str] = set()
    parent_links: list[tuple[str, str, str]] = []
    trace_commitment_links: dict[str, set[str]] = {}
    unresolved_evidence = {"已取得待核验", "待补证", "证据失配", "无证据"}
    nonfinal_progress = {"未处理", "已拆解", "已起草", "待证据/待确认", "已复核"}
    for index, row in enumerate(rows, start=2):
        requirement_id = row.get("requirement_id", "")
        record = requirement_id or f"row:{index}"
        if not requirement_id:
            report.add(
                "error",
                "REQUIREMENT_ID_BLANK",
                "requirement_id cannot be blank.",
                file=str(path),
                record=record,
                field="requirement_id",
            )
        elif requirement_id in seen:
            report.add(
                "error",
                "REQUIREMENT_ID_DUPLICATE",
                f"Duplicate requirement_id: {requirement_id}",
                file=str(path),
                record=record,
                field="requirement_id",
            )
        else:
            seen.add(requirement_id)
        parent_id = row.get("parent_id", "")
        if requirement_id and parent_id:
            parent_links.append((record, requirement_id, parent_id))

        requirement_type = row.get("requirement_type", "")
        applicability = row.get("applicability", "")
        capability = row.get("capability_status", "")
        progress = row.get("response_progress", "")
        evidence_status = row.get("evidence_status", "")
        deviation = row.get("deviation_status", "")
        review_status = row.get("review_status", "")

        baseline_row = source_requirements.get(requirement_id)
        if baseline_row:
            for field in BASELINE_MATCH_FIELDS:
                if row.get(field, "") != baseline_row.get(field, ""):
                    report.add(
                        report.gate(),
                        "REQUIREMENT_BASELINE_FIELD_MISMATCH",
                        "Traceability cannot rewrite an immutable source requirement "
                        "field; update the source baseline only from an authoritative "
                        "source revision.",
                        file=str(path),
                        record=record,
                        field=field,
                        match=f"baseline={baseline_row.get(field, '')!r}; trace={row.get(field, '')!r}",
                    )

        mandatory_or_veto = bool(
            (baseline_row and baseline_row.get("mandatory") == "是")
            or (baseline_row and baseline_row.get("requirement_type") in {"强制项", "否决项"})
            or requirement_type in {"强制项", "否决项"}
        )
        blocked_mandatory_states: list[str] = []
        if capability == "不支持":
            blocked_mandatory_states.append("capability_status=不支持")
        if deviation in {"条件响应", "负偏离"}:
            blocked_mandatory_states.append(f"deviation_status={deviation}")
        if mandatory_or_veto and blocked_mandatory_states:
            report.add(
                report.gate(),
                "MANDATORY_OR_VETO_RESPONSE_BLOCKED",
                "A mandatory/veto requirement cannot enter a submission candidate "
                "as unsupported, conditionally responsive, or negatively deviated: "
                + ", ".join(blocked_mandatory_states),
                file=str(path),
                record=record,
                field="capability_status",
            )

        enum_checks = (
            ("requirement_type", requirement_type, REQUIREMENT_TYPES, "REQUIREMENT_TYPE_INVALID"),
            ("applicability", applicability, APPLICABILITY_VALUES, "APPLICABILITY_INVALID"),
            ("response_progress", progress, RESPONSE_PROGRESS_VALUES, "RESPONSE_PROGRESS_INVALID"),
            ("evidence_status", evidence_status, EVIDENCE_STATUSES, "EVIDENCE_STATUS_INVALID"),
            ("deviation_status", deviation, DEVIATION_STATUSES, "DEVIATION_STATUS_INVALID"),
            ("review_status", review_status, REVIEW_STATUSES, "REVIEW_STATUS_INVALID"),
        )
        for field, value, allowed, code in enum_checks:
            if value not in allowed:
                report.add(
                    "error",
                    code,
                    f"Unsupported {field}: {value or '<blank>'}",
                    file=str(path),
                    record=record,
                    field=field,
                )

        if applicability == "适用":
            if capability not in CAPABILITY_STATUSES:
                report.add(
                    "error",
                    "CAPABILITY_STATUS_INVALID",
                    f"Applicable item requires a supported capability_status: {capability or '<blank>'}",
                    file=str(path),
                    record=record,
                    field="capability_status",
                )
            elif capability != "待核验":
                for field in ("capability_confirmer", "capability_confirmed_at"):
                    if not row.get(field):
                        report.add(
                            report.gate(),
                            "CAPABILITY_CONFIRMATION_MISSING",
                            "A decided capability status requires confirmer and date.",
                            file=str(path),
                            record=record,
                            field=field,
                        )
            if evidence_status == "不适用":
                report.add(
                    report.gate(),
                    "EVIDENCE_NOT_APPLICABLE_CONFLICT",
                    "An applicable requirement cannot use evidence_status=不适用.",
                    file=str(path),
                    record=record,
                    field="evidence_status",
                )
        elif capability:
            report.add(
                report.gate(),
                "CAPABILITY_PRESENT_FOR_NOT_APPLICABLE",
                "A non-applicable item should leave capability_status blank.",
                file=str(path),
                record=record,
                field="capability_status",
            )

        for field in (
            "requirement_text",
            "source_ref",
            "action",
            "object_scope",
            "owner",
        ):
            if not row.get(field):
                report.add(
                    "error",
                    "TRACE_FIELD_BLANK",
                    "Required traceability field is blank.",
                    file=str(path),
                    record=record,
                    field=field,
                )

        if row.get("source_ref"):
            validate_ref_cell(
                row["source_ref"],
                source_status,
                report,
                file=path,
                record=record,
                field="source_ref",
                locator_required=True,
            )
        if row.get("evidence_refs"):
            validate_ref_cell(
                row["evidence_refs"],
                source_status,
                report,
                file=path,
                record=record,
                field="evidence_refs",
                locator_required=True,
            )
        if applicability == "适用" and capability in {
            "已具备",
            "条件具备",
            "定制实现",
            "第三方依赖",
        }:
            evidence_source_ids = {
                parse_ref(raw_ref)[0]
                for raw_ref in split_refs(row.get("evidence_refs", ""))
            }
            if not any(
                source_types.get(source_id) in CAPABILITY_EVIDENCE_SOURCE_TYPES
                for source_id in evidence_source_ids
            ):
                report.add(
                    report.gate(),
                    "CAPABILITY_EVIDENCE_SOURCE_ROLE_INVALID",
                    "Procurement requirement sources can prove what is required but "
                    "cannot alone prove bidder capability. Add product, written "
                    "confirmation, or another registered capability-evidence source.",
                    file=str(path),
                    record=record,
                    field="evidence_refs",
                )
        if evidence_status == "已核验可引用" and not row.get("evidence_refs"):
            report.add(
                report.gate(),
                "VERIFIED_EVIDENCE_REF_MISSING",
                "已核验可引用 requires at least one located evidence reference.",
                file=str(path),
                record=record,
                field="evidence_refs",
            )
        for commitment_ref in split_refs(row.get("commitment_refs", "")):
            if requirement_id:
                trace_commitment_links.setdefault(requirement_id, set()).add(
                    commitment_ref
                )
            if commitment_ref not in commitment_ids:
                report.add(
                    "error",
                    "COMMITMENT_REF_UNKNOWN",
                    f"Referenced commitment_id does not exist: {commitment_ref}",
                    file=str(path),
                    record=record,
                    field="commitment_refs",
                    match=commitment_ref,
                )
            elif commitment_ref not in usable_commitments:
                report.add(
                    report.gate(),
                    "COMMITMENT_REF_NOT_USABLE",
                    f"{commitment_ref} is deleted, prohibited, conflicted, or not "
                    "finally approved for response use.",
                    file=str(path),
                    record=record,
                    field="commitment_refs",
                    match=commitment_ref,
                )
            elif requirement_id and requirement_id not in commitment_requirements.get(
                commitment_ref, set()
            ):
                report.add(
                    "error",
                    "COMMITMENT_LINK_NOT_RECIPROCAL",
                    f"{commitment_ref} does not link back to {requirement_id} in "
                    "commitment_register.csv.",
                    file=str(path),
                    record=record,
                    field="commitment_refs",
                    match=commitment_ref,
                )

        if progress not in {"未处理", "已拆解"} and not row.get("response_section"):
            report.add(
                report.gate(),
                "RESPONSE_SECTION_BLANK",
                "Started response item has no response_section.",
                file=str(path),
                record=record,
                field="response_section",
            )
        if capability == "已具备":
            if evidence_status != "已核验可引用" or not row.get("evidence_refs"):
                report.add(
                    report.gate(),
                    "FULL_CAPABILITY_EVIDENCE_MISSING",
                    "已具备 requires verified evidence with a located source reference.",
                    file=str(path),
                    record=record,
                    field="evidence_refs",
                )
            if deviation not in {"无偏离", "正偏离"}:
                report.add(
                    report.gate(),
                    "FULL_CAPABILITY_DEVIATION_CONFLICT",
                    "已具备 can only be paired with 无偏离 or an approved 正偏离.",
                    file=str(path),
                    record=record,
                    field="deviation_status",
                )
        if deviation == "正偏离":
            if not row.get("deviation_note"):
                report.add(
                    report.gate(),
                    "POSITIVE_DEVIATION_NOTE_MISSING",
                    "正偏离 requires a concrete explanation of the additional scope "
                    "and boundary.",
                    file=str(path),
                    record=record,
                    field="deviation_note",
                )
            positive_refs = split_refs(row.get("commitment_refs", ""))
            if not positive_refs:
                report.add(
                    report.gate(),
                    "POSITIVE_DEVIATION_COMMITMENT_MISSING",
                    "正偏离 adds delivery scope and must link to a closed commitment.",
                    file=str(path),
                    record=record,
                    field="commitment_refs",
                )
            elif any(
                commitment_ref not in positive_deviation_commitments
                for commitment_ref in positive_refs
            ):
                report.add(
                    report.gate(),
                    "POSITIVE_DEVIATION_COMMITMENT_NOT_APPROVED",
                    "Every commitment authorizing 正偏离 must be an active 已审批 "
                    "record with evidence, approver, approval date, no conflict, and "
                    "a final retained disposition.",
                    file=str(path),
                    record=record,
                    field="commitment_refs",
                    match="; ".join(positive_refs),
                )
        if capability in {"条件具备", "定制实现", "第三方依赖"} and deviation != "条件响应":
            report.add(
                report.gate(),
                "CONDITIONAL_DEVIATION_MISMATCH",
                f"{capability} must be paired with 条件响应.",
                file=str(path),
                record=record,
                field="deviation_status",
            )
        if capability == "不支持" and deviation != "负偏离":
            report.add(
                report.gate(),
                "UNSUPPORTED_DEVIATION_MISMATCH",
                "不支持 must be paired with 负偏离.",
                file=str(path),
                record=record,
                field="deviation_status",
            )
        if capability == "待核验" and deviation != "待澄清":
            report.add(
                report.gate(),
                "PENDING_CAPABILITY_DEVIATION_MISMATCH",
                "待核验 must be paired with 待澄清.",
                file=str(path),
                record=record,
                field="deviation_status",
            )
        if capability in {"条件具备", "定制实现", "第三方依赖", "不支持"} and not row.get(
            "deviation_note"
        ):
            report.add(
                report.gate(),
                "DEVIATION_NOTE_MISSING",
                f"{capability} requires a concrete deviation_note.",
                file=str(path),
                record=record,
                field="deviation_note",
            )
        if applicability in {"不适用待确认", "不适用已确认"} and not (
            row.get("deviation_note") or row.get("notes")
        ):
            report.add(
                report.gate(),
                "NOT_APPLICABLE_BASIS_MISSING",
                "Non-applicable judgment requires a located basis or explanation.",
                file=str(path),
                record=record,
                field="deviation_note",
            )
        if applicability == "不适用已确认":
            if evidence_status != "不适用" or not row.get("evidence_refs"):
                report.add(
                    report.gate(),
                    "NOT_APPLICABLE_EVIDENCE_BASIS_MISSING",
                    "不适用已确认 requires evidence_status=不适用 and a located "
                    "basis in evidence_refs.",
                    file=str(path),
                    record=record,
                    field="evidence_refs",
                )
            if deviation != "无偏离":
                report.add(
                    report.gate(),
                    "NOT_APPLICABLE_DEVIATION_CONFLICT",
                    "不适用已确认 must use deviation_status=无偏离.",
                    file=str(path),
                    record=record,
                    field="deviation_status",
                )
        elif applicability == "不适用待确认" and evidence_status == "不适用":
            report.add(
                report.gate(),
                "NOT_APPLICABLE_EVIDENCE_PREMATURE",
                "Evidence cannot be marked 不适用 before applicability is confirmed.",
                file=str(path),
                record=record,
                field="evidence_status",
            )

        if applicability == "不适用待确认":
            report.add(
                report.gate(),
                "APPLICABILITY_NOT_FINAL",
                "Applicability remains unconfirmed.",
                file=str(path),
                record=record,
                field="applicability",
            )
        if capability == "待核验":
            report.add(
                report.gate(),
                "CAPABILITY_NOT_FINAL",
                "Capability remains unverified.",
                file=str(path),
                record=record,
                field="capability_status",
            )
        if progress in nonfinal_progress:
            report.add(
                report.gate(),
                "RESPONSE_PROGRESS_NOT_FINAL",
                f"Response remains non-final: response_progress={progress}.",
                file=str(path),
                record=record,
                field="response_progress",
            )
        if evidence_status in unresolved_evidence:
            report.add(
                report.gate(),
                "EVIDENCE_NOT_FINAL",
                f"Evidence remains non-final: evidence_status={evidence_status}.",
                file=str(path),
                record=record,
                field="evidence_status",
            )
        if deviation == "待澄清":
            report.add(
                report.gate(),
                "DEVIATION_NOT_FINAL",
                "Deviation remains pending clarification.",
                file=str(path),
                record=record,
                field="deviation_status",
            )
        if review_status != "已锁定":
            report.add(
                report.gate(),
                "REVIEW_NOT_LOCKED",
                f"Review is not locked: review_status={review_status or '<blank>'}.",
                file=str(path),
                record=record,
                field="review_status",
            )
        check_placeholders(row, report, file=path, record=record)

    parent_map: dict[str, str] = {}
    for record, requirement_id, parent_id in parent_links:
        if parent_id == requirement_id:
            report.add(
                "error",
                "PARENT_SELF_REFERENCE",
                "A requirement cannot be its own parent.",
                file=str(path),
                record=record,
                field="parent_id",
                match=parent_id,
            )
        elif parent_id not in seen:
            report.add(
                "error",
                "PARENT_REF_UNKNOWN",
                f"Referenced parent_id does not exist: {parent_id}",
                file=str(path),
                record=record,
                field="parent_id",
                match=parent_id,
            )
        else:
            parent_map[requirement_id] = parent_id

    reported_cycles: set[frozenset[str]] = set()
    for start in parent_map:
        chain: list[str] = []
        current = start
        while current in parent_map:
            if current in chain:
                cycle = frozenset(chain[chain.index(current) :])
                if cycle not in reported_cycles:
                    reported_cycles.add(cycle)
                    report.add(
                        "error",
                        "PARENT_CYCLE",
                        "Requirement parent links contain a cycle: "
                        + " -> ".join(chain[chain.index(current) :] + [current]),
                        file=str(path),
                        record=start,
                        field="parent_id",
                    )
                break
            chain.append(current)
            current = parent_map[current]

    baseline_ids = set(source_requirements)
    missing_in_trace = sorted(baseline_ids - seen)
    extra_in_trace = sorted(seen - baseline_ids)
    if missing_in_trace:
        report.add(
            report.gate(),
            "REQUIREMENT_BASELINE_MISSING_IN_TRACE",
            "technical_traceability.csv is missing source baseline IDs: "
            + ", ".join(missing_in_trace),
            file=str(path),
            field="requirement_id",
        )
    if extra_in_trace:
        report.add(
            report.gate(),
            "TRACE_REQUIREMENT_NOT_IN_BASELINE",
            "technical_traceability.csv contains IDs absent from the independent "
            "source baseline: "
            + ", ".join(extra_in_trace),
            file=str(path),
            field="requirement_id",
        )
    return seen, trace_commitment_links, len(rows)


def validate_commitments(
    path: Path,
    source_status: dict[str, str],
    source_types: dict[str, str],
    report: Report,
) -> tuple[
    set[str],
    list[tuple[str, str]],
    dict[str, set[str]],
    set[str],
    set[str],
    set[str],
    int,
]:
    rows = load_csv(path, COMMITMENT_FIELDS, report)
    if not rows:
        report.add(
            "info",
            "COMMITMENTS_EMPTY",
            "No commitment rows are present; submission text scanning must still "
            "confirm that no risky commitment exists.",
            file=str(path),
        )
        return set(), [], {}, set(), set(), set(), 0

    seen: set[str] = set()
    requirement_links: list[tuple[str, str]] = []
    commitment_requirements: dict[str, set[str]] = {}
    retained_commitments: set[str] = set()
    usable_commitments: set[str] = set()
    positive_deviation_commitments: set[str] = set()
    for index, row in enumerate(rows, start=2):
        commitment_id = row.get("commitment_id", "")
        record = commitment_id or f"row:{index}"
        if not commitment_id:
            report.add(
                "error",
                "COMMITMENT_ID_BLANK",
                "commitment_id cannot be blank.",
                file=str(path),
                record=record,
                field="commitment_id",
            )
        elif commitment_id in seen:
            report.add(
                "error",
                "COMMITMENT_ID_DUPLICATE",
                f"Duplicate commitment_id: {commitment_id}",
                file=str(path),
                record=record,
                field="commitment_id",
            )
        seen.add(commitment_id)

        commitment_type = row.get("commitment_type", "")
        confirmation = row.get("confirmation_status", "")
        conflict = row.get("conflict_check", "")
        disposition = row.get("disposition", "")
        removed = disposition == "删除"
        original_text = row.get("original_text", "")
        final_text = row.get("final_text", "")
        if commitment_id and not removed:
            retained_commitments.add(commitment_id)

        enum_checks = (
            ("commitment_type", commitment_type, COMMITMENT_TYPES, "COMMITMENT_TYPE_INVALID"),
            (
                "confirmation_status",
                confirmation,
                CONFIRMATION_STATUSES,
                "CONFIRMATION_STATUS_INVALID",
            ),
            ("conflict_check", conflict, CONFLICT_STATUSES, "CONFLICT_CHECK_INVALID"),
            ("disposition", disposition, DISPOSITIONS, "DISPOSITION_INVALID"),
        )
        for field, value, allowed, code in enum_checks:
            if value not in allowed:
                report.add(
                    "error",
                    code,
                    f"Unsupported {field}: {value or '<blank>'}",
                    file=str(path),
                    record=record,
                    field=field,
                )

        for field in (
            "original_text",
            "requirement_refs",
            "source_ref",
            "conditions",
            "owner",
        ):
            if not row.get(field):
                report.add(
                    report.gate(),
                    "COMMITMENT_FIELD_BLANK",
                    "Required commitment field is blank.",
                    file=str(path),
                    record=record,
                    field=field,
                )
        final_disposition = disposition in {"保留", "收窄", "改为条件承诺"}
        if final_disposition and not final_text:
            report.add(
                report.gate(),
                "COMMITMENT_FINAL_TEXT_BLANK",
                "A retained commitment requires final_text; only final_text may be "
                "copied into or whitelisted for the submission.",
                file=str(path),
                record=record,
                field="final_text",
            )
        if removed and final_text:
            report.add(
                report.gate(),
                "DELETED_COMMITMENT_FINAL_TEXT_PRESENT",
                "A deleted commitment must leave final_text blank so it cannot be "
                "reused accidentally.",
                file=str(path),
                record=record,
                field="final_text",
            )
        normalized_original = re.sub(r"\s+", "", original_text)
        normalized_final = re.sub(r"\s+", "", final_text)
        if disposition == "保留" and normalized_original and normalized_final != normalized_original:
            report.add(
                report.gate(),
                "RETAINED_COMMITMENT_TEXT_CHANGED",
                "disposition=保留 requires original_text and final_text to be identical; "
                "use 收窄 or 改为条件承诺 when wording changes.",
                file=str(path),
                record=record,
                field="final_text",
            )
        if disposition in {"收窄", "改为条件承诺"}:
            if normalized_original and normalized_final == normalized_original:
                report.add(
                    report.gate(),
                    "CHANGED_COMMITMENT_TEXT_UNCHANGED",
                    f"disposition={disposition} requires final_text to differ from "
                    "original_text.",
                    file=str(path),
                    record=record,
                    field="final_text",
                )
            if not row.get("notes"):
                report.add(
                    report.gate(),
                    "COMMITMENT_CHANGE_BASIS_MISSING",
                    f"disposition={disposition} requires notes describing the narrowed "
                    "scope or added conditions.",
                    file=str(path),
                    record=record,
                    field="notes",
                )
        if row.get("requirement_refs"):
            requirement_links.append((record, row["requirement_refs"]))
            commitment_requirements.setdefault(record, set()).update(
                split_refs(row["requirement_refs"])
            )
        if not removed and not row.get("response_section"):
            report.add(
                report.gate(),
                "COMMITMENT_RESPONSE_SECTION_BLANK",
                "Commitment retained in the response has no response_section.",
                file=str(path),
                record=record,
                field="response_section",
            )

        if row.get("source_ref"):
            validate_ref_cell(
                row["source_ref"],
                source_status,
                report,
                file=path,
                record=record,
                field="source_ref",
                locator_required=True,
            )
        source_ref_ids = {
            parse_ref(raw_ref)[0]
            for raw_ref in split_refs(row.get("source_ref", ""))
        }
        procurement_source_ok = any(
            source_types.get(source_id) in PROCUREMENT_SOURCE_TYPES
            for source_id in source_ref_ids
        )
        if confirmation == "沿用采购要求" and not procurement_source_ok:
            report.add(
                report.gate(),
                "COMMITMENT_PROCUREMENT_SOURCE_MISSING",
                "沿用采购要求 must cite a located procurement-authority source "
                "(tender, amendment, requirements, or scoring).",
                file=str(path),
                record=record,
                field="source_ref",
            )
        if row.get("evidence_refs"):
            validate_ref_cell(
                row["evidence_refs"],
                source_status,
                report,
                file=path,
                record=record,
                field="evidence_refs",
                locator_required=True,
            )

        if confirmation == "已审批":
            if not row.get("evidence_refs"):
                report.add(
                    report.gate(),
                    "COMMITMENT_EVIDENCE_MISSING",
                    "已审批 commitment has no evidence reference.",
                    file=str(path),
                    record=record,
                    field="evidence_refs",
                )
            for field, code in (
                ("approver", "APPROVER_MISSING"),
                ("approval_date", "APPROVAL_DATE_MISSING"),
            ):
                if not row.get(field):
                    report.add(
                        report.gate(),
                        code,
                        f"已审批 commitment has no {field}.",
                        file=str(path),
                        record=record,
                        field=field,
                    )
        if confirmation in {"待审批", "禁止承诺"} and not (
            confirmation == "禁止承诺" and removed
        ):
            report.add(
                report.gate(),
                "COMMITMENT_NOT_CLOSED",
                f"Commitment remains non-final: confirmation_status={confirmation}.",
                file=str(path),
                record=record,
                field="confirmation_status",
            )
        if conflict in {"有冲突", "待核验"} and not removed:
            report.add(
                report.gate(),
                "COMMITMENT_CONFLICT_NOT_CLOSED",
                f"Commitment conflict remains open: conflict_check={conflict}.",
                file=str(path),
                record=record,
                field="conflict_check",
            )
        if disposition == "升级确认":
            report.add(
                report.gate(),
                "COMMITMENT_DISPOSITION_NOT_FINAL",
                "Commitment still requires escalation.",
                file=str(path),
                record=record,
                field="disposition",
            )
        quantified_claim = bool(
            QUANTIFIED_CLAIM_RE.search(final_text)
            or row.get("quantified_value")
        )
        absolute_claim = bool(
            ABSOLUTE_CLAIM_RE.search(final_text)
        )
        if quantified_claim and confirmation == "无需新增承诺":
            report.add(
                report.gate(),
                "NUMERIC_COMMITMENT_STATUS_INVALID",
                "A quantified commitment cannot use 无需新增承诺; use "
                "沿用采购要求 or an evidence-backed 已审批 record.",
                file=str(path),
                record=record,
                field="confirmation_status",
            )
        if absolute_claim and confirmation == "无需新增承诺":
            report.add(
                report.gate(),
                "ABSOLUTE_COMMITMENT_STATUS_INVALID",
                "An absolute-scope commitment cannot use 无需新增承诺; use "
                "沿用采购要求 or an evidence-backed 已审批 record.",
                file=str(path),
                record=record,
                field="confirmation_status",
            )
        if quantified_claim and not row.get("quantified_value"):
            report.add(
                report.gate(),
                "QUANTIFIED_VALUE_MISSING",
                "Quantified commitment has no normalized quantified_value.",
                file=str(path),
                record=record,
                field="quantified_value",
            )
        has_common_closure = (
            not removed
            and conflict == "无冲突"
            and final_disposition
            and bool(final_text)
            and bool(row.get("source_ref"))
        )
        if confirmation == "已审批":
            approved_closure = has_common_closure and all(
                row.get(field)
                for field in ("evidence_refs", "approver", "approval_date")
            )
            if approved_closure and commitment_id:
                usable_commitments.add(commitment_id)
                positive_deviation_commitments.add(commitment_id)
        elif confirmation == "沿用采购要求":
            if has_common_closure and procurement_source_ok and commitment_id:
                usable_commitments.add(commitment_id)
        elif confirmation == "无需新增承诺":
            if (
                has_common_closure
                and not quantified_claim
                and not absolute_claim
                and (row.get("source_ref") or row.get("evidence_refs"))
                and commitment_id
            ):
                usable_commitments.add(commitment_id)
        # original_text is an audit trail and may preserve the superseded wording;
        # only final_text and active control fields are gated for submission use.
        check_placeholders(
            {field: value for field, value in row.items() if field != "original_text"},
            report,
            file=path,
            record=record,
        )
    return (
        seen,
        requirement_links,
        commitment_requirements,
        retained_commitments,
        usable_commitments,
        positive_deviation_commitments,
        len(rows),
    )


def validate_commitment_requirement_links(
    path: Path,
    links: list[tuple[str, str]],
    requirement_ids: set[str],
    trace_commitment_links: dict[str, set[str]],
    retained_commitments: set[str],
    report: Report,
) -> None:
    for record, raw_links in links:
        for requirement_ref in split_refs(raw_links):
            if requirement_ref not in requirement_ids:
                report.add(
                    "error",
                    "COMMITMENT_REQUIREMENT_REF_UNKNOWN",
                    f"Referenced requirement_id does not exist: {requirement_ref}",
                    file=str(path),
                    record=record,
                    field="requirement_refs",
                    match=requirement_ref,
                )
            elif (
                record in retained_commitments
                and record not in trace_commitment_links.get(requirement_ref, set())
            ):
                report.add(
                    "error",
                    "COMMITMENT_LINK_NOT_RECIPROCAL",
                    f"{record} links to {requirement_ref}, but that requirement does "
                    "not link back in technical_traceability.csv.",
                    file=str(path),
                    record=record,
                    field="requirement_refs",
                    match=requirement_ref,
                )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate source metadata, the independent source-requirement baseline, "
            "technical traceability, and commitment registers."
        )
    )
    parser.add_argument(
        "--bundle",
        type=Path,
        required=True,
        help="Directory containing the four register files.",
    )
    parser.add_argument(
        "--mode",
        choices=("draft", "submission"),
        default="draft",
        help="draft reports incomplete work as warnings; submission gates it as errors.",
    )
    parser.add_argument(
        "--source-register",
        default="source_register.json",
        help="Source register filename relative to --bundle.",
    )
    parser.add_argument(
        "--source-requirements",
        default="source_requirements.csv",
        help="Independent source requirement baseline filename relative to --bundle.",
    )
    parser.add_argument(
        "--traceability",
        default="technical_traceability.csv",
        help="Traceability filename relative to --bundle.",
    )
    parser.add_argument(
        "--commitments",
        default="commitment_register.csv",
        help="Commitment filename relative to --bundle.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON report path. The report is always printed to stdout.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bundle = args.bundle.resolve()
    paths = {
        "source_register": bundle / args.source_register,
        "source_requirements": bundle / args.source_requirements,
        "technical_traceability": bundle / args.traceability,
        "commitment_register": bundle / args.commitments,
    }
    report = Report(args.mode)
    source_status, source_types, source_count = validate_sources(
        paths["source_register"], report
    )
    source_requirements, source_requirement_count = validate_source_requirements(
        paths["source_requirements"], source_status, report
    )
    (
        commitment_ids,
        commitment_requirement_links,
        commitment_requirements,
        retained_commitments,
        usable_commitments,
        positive_deviation_commitments,
        commitment_count,
    ) = validate_commitments(
        paths["commitment_register"], source_status, source_types, report
    )
    requirement_ids, trace_commitment_links, trace_count = validate_traceability(
        paths["technical_traceability"],
        source_requirements,
        source_status,
        source_types,
        commitment_ids,
        commitment_requirements,
        usable_commitments,
        positive_deviation_commitments,
        report,
    )
    validate_commitment_requirement_links(
        paths["commitment_register"],
        commitment_requirement_links,
        requirement_ids,
        trace_commitment_links,
        retained_commitments,
        report,
    )
    counts = report.summary()
    counts.update(
        {
            "files_checked": 4,
            "sources": source_count,
            "source_requirements": source_requirement_count,
            "traceability_items": trace_count,
            "commitments": commitment_count,
        }
    )
    payload = {
        "tool": "validate_bid_bundle",
        "report_version": REPORT_VERSION,
        "generated_at": utc_now(),
        "mode": args.mode,
        "valid": counts["errors"] == 0,
        "files": {key: str(value) for key, value in paths.items()},
        "summary": counts,
        "issues": report.issues,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if payload["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
