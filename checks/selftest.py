#!/usr/bin/env python3
"""Run the checks against known-good and known-bad inputs.

The pass examples live in examples/. The rejected fixtures live in
examples/invalid/ and exist to prove the checks fail when they should: a check
that only ever passes is not evidence.

Output: one JSON object on stdout. Exit 0 when every case behaves as expected,
1 when a case behaves differently, 2 when dependencies are missing.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:  # pragma: no cover - depends on environment
    print(json.dumps({"check": "selftest", "status": "skip", "detail": "jsonschema is not installed"}))
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
EXAMPLES = ROOT / "examples"
INVALID = EXAMPLES / "invalid"
SCHEMAS = ROOT / "schemas"

KVCACHE_METRICS = ROOT / "recipes" / "kvcache" / "metrics.yaml"
COLLECTION_METRICS = ROOT / "recipes" / "model-code-collection" / "metrics.yaml"


def run_check(script: str, *args: str) -> int:
    process = subprocess.run(
        [sys.executable, str(CHECKS / script), *args],
        capture_output=True,
        text=True,
    )
    return process.returncode


def schema_rejects(schema_name: str, instance_path: Path) -> bool:
    with (SCHEMAS / schema_name).open(encoding="utf-8") as handle:
        schema = json.load(handle)
    with instance_path.open(encoding="utf-8") as handle:
        instance = json.load(handle)
    try:
        jsonschema.validate(instance, schema)
    except jsonschema.ValidationError:
        return True
    return False


def schema_rejects_yaml(schema_name: str, instance_path: Path) -> bool:
    import yaml

    with (SCHEMAS / schema_name).open(encoding="utf-8") as handle:
        schema = json.load(handle)
    with instance_path.open(encoding="utf-8") as handle:
        instance = yaml.safe_load(handle)
    try:
        jsonschema.validate(instance, schema)
    except jsonschema.ValidationError:
        return True
    return False


def positive_cases() -> list[tuple[str, int, int]]:
    return [
        ("accept io-pattern", run_check(
            "check_io_pattern.py",
            "--real", str(EXAMPLES / "io-pattern-real.json"),
            "--bypassed", str(EXAMPLES / "io-pattern-bypassed.json"),
            "--metrics", str(KVCACHE_METRICS),
        ), 0),
        ("accept coverage", run_check(
            "check_coverage.py",
            "--manifest", str(EXAMPLES / "coverage.json"),
            "--metrics", str(COLLECTION_METRICS),
        ), 0),
        ("accept scaling", run_check(
            "check_scaling_consistency.py",
            "--input", str(EXAMPLES / "scaling-levels.json"),
            "--metrics", str(KVCACHE_METRICS),
        ), 0),
    ]


def negative_cases() -> list[tuple[str, int, int]]:
    return [
        ("reject record without sys layer", run_check(
            "check_io_pattern.py",
            "--real", str(INVALID / "io-pattern-bad-sources.json"),
            "--bypassed", str(EXAMPLES / "io-pattern-bypassed.json"),
            "--metrics", str(KVCACHE_METRICS),
        ), 2),
        ("reject unknown tolerance key", run_check(
            "check_io_pattern.py",
            "--real", str(EXAMPLES / "io-pattern-real.json"),
            "--bypassed", str(EXAMPLES / "io-pattern-bypassed.json"),
            "--metrics", str(INVALID / "metrics-unknown-tolerance.yaml"),
        ), 2),
        ("reject coverage cell without arch_family", run_check(
            "check_coverage.py",
            "--manifest", str(INVALID / "coverage-missing-axis.json"),
            "--metrics", str(COLLECTION_METRICS),
        ), 2),
        ("reject scaling with wrong value count", run_check(
            "check_scaling_consistency.py",
            "--input", str(INVALID / "scaling-bad-lengths.json"),
            "--metrics", str(KVCACHE_METRICS),
        ), 2),
    ]


def schema_cases() -> list[tuple[str, int, int]]:
    checks = [
        ("reject recipe without metrics_ref", schema_rejects_yaml(
            "recipe.schema.json", INVALID / "recipe-missing-field.yaml")),
        ("reject run spec with unknown level", schema_rejects(
            "run-spec.schema.json", INVALID / "run-spec-bad-level.json")),
        ("reject SLI without storage identity", schema_rejects(
            "sli.schema.json", INVALID / "sli-missing-storage.json")),
    ]
    return [(name, 1 if rejected else 0, 1) for name, rejected in checks]


def cases() -> list[tuple[str, int, int]]:
    return positive_cases() + negative_cases() + schema_cases()


def main() -> int:
    results = []
    failures = 0
    for name, actual, expected in cases():
        ok = actual == expected
        failures += 0 if ok else 1
        results.append({"name": name, "expected": expected, "actual": actual, "ok": ok})

    print(json.dumps({"check": "selftest", "status": "pass" if not failures else "fail", "cases": results}))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
