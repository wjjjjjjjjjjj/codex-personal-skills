from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="对多模态智能编研提示词执行静态规则与冲突 lint")
    parser.add_argument("prompt", type=Path, help="智能编研提示词 Markdown 文件")
    return parser.parse_args()


def forbidden_rule(text: str, term: str, radius: int = 24) -> bool:
    escaped = re.escape(term)
    patterns = [
        rf"(?:禁止|不得|严禁|不要).{{0,{radius}}}{escaped}",
        rf"{escaped}.{{0,{radius}}}(?:禁止|不得|严禁|不要|排除)",
    ]
    return any(re.search(pattern, text, re.S) for pattern in patterns)


def conflict_matches(text: str) -> list[str]:
    dangerous = r"(?:伪造(?:图片)?路径|加入二维码|插入二维码|生成二维码|敏感地图|真实工艺参数)"
    directive = r"(?:必须|应当|需要|务必|请)"
    patterns = [rf"{directive}.{{0,24}}{dangerous}", rf"{dangerous}.{{0,24}}{directive}"]
    matches: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.S):
            excerpt = re.sub(r"\s+", " ", match.group(0)).strip()
            if re.search(r"禁止|不得|严禁|不要|排除", excerpt):
                continue
            if excerpt not in matches:
                matches.append(excerpt)
    return matches


def main() -> int:
    args = parse_args()
    try:
        text = args.prompt.read_text(encoding="utf-8-sig")
    except Exception as exc:
        print(f"[FAIL] 文件读取：{exc}")
        return 1

    compact = re.sub(r"\s+", "", text)
    checks = [
        ("图片发现", "PDF" in text and "图片" in text and ("扫描" in text or "发现" in text)),
        ("稳定图片ID", "稳定" in text and "图片ID" in compact),
        ("OCR与图像理解", "OCR" in text and ("图像内容识别" in text or "图像理解" in text)),
        ("可见事实与推断分离", "直接可见" in text and ("推断" in text or "审慎解释" in text)),
        ("图片筛选", "3—5" in text or "3-5" in text or "3至5" in text),
        ("正文回填", "图片URI" in compact and ("插入" in text or "回填" in text)),
        ("无URI降级", "插图建议" in text and forbidden_rule(text, "伪造路径")),
        ("图文证据互证", "图片不得成为唯一证据" in compact or "图片不能成为唯一证据" in compact),
        ("插图来源清单", "插图来源与使用清单" in text),
        (
            "敏感内容明确禁止",
            all(forbidden_rule(text, term) for term in ["二维码", "敏感地图", "真实工艺参数"]),
        ),
    ]

    conflicts = conflict_matches(text)
    checks.append(("无反向安全指令", not conflicts))
    for name, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    for conflict in conflicts:
        print(f"[CONFLICT] {conflict}")
    passed = all(ok for _, ok in checks)
    print(f"RESULT={'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
