from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


RULE_HEADERS = ["开放审核规则名称（暂定）", "规则编号（拟定）", "开放标志"]
DOCUMENT_HEADERS = ["文档编号", "文件名"]
GROUND_TRUTH_HEADERS = [
    "文档编号",
    "规则编号",
    "预期命中",
    "证据类型",
    "证据定位",
    "证据摘录",
    "期望审核结论",
    "判定说明",
]
ALLOWED_STATUS = {"开放", "限制"}
ALLOWED_HIT = {"是", "否"}
ALLOWED_EVIDENCE = {"段落", "图片", "表格", "无命中"}
ALLOWED_CONCLUSION = {"开放", "限制", "人工复核"}


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        return headers, [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def require_headers(label: str, actual: list[str], required: list[str], errors: list[str]) -> None:
    missing = [header for header in required if header not in actual]
    if missing:
        errors.append(f"{label}缺少字段：{', '.join(missing)}")


def duplicate_values(rows: list[dict[str, str]], key: str) -> set[str]:
    values = [row.get(key, "") for row in rows if row.get(key, "")]
    return {value for value in values if values.count(value) > 1}


def validate_rules(path: Path, errors: list[str]) -> set[str]:
    headers, rows = read_csv(path)
    require_headers("规则表", headers, RULE_HEADERS, errors)
    if any(row.get("规则编号（拟定）", "") == "" for row in rows):
        errors.append("规则表存在空规则编号")
    duplicates = duplicate_values(rows, "规则编号（拟定）")
    if duplicates:
        errors.append(f"规则编号重复：{', '.join(sorted(duplicates))}")
    invalid_status = sorted({row.get("开放标志", "") for row in rows} - ALLOWED_STATUS)
    if invalid_status:
        errors.append(f"开放标志不在开放/限制枚举内：{', '.join(invalid_status)}")
    return {row.get("规则编号（拟定）", "") for row in rows if row.get("规则编号（拟定）", "")}


def validate_documents(path: Path, errors: list[str], root: Path | None = None) -> set[str]:
    headers, rows = read_csv(path)
    require_headers("文档清单", headers, DOCUMENT_HEADERS, errors)
    document_ids = {row.get("文档编号", "") for row in rows if row.get("文档编号", "")}
    duplicates = duplicate_values(rows, "文档编号")
    if duplicates:
        errors.append(f"文档编号重复：{', '.join(sorted(duplicates))}")
    for row in rows:
        if not row.get("文件名", ""):
            errors.append(f"文档清单中{row.get('文档编号', '未命名文档')}缺少文件名")
        elif root is not None and not Path(row["文件名"]).is_absolute() and not (root / row["文件名"]).is_file():
            errors.append(f"文档文件不存在：{row['文件名']}")
    return document_ids


def validate_ground_truth(
    path: Path,
    rule_ids: set[str],
    document_ids: set[str],
    errors: list[str],
    image_ids: set[str] | None = None,
) -> None:
    headers, rows = read_csv(path)
    require_headers("审核标准答案", headers, GROUND_TRUTH_HEADERS, errors)
    for index, row in enumerate(rows, start=2):
        document_id = row.get("文档编号", "")
        rule_id = row.get("规则编号", "")
        hit = row.get("预期命中", "")
        evidence_type = row.get("证据类型", "")
        location = row.get("证据定位", "")
        conclusion = row.get("期望审核结论", "")
        if document_id not in document_ids:
            errors.append(f"审核标准答案第{index}行引用了不存在的文档编号：{document_id}")
        if rule_id not in rule_ids:
            errors.append(f"审核标准答案第{index}行引用了不存在的规则编号：{rule_id}")
        if hit not in ALLOWED_HIT:
            errors.append(f"审核标准答案第{index}行预期命中必须为是/否：{hit}")
        if evidence_type not in ALLOWED_EVIDENCE:
            errors.append(f"审核标准答案第{index}行证据类型无效：{evidence_type}")
        if conclusion not in ALLOWED_CONCLUSION:
            errors.append(f"审核标准答案第{index}行期望审核结论无效：{conclusion}")
        if hit == "否" and evidence_type != "无命中":
            errors.append(f"审核标准答案第{index}行未命中时证据类型应为无命中")
        if hit == "是" and evidence_type == "无命中":
            errors.append(f"审核标准答案第{index}行命中时必须提供段落/图片/表格证据")
        if evidence_type == "无命中" and location not in {"", "-", "无"}:
            errors.append(f"审核标准答案第{index}行无命中证据定位应为空、-或无")
        if evidence_type == "图片" and image_ids is not None and location not in image_ids:
            errors.append(f"审核标准答案第{index}行引用了不存在的图片编号：{location}")


def validate_image_manifest(path: Path, errors: list[str], root: Path | None = None) -> set[str]:
    headers, rows = read_csv(path)
    required = ["图片编号", "文件名"]
    require_headers("图片清单", headers, required, errors)
    image_ids = {row.get("图片编号", "") for row in rows if row.get("图片编号", "")}
    duplicates = duplicate_values(rows, "图片编号")
    if duplicates:
        errors.append(f"图片编号重复：{', '.join(sorted(duplicates))}")
    if root is not None:
        for row in rows:
            file_name = row.get("文件名", "")
            if file_name and not Path(file_name).is_absolute() and not (root / file_name).is_file():
                errors.append(f"图片文件不存在：{file_name}")
    return image_ids


def main() -> int:
    parser = argparse.ArgumentParser(description="校验智能开放审核演示数据包的三张 CSV 契约")
    parser.add_argument("--rules", required=True, type=Path)
    parser.add_argument("--documents", required=True, type=Path)
    parser.add_argument("--ground-truth", required=True, type=Path)
    parser.add_argument("--root", type=Path, help="数据包根目录；提供后检查文档/图片文件是否存在")
    parser.add_argument("--image-manifest", type=Path, help="可选图片清单 CSV，至少包含图片编号、文件名")
    args = parser.parse_args()
    errors: list[str] = []
    rule_ids = validate_rules(args.rules, errors)
    document_ids = validate_documents(args.documents, errors, args.root)
    image_ids = validate_image_manifest(args.image_manifest, errors, args.root) if args.image_manifest else None
    validate_ground_truth(args.ground_truth, rule_ids, document_ids, errors, image_ids)
    if errors:
        print("开放审核数据包校验失败")
        for error in errors:
            print(f"- {error}")
        return 1
    print("开放审核数据包校验通过：规则表、文档清单、审核标准答案引用和枚举均有效")
    return 0


if __name__ == "__main__":
    sys.exit(main())
