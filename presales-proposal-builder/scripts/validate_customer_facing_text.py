#!/usr/bin/env python3
"""Reject internal-source wording in customer-facing TXT, MD, or DOCX files."""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree


PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "internal Amber feature list",
        re.compile(r"(?:参照|参考|根据|依据|对照)?安铂(?:现有)?(?:产品)?功能清单"),
    ),
    (
        "internal Amber knowledge base",
        re.compile(r"(?:参照|参考|根据|依据|对照)?安铂(?:内部)?知识库"),
    ),
    (
        "internal product whitepaper",
        re.compile(r"(?:参照|参考|根据|依据|对照)(?:公司)?(?:产品)?白皮书"),
    ),
    (
        "internal product material",
        re.compile(r"内部产品资料(?:显示|表明|记载|说明)?"),
    ),
    (
        "skill implementation detail",
        re.compile(
            r"(?:本|该)\s*[Ss]kill\b|"
            r"(?:按照|按|根据|依据)\s*(?:本|该)?\s*[Ss]kill\s*(?:要求|规则|流程)?|"
            r"(?:presales-proposal-builder|presales-consultant-persona|"
            r"bid-document-builder|bid-technical-proposal|archive-quotation-builder|"
            r"amber-pptx-style|demo-data-builder|doc-token-saver|"
            r"markitdown-converter)|"
            r"(?:\.codex|\.agents)[\\/]skills[\\/]",
            re.IGNORECASE,
        ),
    ),
    (
        "manifest implementation detail",
        re.compile(r"proposal_manifest(?:\.json)?"),
    ),
    (
        "prompt implementation detail",
        re.compile(r"(?:按照|根据)(?:本|上述)?提示词(?:要求)?"),
    ),
    (
        "user-request drafting process",
        re.compile(
            r"(?:根据|依据|参照)(?:用户|客户)提供的?(?:相关)?需求(?:内容)?"
            r"(?:进行)?(?:编写|整理|形成)"
        ),
    ),
)


def read_docx(path: Path) -> str:
    text_parts: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = [
            name
            for name in archive.namelist()
            if name == "word/document.xml"
            or re.fullmatch(
                r"word/(?:header|footer)\d+\.xml|word/(?:footnotes|endnotes)\.xml",
                name,
            )
        ]
        for name in names:
            root = ElementTree.fromstring(archive.read(name))
            for node in root.iter():
                if node.tag.endswith("}t") and node.text:
                    text_parts.append(node.text)
            text_parts.append("\n")
    return "".join(text_parts)


def read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8-sig")
    if suffix == ".docx":
        return read_docx(path)
    raise ValueError("supported formats are .txt, .md, and .docx")


def context(text: str, start: int, end: int, radius: int = 30) -> str:
    excerpt = text[max(0, start - radius) : min(len(text), end + radius)]
    return re.sub(r"\s+", " ", excerpt).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path", help="Customer-facing .txt, .md, or .docx file, or - for stdin"
    )
    args = parser.parse_args()

    try:
        text = sys.stdin.read() if args.path == "-" else read_text(Path(args.path))
    except (OSError, ValueError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    matches: list[tuple[str, str, int]] = []
    for label, pattern in PATTERNS:
        for match in pattern.finditer(text):
            matches.append((label, context(text, match.start(), match.end()), match.start()))

    if matches:
        for label, excerpt, position in sorted(matches, key=lambda item: item[2]):
            print(f"ERROR: {label} at character {position}: {excerpt}")
        print(f"INVALID: {len(matches)} internal-source reference(s)")
        return 1

    print("VALID: no internal-source wording found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
