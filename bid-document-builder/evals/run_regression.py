#!/usr/bin/env python3
"""Minimal safety regression suite for bid-document-builder."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCH = ROOT / "scripts" / "make_arch.py"
PROTO = ROOT / "scripts" / "make_proto.py"
LIB = ROOT / "assets" / "lib.js"
FORBIDDEN = (
    "北京市知识产权局",
    "数字档案室建设采购项目",
    "11000026210200175694-XM001",
    "2026年6月23日",
    "等保三级",
    "商用密码应用",
    "Kubernetes",
    "区块链上链核验",
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(command: list[str], expect_ok: bool = True) -> subprocess.CompletedProcess[str]:
    child_env = os.environ.copy()
    child_env["PYTHONUTF8"] = "1"
    child_env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
        env=child_env,
    )
    if expect_ok and result.returncode != 0:
        raise AssertionError(f"command failed: {command}\n{result.stdout}\n{result.stderr}")
    if not expect_ok and result.returncode == 0:
        raise AssertionError(f"command unexpectedly succeeded: {command}")
    return result


def main() -> int:
    for path in (ARCH, PROTO):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")

    production_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (ARCH, PROTO, LIB)
    )
    for token in FORBIDDEN:
        check(token not in production_text, f"forbidden project/capability default remains: {token}")
    check("原型示意｜非真实产品截图" in PROTO.read_text(encoding="utf-8"), "prototype watermark missing")
    check("Missing required document config" in LIB.read_text(encoding="utf-8"), "lib.js does not fail closed")
    check('img.save("assets/' not in production_text, "generator still writes into skill assets")

    node = shutil.which("node")
    if node:
        run([node, "--check", str(LIB)])

    with tempfile.TemporaryDirectory(prefix="bid-builder-regression-") as temp_name:
        temp = Path(temp_name)
        arch_config = temp / "arch.json"
        proto_config = temp / "proto.json"
        invalid_config = temp / "invalid.json"
        arch_config.write_text(
            json.dumps(
                {
                    "title": "已确认架构标题",
                    "layers": [{"label": "已确认层级", "rows": [["已确认组件"]]}],
                    "pillars": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        proto_config.write_text(
            json.dumps(
                {"title": "已确认功能", "layout": "table", "columns": ["字段一", "字段二"], "rows": []},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        invalid_config.write_text(json.dumps({"layout": "table", "columns": ["字段"]}, ensure_ascii=False), encoding="utf-8")

        arch_output = temp / "arch.png"
        proto_output = temp / "proto.png"
        run([sys.executable, str(ARCH), "--config", str(arch_config), "--output", str(arch_output)])
        proto_result = run([sys.executable, str(PROTO), "--config", str(proto_config), "--output", str(proto_output)])
        check(arch_output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), "architecture output is not PNG")
        check(proto_output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), "prototype output is not PNG")
        check("原型示意｜非真实产品截图" in proto_result.stdout, "watermark not confirmed by renderer")
        run([sys.executable, str(PROTO), "--config", str(invalid_config), "--output", str(temp / "invalid.png")], expect_ok=False)

    print(json.dumps({"status": "ok", "checks": 8}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
