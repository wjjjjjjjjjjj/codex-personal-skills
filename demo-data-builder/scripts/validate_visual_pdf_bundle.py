from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="逐页检查图文演示 PDF 的文本层、空白页与内嵌图片")
    parser.add_argument("pdf_dir", type=Path, help="PDF 文件或包含 PDF 的目录")
    parser.add_argument("--min-pages", type=int, default=2)
    parser.add_argument("--min-chars", type=int, default=800)
    parser.add_argument("--min-images", type=int, default=1)
    parser.add_argument("--min-page-chars", type=int, default=20)
    parser.add_argument("--allow-image-only", action="store_true", help="允许有图片但无文本层的页面")
    parser.add_argument("--json", action="store_true", help="仅输出 JSON 结果")
    return parser.parse_args()


def image_signature(image: dict[str, Any]) -> tuple[Any, ...]:
    return (
        round(float(image.get("width", 0)), 2),
        round(float(image.get("height", 0)), 2),
        str(image.get("colorspace", "")),
        str(image.get("srcsize", "")),
    )


def main() -> int:
    args = parse_args()
    try:
        import pdfplumber
    except ImportError:
        result = {
            "valid": False,
            "error": "缺少依赖 pdfplumber；请使用工作区依赖运行时或先安装对应 PDF extra。",
            "files": [],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"[FAIL] {result['error']}")
        return 2

    if args.pdf_dir.is_file() and args.pdf_dir.suffix.lower() == ".pdf":
        pdfs = [args.pdf_dir]
    elif args.pdf_dir.is_dir():
        pdfs = sorted(args.pdf_dir.rglob("*.pdf"))
    else:
        message = f"路径不存在或不是 PDF：{args.pdf_dir}"
        print(json.dumps({"valid": False, "error": message, "files": []}, ensure_ascii=False) if args.json else f"[FAIL] {message}")
        return 2

    if not pdfs:
        message = "未找到 PDF"
        print(json.dumps({"valid": False, "error": message, "files": []}, ensure_ascii=False) if args.json else f"[FAIL] {message}")
        return 2

    results: list[dict[str, Any]] = []
    for path in pdfs:
        file_result: dict[str, Any] = {"file": str(path), "valid": False, "pages": []}
        try:
            with pdfplumber.open(path) as pdf:
                signatures: list[tuple[Any, ...]] = []
                for index, page in enumerate(pdf.pages, start=1):
                    text = (page.extract_text() or "").strip()
                    images = page.images
                    signatures.extend(image_signature(image) for image in images)
                    file_result["pages"].append(
                        {
                            "page": index,
                            "chars": len(text),
                            "images": len(images),
                            "blank": not text and not images,
                            "low_text": len(text) < args.min_page_chars,
                        }
                    )
        except Exception as exc:
            file_result["error"] = f"读取失败：{exc}"
            results.append(file_result)
            continue

        page_count = len(file_result["pages"])
        char_count = sum(page["chars"] for page in file_result["pages"])
        image_count = sum(page["images"] for page in file_result["pages"])
        blank_pages = [page["page"] for page in file_result["pages"] if page["blank"]]
        low_text_pages = [
            page["page"]
            for page in file_result["pages"]
            if page["low_text"] and not (args.allow_image_only and page["images"] > 0)
        ]
        repeated_image_hint = bool(signatures) and len(set(signatures)) == 1 and len(signatures) > 1
        file_result.update(
            {
                "page_count": page_count,
                "char_count": char_count,
                "image_count": image_count,
                "blank_pages": blank_pages,
                "low_text_pages": low_text_pages,
                "repeated_image_signature_hint": repeated_image_hint,
            }
        )
        file_result["valid"] = (
            page_count >= args.min_pages
            and char_count >= args.min_chars
            and image_count >= args.min_images
            and not blank_pages
            and not low_text_pages
        )
        results.append(file_result)

    valid = all(item["valid"] for item in results)
    report = {"valid": valid, "files": results}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for item in results:
            if "error" in item:
                print(f"[FAIL] {Path(item['file']).name}：{item['error']}")
                continue
            print(
                f"[{'PASS' if item['valid'] else 'FAIL'}] {Path(item['file']).name}："
                f"pages={item['page_count']}/{args.min_pages} "
                f"chars={item['char_count']}/{args.min_chars} "
                f"images={item['image_count']}/{args.min_images} "
                f"blank={item['blank_pages']} low_text={item['low_text_pages']}"
            )
            if item["repeated_image_signature_hint"]:
                print("[WARN] 所有图片尺寸/色彩签名相同，检查是否仅重复背景或装饰图。")
        print(f"RESULT={'PASS' if valid else 'FAIL'} {sum(item['valid'] for item in results)}/{len(results)}")
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
