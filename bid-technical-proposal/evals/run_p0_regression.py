from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_bid_bundle.py"
SCANNER = ROOT / "scripts" / "scan_submission.py"
FILES = Path(__file__).resolve().parent / "files"
VALID = FILES / "bundle_submission_valid"


def run_json(command: list[str], expected_code: int) -> dict:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != expected_code:
        raise AssertionError(
            f"expected exit {expected_code}, got {completed.returncode}\n{completed.stdout}\n{completed.stderr}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"non-JSON output: {completed.stdout}") from exc


def validate(bundle: Path, expected_valid: bool, **overrides: str) -> dict:
    command = [sys.executable, str(SCRIPT), "--bundle", str(bundle), "--mode", "submission"]
    option_map = {
        "traceability": "--traceability",
        "source_register": "--source-register",
        "source_requirements": "--source-requirements",
        "commitments": "--commitments",
    }
    for key, value in overrides.items():
        command.extend([option_map[key], value])
    report = run_json(command, 0 if expected_valid else 1)
    if bool(report.get("valid")) is not expected_valid:
        raise AssertionError(f"unexpected valid flag: {report}")
    return report


def scan(input_name: str, expected_valid: bool, register: str | None = None) -> dict:
    command = [
        sys.executable,
        str(SCANNER),
        str(FILES / "scan" / input_name),
        "--mode",
        "submission",
    ]
    if register:
        command.extend(
            [
                "--commitment-register",
                str(VALID / register),
                "--source-register",
                str(VALID / "source_register.json"),
            ]
        )
    report = run_json(command, 0 if expected_valid else 1)
    if bool(report.get("valid")) is not expected_valid:
        raise AssertionError(f"unexpected scan valid flag: {report}")
    return report


def main() -> int:
    checks = 0
    validate(VALID, True)
    checks += 1

    draft_command = [
        sys.executable,
        str(SCRIPT),
        "--bundle",
        str(FILES / "bundle_draft_valid"),
        "--mode",
        "draft",
    ]
    draft = run_json(draft_command, 0)
    assert draft["valid"] is True and draft["summary"]["errors"] == 0
    checks += 1

    for filename in [
        "missing_requirement_traceability.csv",
        "mandatory_unsupported_traceability.csv",
        "mandatory_conditional_traceability.csv",
        "marker_tampered_traceability.csv",
    ]:
        validate(VALID, False, traceability=filename)
        checks += 1

    validate(VALID, False, source_register="source_register_missing_hash.json")
    checks += 1
    validate(VALID, False, source_requirements="source_requirements_invalid_score.csv")
    checks += 1
    validate(
        VALID,
        True,
        traceability="positive_deviation_traceability.csv",
        commitments="positive_deviation_commitment_register.csv",
    )
    checks += 1

    scan("original_broad_commitment.md", False, "narrowed_commitment_register.csv")
    checks += 1
    scan("registered_commitment.md", True, "narrowed_commitment_register.csv")
    checks += 1
    structural = scan("structural_numbers_clean.md", True)
    assert structural["summary"]["risky_commitment_hits"] == 0
    checks += 1

    print(json.dumps({"status": "ok", "checks": checks}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
