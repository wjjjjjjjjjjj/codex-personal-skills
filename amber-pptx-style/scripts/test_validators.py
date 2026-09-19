#!/usr/bin/env python3
"""Deterministic regression checks for Amber content/layout validators."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run(script: str, fixture: str, expected: int) -> None:
    completed = subprocess.run(
        [PYTHON, str(ROOT / "scripts" / script), str(ROOT / "evals" / "fixtures" / fixture), "--require-confirmed"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != expected:
        raise AssertionError(
            f"{script} {fixture}: expected {expected}, got {completed.returncode}\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )


def main() -> int:
    run("validate_content_plan.py", "confirmed-content-plan.json", 0)
    run("validate_content_plan.py", "invalid-content-plan.json", 1)
    run("validate_dynamic_plan.py", "confirmed-layout-plan.json", 0)
    run("validate_dynamic_plan.py", "pending-layout-plan.json", 1)
    run("validate_dynamic_plan.py", "invalid-layout-plan.json", 1)
    print("PASS Amber validator regression suite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
