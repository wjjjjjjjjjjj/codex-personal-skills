#!/usr/bin/env python3
"""Scan TXT, Markdown, or DOCX submission text for delivery risks.

Checks literal banned terms, old project names, placeholders, and numerical
commitments that are not present in an approved commitment register.
Only the Python standard library is required.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


REPORT_VERSION = "1.1"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PROCUREMENT_SOURCE_TYPES = {"tender", "amendment", "requirements", "scoring"}

PLACEHOLDER_PATTERNS = (
    re.compile(r"【\s*(?:待|需)[^】]{0,40}】"),
    re.compile(r"\[\s*(?:待|需)[^\]]{0,40}\]"),
    re.compile(r"\b(?:TBD|TODO|FIXME)\b", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z])X{2,}(?![A-Za-z])", re.IGNORECASE),
    re.compile(r"(?:\?{2,}|？{2,})"),
    re.compile(r"_{4,}"),
    re.compile(r"\{\{[^{}]{1,80}\}\}"),
    re.compile(r"<\s*(?:待|需)[^>]{0,40}>"),
)

RISK_NUMBER_RE = re.compile(
    r"(?:"
    r"\d+(?:\.\d+)?\s*(?:%|％|小时|分钟|秒|天|日|工作日|个月|月|年|人|次|"
    r"个|项|套|台|节点|路|门|批|份|家|条|页|并发|QPS|TPS|MB|GB|TB|PB|"
    r"万元|亿元|万|元)"
    r"|7\s*[×xX*]\s*24"
    r"|[零〇一二两三四五六七八九十百千万亿]+(?:个)?(?:小时|分钟|秒|天|日|"
    r"工作日|月|年|人|次|项|套|台|节点|路|门|批|份|家|条|页|并发|元)"
    r")",
    re.IGNORECASE,
)
BARE_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9.])\d+(?:\.\d+)?(?![A-Za-z0-9.])"
)
STRUCTURAL_ID_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:REQ|RQ|SC|SCORE|CM|COM|SRC|EV)"
    r"(?:-[A-Za-z0-9]+){1,}(?![A-Za-z0-9-])",
    re.IGNORECASE,
)
ABSOLUTE_CLAIM_RE = re.compile(
    r"(?:终身|永久|免费|不限(?:次数|期限|数量)?|无条件|无需(?:任何)?前置条件|"
    r"全部(?:包含|支持|覆盖)?|任何情况下|所有(?:环境|场景|版本)|"
    r"不受[^，。；;]{0,30}约束|零故障|零停机|自主可控|"
    r"无缝兼容|国内领先|百分之百|100\s*[%％])",
    re.IGNORECASE,
)
NON_COMMITMENT_DISCLAIMER_RE = re.compile(
    r"(?:不(?:作出|提供|包含|涉及)\s*[^。；;]{0,60}(?:量化|绝对化|免费|性能|服务|资源|"
    r"时限|范围)?[^。；;]{0,30}承诺|不对[^。；;]{0,80}(?:作出)?[^。；;]{0,30}承诺|"
    r"不承诺)",
    re.IGNORECASE,
)
RISK_KEYWORDS = (
    "承诺",
    "保证",
    "确保",
    "不得低于",
    "不低于",
    "不少于",
    "不超过",
    "以内",
    "内响应",
    "内解决",
    "到场",
    "恢复",
    "可用性",
    "准确率",
    "识别率",
    "并发",
    "吞吐",
    "质保",
    "维保",
    "交付",
    "工期",
    "性能",
    "服务",
    "期限",
    "周期",
    "有效期",
    "驻场",
    "人员",
    "团队",
    "培训",
    "备份",
    "保存",
    "保留",
    "接口",
    "数量",
    "费用",
    "价格",
    "保修",
    "覆盖",
    "成功率",
    "合格率",
    "提升",
    "降低",
    "缩短",
    "达到",
    "支持",
)
BARE_NUMBER_ACTION_KEYWORDS = (
    "承诺",
    "保证",
    "确保",
    "达到",
    "支持",
    "不得低于",
    "不低于",
    "不少于",
    "不超过",
    "以内",
    "提升",
    "降低",
    "缩短",
)
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


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
        line: int | None = None,
        match: str = "",
        context: str = "",
    ) -> None:
        issue: dict[str, Any] = {
            "severity": severity,
            "code": code,
            "message": message,
        }
        if file:
            issue["file"] = file
        if line is not None:
            issue["line"] = line
        if match:
            issue["match"] = match
        if context:
            issue["context"] = context
        self.issues.append(issue)

    def gate(self) -> str:
        return "warning" if self.mode == "draft" else "error"

    def counts(self) -> dict[str, int]:
        return {
            "errors": sum(i["severity"] == "error" for i in self.issues),
            "warnings": sum(i["severity"] == "warning" for i in self.issues),
            "info": sum(i["severity"] == "info" for i in self.issues),
        }


def read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def paragraph_text(paragraph: ET.Element) -> str:
    pieces: list[str] = []
    for node in paragraph.iter():
        if node.tag in {
            f"{{{W_NS}}}t",
            f"{{{W_NS}}}delText",
            f"{{{W_NS}}}instrText",
        }:
            pieces.append(node.text or "")
        elif node.tag == f"{{{W_NS}}}tab":
            pieces.append("\t")
        elif node.tag in {f"{{{W_NS}}}br", f"{{{W_NS}}}cr"}:
            pieces.append("\n")
    return "".join(pieces)


def read_docx(path: Path) -> tuple[str, list[str]]:
    wanted = re.compile(
        r"^word/(?:document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml$"
    )
    paragraphs: list[str] = []
    parts_read: list[str] = []
    with zipfile.ZipFile(path) as archive:
        package_names = sorted(archive.namelist())
        names = sorted(name for name in package_names if wanted.match(name))
        if "word/document.xml" not in names:
            raise ValueError("DOCX has no word/document.xml")
        names.sort(key=lambda name: (name != "word/document.xml", name))
        for name in names:
            root = ET.fromstring(archive.read(name))
            parts_read.append(name)
            for paragraph in root.iter(f"{{{W_NS}}}p"):
                text = paragraph_text(paragraph).strip()
                if text:
                    paragraphs.append(text)
            for node in root.iter():
                for attribute, value in node.attrib.items():
                    local_name = attribute.rsplit("}", 1)[-1]
                    if value.strip():
                        paragraphs.append(f"[{name}:{local_name}] {value.strip()}")

        metadata_names = [
            name
            for name in package_names
            if name not in names
            and (name.lower().endswith(".xml") or name.lower().endswith(".rels"))
        ]
        for name in metadata_names:
            root = ET.fromstring(archive.read(name))
            parts_read.append(name)
            for node in root.iter():
                if node.text and node.text.strip():
                    paragraphs.append(f"[{name}] {node.text.strip()}")
                for attribute, value in node.attrib.items():
                    local_name = attribute.rsplit("}", 1)[-1]
                    if value.strip():
                        paragraphs.append(
                            f"[{name}:{local_name}] {value.strip()}"
                        )

        paragraphs.extend(f"[package-entry] {name}" for name in package_names)
    return "\n".join(paragraphs), parts_read


def read_submission(path: Path) -> tuple[str, str, list[str]]:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".markdown"}:
        return read_text_file(path), suffix.lstrip("."), [str(path)]
    if suffix == ".docx":
        text, parts = read_docx(path)
        return text, "docx", parts
    raise ValueError("Supported input types are .txt, .md, .markdown, and .docx")


def read_terms(values: list[str], file_path: Path | None) -> list[str]:
    terms = [value.strip() for value in values if value.strip()]
    if file_path:
        for line in read_text_file(file_path).splitlines():
            value = line.strip()
            if value and not value.startswith("#"):
                terms.append(value)
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        key = term.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(term)
    return unique


def normalize_text(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def normalize_commitment_clause(value: str) -> str:
    normalized = normalize_text(value)
    prefixes = (
        "我方郑重承诺",
        "我方承诺",
        "我方保证",
        "我方确保",
        "我方",
        "本系统",
        "系统",
    )
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            normalized_prefix = normalize_text(prefix)
            if normalized.startswith(normalized_prefix):
                normalized = normalized[len(normalized_prefix) :]
                changed = True
                break
    return normalized


def find_risk_numbers(value: str) -> list[str]:
    markdown_heading = re.match(
        r"^\s*#{1,6}\s+(\d+(?:\.\d+)*)\s+",
        value,
    )
    plain_heading = re.match(
        r"^\s*(\d+(?:\.\d+)*)\s+.{0,60}"
        r"(?:方案|响应|索引|要求|章节|设计|概述|说明)\s*$",
        value,
    )
    heading_number = (
        markdown_heading.group(1)
        if markdown_heading
        else plain_heading.group(1)
        if plain_heading
        else ""
    )
    structural_id_spans = [match.span() for match in STRUCTURAL_ID_RE.finditer(value)]

    def is_structural_number(match: re.Match[str]) -> bool:
        start, end = match.span()
        prefix = value[max(0, start - 16) : start]
        suffix = value[end : end + 6]
        if any(
            start >= id_start and end <= id_end
            for id_start, id_end in structural_id_spans
        ):
            return True
        if prefix.endswith("第") and re.match(r"(?:章|节|条|款|页|表|图|附件)", suffix):
            return True
        if heading_number and match.group(0) == heading_number:
            return True
        return False

    matches = [
        match for match in RISK_NUMBER_RE.finditer(value) if not is_structural_number(match)
    ]
    occupied = [match.span() for match in matches]
    if any(keyword in value for keyword in BARE_NUMBER_ACTION_KEYWORDS):
        for match in BARE_NUMBER_RE.finditer(value):
            start, end = match.span()
            if is_structural_number(match):
                continue
            if any(start < used_end and end > used_start for used_start, used_end in occupied):
                continue
            matches.append(match)
            occupied.append((start, end))
    matches.sort(key=lambda match: match.start())
    return [match.group(0) for match in matches]


def load_source_metadata(
    path: Path | None, report: Report
) -> dict[str, tuple[str, str]]:
    if path is None:
        return {}
    if not path.is_file():
        report.add(
            "error",
            "SOURCE_REGISTER_MISSING",
            "Source register does not exist.",
            file=str(path),
        )
        return {}
    try:
        data = json.loads(read_text_file(path))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        report.add(
            "error",
            "SOURCE_REGISTER_INVALID",
            f"Cannot read source register: {exc}",
            file=str(path),
        )
        return {}
    sources = data.get("sources") if isinstance(data, dict) else None
    if not isinstance(sources, list):
        report.add(
            "error",
            "SOURCE_REGISTER_INVALID",
            "source_register.json must contain a sources array.",
            file=str(path),
        )
        return {}
    metadata: dict[str, tuple[str, str]] = {}
    for index, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            report.add(
                "error",
                "SOURCE_REGISTER_RECORD_INVALID",
                "Source register entry must be an object.",
                file=str(path),
                line=index,
            )
            continue
        source_id = str(source.get("source_id", "")).strip()
        source_type = str(source.get("source_type", "")).strip()
        status = str(source.get("status", "")).strip()
        if not source_id or source_id in metadata:
            report.add(
                "error",
                "SOURCE_REGISTER_ID_INVALID",
                "Source IDs must be non-blank and unique.",
                file=str(path),
                line=index,
                context=source_id,
            )
            continue
        metadata[source_id] = (source_type, status)
    return metadata


def load_approved_commitments(
    path: Path | None,
    report: Report,
    source_metadata: dict[str, tuple[str, str]],
) -> list[str]:
    if path is None:
        return []
    if not path.is_file():
        report.add(
            "error",
            "COMMITMENT_REGISTER_MISSING",
            "Commitment register does not exist.",
            file=str(path),
        )
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            if any(not name for name in fieldnames):
                report.add(
                    "error",
                    "COMMITMENT_REGISTER_BLANK_HEADER",
                    "Commitment register contains a blank column name.",
                    file=str(path),
                )
                return []
            duplicates = sorted(
                {name for name in fieldnames if fieldnames.count(name) > 1}
            )
            if duplicates:
                report.add(
                    "error",
                    "COMMITMENT_REGISTER_DUPLICATE_HEADER",
                    "Duplicate column names: " + ", ".join(duplicates),
                    file=str(path),
                )
                return []
            headers = set(fieldnames)
            has_v3_text = {"original_text", "final_text"} <= headers
            has_v2_text = "commitment_text" in headers
            has_confirmation = "confirmation_status" in headers
            has_legacy_approval = "approval_status" in headers
            if not (has_v3_text or has_v2_text) or not (
                has_confirmation or has_legacy_approval
            ):
                report.add(
                    "error",
                    "COMMITMENT_REGISTER_FIELDS_MISSING",
                    "Commitment register requires original_text, final_text, and "
                    "confirmation_status. Older commitment_text/approval_status schemas "
                    "are recognized only to fail closed during migration.",
                    file=str(path),
                )
                return []
            schema_kind = (
                "v3"
                if has_v3_text and has_confirmation
                else "v2"
                if has_v2_text and has_confirmation
                else "legacy"
            )
            new_schema = schema_kind == "v3"
            if schema_kind == "v2":
                report.add(
                    report.gate(),
                    "COMMITMENT_REGISTER_PRE_FINAL_SCHEMA",
                    "The commitment_text-only schema cannot prove which narrowed wording "
                    "is final. Migrate to original_text/final_text; only final_text can be "
                    "whitelisted.",
                    file=str(path),
                )
            elif schema_kind == "legacy":
                report.add(
                    report.gate(),
                    "COMMITMENT_REGISTER_LEGACY_SCHEMA",
                    "Legacy approval_status cannot prove evidence, approver, approval "
                    "date, conflict closure, or final disposition. Migrate the register "
                    "to the V2 confirmation_status schema before submission.",
                    file=str(path),
                )
            approved_values = (
                {"沿用采购要求", "已审批"}
                if has_confirmation
                else {"approved", "not_required"}
            )
            approved: list[str] = []
            for line_number, row in enumerate(reader, start=2):
                if None in row or any(row.get(name) is None for name in fieldnames):
                    report.add(
                        "error",
                        "COMMITMENT_REGISTER_ROW_WIDTH_INVALID",
                        "Commitment register row width does not match its header.",
                        file=str(path),
                        line=line_number,
                    )
                    continue
                status = (
                    row.get("confirmation_status")
                    or row.get("approval_status")
                    or ""
                ).strip()
                disposition = (row.get("disposition") or "").strip()
                conflict = (row.get("conflict_check") or "").strip()
                original_text = (row.get("original_text") or "").strip()
                final_text = (row.get("final_text") or "").strip()
                legacy_text = (row.get("commitment_text") or "").strip()
                display_text = final_text or original_text or legacy_text
                if has_confirmation and status not in {
                    "无需新增承诺",
                    "沿用采购要求",
                    "已审批",
                    "待审批",
                    "禁止承诺",
                }:
                    report.add(
                        report.gate(),
                        "COMMITMENT_REGISTER_STATUS_INVALID",
                        f"Unsupported V2 confirmation_status: {status or '<blank>'}.",
                        file=str(path),
                        line=line_number,
                        context=display_text,
                    )
                    continue
                if (
                    new_schema
                    and status == "无需新增承诺"
                    and (
                        find_risk_numbers(final_text)
                        or ABSOLUTE_CLAIM_RE.search(final_text)
                    )
                ):
                    report.add(
                        report.gate(),
                        "COMMITMENT_REGISTER_HIGH_RISK_STATUS_INVALID",
                        "A numerical or absolute-scope commitment cannot be "
                        "whitelisted as 无需新增承诺.",
                        file=str(path),
                        line=line_number,
                        context=final_text,
                    )
                    continue
                if status == "沿用采购要求":
                    located_procurement_ref = False
                    for raw_ref in re.split(r"[;；\n]+", row.get("source_ref", "")):
                        if not raw_ref.strip():
                            continue
                        parts = re.split(r"[#@]", raw_ref.strip(), maxsplit=1)
                        source_id = parts[0].strip()
                        locator = parts[1].strip() if len(parts) == 2 else ""
                        source_type, source_status = source_metadata.get(
                            source_id, ("", "")
                        )
                        if (
                            locator
                            and source_type in PROCUREMENT_SOURCE_TYPES
                            and source_status == "active"
                        ):
                            located_procurement_ref = True
                            break
                    if not located_procurement_ref:
                        report.add(
                            report.gate(),
                            "COMMITMENT_PROCUREMENT_SOURCE_UNVERIFIED",
                            "沿用采购要求 requires --source-register and a located "
                            "active procurement-authority source.",
                            file=str(path),
                            line=line_number,
                            context=display_text,
                        )
                        continue
                if not new_schema:
                    # Pre-final and legacy rows remain visible as audit evidence, but
                    # they never authorize submission wording.
                    continue
                if not original_text:
                    report.add(
                        report.gate(),
                        "COMMITMENT_REGISTER_ORIGINAL_TEXT_MISSING",
                        "original_text is required to preserve the proposed wording.",
                        file=str(path),
                        line=line_number,
                        context=final_text,
                    )
                    continue
                if disposition in {"保留", "收窄", "改为条件承诺"} and not final_text:
                    report.add(
                        report.gate(),
                        "COMMITMENT_REGISTER_FINAL_TEXT_MISSING",
                        "A retained commitment requires final_text; only final_text may "
                        "be whitelisted.",
                        file=str(path),
                        line=line_number,
                        context=original_text,
                    )
                    continue
                normalized_original = normalize_text(original_text)
                normalized_final = normalize_text(final_text)
                if disposition == "保留" and normalized_original != normalized_final:
                    report.add(
                        report.gate(),
                        "COMMITMENT_REGISTER_RETAINED_TEXT_CHANGED",
                        "disposition=保留 requires original_text and final_text to match.",
                        file=str(path),
                        line=line_number,
                        context=final_text,
                    )
                    continue
                if disposition in {"收窄", "改为条件承诺"} and (
                    normalized_original == normalized_final
                    or not (row.get("notes") or "").strip()
                ):
                    report.add(
                        report.gate(),
                        "COMMITMENT_REGISTER_CHANGE_NOT_EXPLAINED",
                        "A narrowed or conditional commitment requires changed final_text "
                        "and notes explaining the change.",
                        file=str(path),
                        line=line_number,
                        context=final_text,
                    )
                    continue
                if status not in approved_values or disposition == "删除" or not final_text:
                    continue

                closed = True
                if new_schema:
                    if disposition not in {"保留", "收窄", "改为条件承诺"}:
                        closed = False
                    if conflict != "无冲突":
                        closed = False
                    if status == "已审批" and not all(
                        (row.get(field) or "").strip()
                        for field in ("evidence_refs", "approver", "approval_date")
                    ):
                        closed = False
                    if status == "沿用采购要求" and not (
                        row.get("source_ref") or ""
                    ).strip():
                        closed = False
                    if status == "无需新增承诺" and not (
                        (row.get("source_ref") or "").strip()
                        or (row.get("evidence_refs") or "").strip()
                    ):
                        closed = False
                if not closed:
                    report.add(
                        report.gate(),
                        "COMMITMENT_REGISTER_ENTRY_NOT_CLOSED",
                        "A nominally approved commitment lacks evidence, approval, "
                        "conflict closure, or final disposition.",
                        file=str(path),
                        line=line_number,
                        context=final_text,
                    )
                    continue
                # Never whitelist original_text. It is audit history and may contain
                # the broader wording that final disposition explicitly narrowed.
                approved.append(final_text)
            return approved
    except (OSError, UnicodeError, csv.Error) as exc:
        report.add(
            "error",
            "COMMITMENT_REGISTER_INVALID",
            f"Cannot read commitment register: {exc}",
            file=str(path),
        )
        return []


def registered_claim_matches(
    sentence: str,
    numeric_matches: list[str],
    absolute_matches: list[str],
    approved: list[str],
) -> tuple[list[str], list[str]]:
    normalized_approved = {
        normalize_commitment_clause(commitment)
        for commitment in approved
        if normalize_commitment_clause(commitment)
    }
    normalized_sentence = normalize_commitment_clause(sentence)
    if normalized_sentence and normalized_sentence in normalized_approved:
        return list(numeric_matches) + list(absolute_matches), []

    clauses = [
        part.strip()
        for part in re.split(r"[，,、；;|]+|并且|同时|以及|且", sentence)
        if part.strip()
    ]
    registered: list[str] = []
    unregistered: list[str] = []
    for clause in clauses:
        clause_numbers = find_risk_numbers(clause)
        clause_absolutes = [
            match.group(0) for match in ABSOLUTE_CLAIM_RE.finditer(clause)
        ]
        clause_claims = clause_numbers + clause_absolutes
        normalized_clause = normalize_commitment_clause(clause)
        clause_is_approved = (
            bool(normalized_clause) and normalized_clause in normalized_approved
        )
        if clause_claims:
            if clause_is_approved:
                registered.extend(clause_claims)
            else:
                unregistered.extend(clause_claims)
            continue

        # A non-numeric neighboring clause can silently expand the scope of an
        # otherwise approved number. In submission mode, every non-empty clause in
        # the same statement must therefore be independently approved; matching a
        # fixed list of words would be bypassable with synonyms.
        if not clause_is_approved:
            unregistered.append(clause)

    return registered, unregistered


def scan_literal_terms(
    lines: list[str],
    terms: list[str],
    *,
    code: str,
    message: str,
    input_path: Path,
    report: Report,
) -> int:
    hits = 0
    for line_number, line in enumerate(lines, start=1):
        for term in terms:
            for match in re.finditer(re.escape(term), line, flags=re.IGNORECASE):
                hits += 1
                report.add(
                    report.gate(),
                    code,
                    message,
                    file=str(input_path),
                    line=line_number,
                    match=match.group(0),
                    context=line.strip(),
                )
    return hits


def scan_placeholders(
    lines: list[str],
    input_path: Path,
    report: Report,
    whitelist: list[str],
) -> int:
    hits = 0
    seen: set[tuple[int, str]] = set()
    allowed = {value.casefold() for value in whitelist}
    for line_number, line in enumerate(lines, start=1):
        for pattern in PLACEHOLDER_PATTERNS:
            for match in pattern.finditer(line):
                if match.group(0).casefold() in allowed:
                    continue
                key = (line_number, match.group(0))
                if key in seen:
                    continue
                seen.add(key)
                hits += 1
                report.add(
                    report.gate(),
                    "PLACEHOLDER_FOUND",
                    "Placeholder remains in the submission text.",
                    file=str(input_path),
                    line=line_number,
                    match=match.group(0),
                    context=line.strip(),
                )
    return hits


def scan_risky_commitments(
    lines: list[str],
    approved: list[str],
    input_path: Path,
    report: Report,
) -> tuple[int, int]:
    risky = 0
    registered = 0
    seen: set[tuple[int, str]] = set()
    for line_number, line in enumerate(lines, start=1):
        sentences = [
            part.strip()
            for part in re.split(r"(?<=[。！？!?])\s*", line)
            if part.strip()
        ]
        for sentence in sentences:
            scan_sentence = NON_COMMITMENT_DISCLAIMER_RE.sub("", sentence).strip(
                " ，,；;"
            )
            if not scan_sentence:
                continue
            numeric_matches = find_risk_numbers(scan_sentence)
            absolute_matches = [
                match.group(0) for match in ABSOLUTE_CLAIM_RE.finditer(scan_sentence)
            ]
            numeric_risk = bool(numeric_matches) and any(
                keyword in scan_sentence for keyword in RISK_KEYWORDS
            )
            if not numeric_risk and not absolute_matches:
                continue
            key = (line_number, sentence)
            if key in seen:
                continue
            seen.add(key)
            risky += 1
            registered_matches, unregistered_matches = registered_claim_matches(
                scan_sentence, numeric_matches, absolute_matches, approved
            )
            if not unregistered_matches:
                registered += 1
                report.add(
                    "info",
                    (
                        "RISKY_NUMERIC_REGISTERED"
                        if numeric_matches
                        else "RISKY_ABSOLUTE_REGISTERED"
                    ),
                    "High-risk commitment is covered by an approved register entry.",
                    file=str(input_path),
                    line=line_number,
                    match="; ".join(registered_matches),
                    context=sentence,
                )
            else:
                report.add(
                    report.gate(),
                    (
                        "RISKY_NUMERIC_UNREGISTERED"
                        if numeric_matches
                        else "RISKY_ABSOLUTE_UNREGISTERED"
                    ),
                    "One or more numerical, absolute, or scope-expanding commitments "
                    "are not covered by an approved register entry.",
                    file=str(input_path),
                    line=line_number,
                    match="; ".join(unregistered_matches),
                    context=sentence,
                )
    return risky, registered


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan TXT, Markdown, or DOCX for submission risks."
    )
    parser.add_argument("input", type=Path, help="Submission file to scan.")
    parser.add_argument(
        "--mode",
        choices=("draft", "submission"),
        default="draft",
        help="draft emits warnings; submission gates placeholders and commitments.",
    )
    parser.add_argument(
        "--banned-word",
        action="append",
        default=[],
        help="Literal banned term. Repeat for more than one.",
    )
    parser.add_argument(
        "--banned-words-file",
        type=Path,
        help="UTF-8 text file containing one banned term per line.",
    )
    parser.add_argument(
        "--old-project-name",
        action="append",
        default=[],
        help="Old project/customer name that must not remain. Repeatable.",
    )
    parser.add_argument(
        "--old-project-names-file",
        type=Path,
        help="UTF-8 text file containing one old name per line.",
    )
    parser.add_argument(
        "--placeholder-whitelist-file",
        type=Path,
        help="Optional UTF-8 file containing exact placeholder-like tokens allowed by "
        "the tender (one per line).",
    )
    parser.add_argument(
        "--commitment-register",
        type=Path,
        help="Optional commitment_register.csv used to approve numerical commitments.",
    )
    parser.add_argument(
        "--source-register",
        type=Path,
        help="Optional source_register.json. Required to whitelist 沿用采购要求.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON report path. The report is always printed to stdout.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_path = args.input.resolve()
    report = Report(args.mode)
    banned_terms: list[str] = []
    old_names: list[str] = []
    placeholder_whitelist: list[str] = []
    text = ""
    input_type = input_path.suffix.lower().lstrip(".")
    parts_read: list[str] = []

    try:
        if not input_path.is_file():
            raise FileNotFoundError(f"Input does not exist: {input_path}")
        banned_terms = read_terms(args.banned_word, args.banned_words_file)
        old_names = read_terms(args.old_project_name, args.old_project_names_file)
        placeholder_whitelist = read_terms([], args.placeholder_whitelist_file)
        text, input_type, parts_read = read_submission(input_path)
    except (OSError, UnicodeError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
        report.add(
            "error",
            "INPUT_READ_FAILED",
            str(exc),
            file=str(input_path),
        )

    source_metadata = load_source_metadata(args.source_register, report)
    approved = load_approved_commitments(
        args.commitment_register, report, source_metadata
    )
    lines = text.splitlines()
    banned_hits = scan_literal_terms(
        lines,
        banned_terms,
        code="BANNED_TERM_FOUND",
        message="Banned term remains in submission text.",
        input_path=input_path,
        report=report,
    )
    old_name_hits = scan_literal_terms(
        lines,
        old_names,
        code="OLD_PROJECT_NAME_FOUND",
        message="Old project or customer name remains in submission text.",
        input_path=input_path,
        report=report,
    )
    placeholder_hits = scan_placeholders(
        lines, input_path, report, placeholder_whitelist
    )
    risky_hits, registered_hits = scan_risky_commitments(
        lines, approved, input_path, report
    )

    counts = report.counts()
    counts.update(
        {
            "banned_term_hits": banned_hits,
            "old_project_name_hits": old_name_hits,
            "placeholder_hits": placeholder_hits,
            "risky_commitment_hits": risky_hits,
            "registered_commitment_hits": registered_hits,
            "scanned_lines": len(lines),
            "extracted_characters": len(text),
        }
    )
    payload = {
        "tool": "scan_submission",
        "report_version": REPORT_VERSION,
        "generated_at": utc_now(),
        "mode": args.mode,
        "valid": counts["errors"] == 0,
        "input": str(input_path),
        "input_type": input_type,
        "parts_read": parts_read,
        "terms": {
            "banned_words": banned_terms,
            "old_project_names": old_names,
            "placeholder_whitelist": placeholder_whitelist,
            "approved_commitments_loaded": len(approved),
            "source_records_loaded": len(source_metadata),
        },
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
