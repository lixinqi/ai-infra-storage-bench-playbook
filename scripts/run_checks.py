#!/usr/bin/env python3
"""Run repository validation, the self-test, and the example checks.

Usage:
    python3 scripts/run_checks.py [--skip-examples]

Exit codes: 0 all passed, 1 any check failed, 2 dependencies missing.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
EXAMPLES = ROOT / "examples"


def run(label: str, command: list[str]) -> tuple[str, int, str]:
    process = subprocess.run(command, capture_output=True, text=True)
    output = (process.stdout + process.stderr).strip()
    return label, process.returncode, output


def build_commands(skip_examples: bool) -> list[tuple[str, list[str]]]:
    commands: list[tuple[str, list[str]]] = [
        ("validate_repo", [sys.executable, str(CHECKS / "validate_repo.py")]),
        ("selftest", [sys.executable, str(CHECKS / "selftest.py")]),
    ]

    if not skip_examples:
        commands += [
            (
                "coverage",
                [
                    sys.executable,
                    str(CHECKS / "check_coverage.py"),
                    "--manifest",
                    str(EXAMPLES / "coverage.json"),
                    "--metrics",
                    str(ROOT / "recipes" / "model-code-collection" / "metrics.yaml"),
                ],
            ),
            (
                "io-pattern-alignment",
                [
                    sys.executable,
                    str(CHECKS / "check_io_pattern.py"),
                    "--real",
                    str(EXAMPLES / "io-pattern-real.json"),
                    "--bypassed",
                    str(EXAMPLES / "io-pattern-bypassed.json"),
                    "--metrics",
                    str(ROOT / "recipes" / "kvcache" / "metrics.yaml"),
                ],
            ),
            (
                "scaling-consistency",
                [
                    sys.executable,
                    str(CHECKS / "check_scaling_consistency.py"),
                    "--input",
                    str(EXAMPLES / "scaling-levels.json"),
                    "--metrics",
                    str(ROOT / "recipes" / "kvcache" / "metrics.yaml"),
                ],
            ),
        ]

    return commands


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-examples", action="store_true", help="only validate the repository")
    args = parser.parse_args()

    commands = build_commands(args.skip_examples)
    failures = 0
    skips = 0
    for label, command in commands:
        label, code, output = run(label, command)
        state = {0: "pass", 1: "fail", 2: "skip"}.get(code, f"error({code})")
        if code == 1:
            failures += 1
        elif code == 2:
            skips += 1
        print(f"[{state}] {label}")
        if state != "pass":
            for line in output.splitlines():
                print(f"    {line}")

    print(f"\n{len(commands)} checks: {failures} failed, {skips} skipped")
    return 1 if failures else (2 if skips else 0)


if __name__ == "__main__":
    sys.exit(main())
