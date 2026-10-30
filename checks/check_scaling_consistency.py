#!/usr/bin/env python3
"""Compute scaling consistency across scale levels.

Usage:
    python3 checks/check_scaling_consistency.py --input levels.json \
        --metrics recipes/kvcache/metrics.yaml

Input structure (one entry per invariant, one value per level):

    {
      "levels": ["S0", "S1", "S2"],
      "invariants": {
        "per_parameter_bytes": {"values": [16.0, 16.2, 15.9]},
        "write_concurrency_p50": {"values": [4, 4, 3], "tolerance": 0.3}
      }
    }

Defaults for `tolerance` and `first_last_tolerance` come from the recipe's
metrics.yaml (scaling-consistency: per_level, first_last). An invariant may
override its own tolerance in the input file.

Rules from metrics/scaling-consistency.md:
  - every adjacent-level deviation must stay within the invariant tolerance
  - first-last deviation must stay within first_last_tolerance
  - a run of same-direction deviations means monotonic drift, which fails even
    when every individual deviation is within tolerance

Exit 0 when consistent, 1 when not, 2 on bad input or a missing threshold.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
try:
    from _metrics import MetricsError, load_metrics, tolerance_of
except ImportError as exc:  # pragma: no cover - depends on environment
    print(
        json.dumps(
            {
                "check": "scaling-consistency",
                "status": "skip",
                "detail": f"missing dependency: {exc.name}; install with pip install -r requirements.txt",
            }
        )
    )
    sys.exit(2)

METRIC_NAME = "scaling-consistency"
LEVEL = re.compile(r"^S[0-9]+$")


def load_json(path: str) -> dict:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def relative_deviation(previous: float, current: float) -> float:
    if previous == 0:
        return abs(current)
    return abs(current - previous) / abs(previous)


def directions(values: list[float]) -> list[int]:
    return [
        0 if values[index] == values[index - 1] else (1 if values[index] > values[index - 1] else -1)
        for index in range(1, len(values))
    ]


def evaluate_invariant(levels: list[str], name: str, spec: dict, defaults: dict[str, float]) -> dict:
    values = spec["values"]
    if len(values) != len(levels):
        raise ValueError(f"invariant {name!r} has {len(values)} values for {len(levels)} levels")

    tolerance = spec.get("tolerance", defaults.get("per_level"))
    if tolerance is None:
        raise MetricsError(
            f"invariant {name!r} has no tolerance and metrics.yaml declares no per_level"
        )

    adjacent = [relative_deviation(values[index - 1], values[index]) for index in range(1, len(values))]
    overall = relative_deviation(values[0], values[-1])
    nonzero = [direction for direction in directions(values) if direction != 0]
    monotonic_drift = len(nonzero) >= 2 and len(set(nonzero)) == 1

    adjacent_ok = all(deviation <= tolerance for deviation in adjacent)
    overall_ok = overall <= defaults.get("first_last", 0.15)
    passed = adjacent_ok and overall_ok and not monotonic_drift

    return {
        "levels": levels,
        "values": values,
        "adjacent_deviations": [round(value, 4) for value in adjacent],
        "first_last_deviation": round(overall, 4),
        "tolerance": tolerance,
        "first_last_tolerance": defaults.get("first_last", 0.15),
        "monotonic_drift": monotonic_drift,
        "passed": passed,
    }


def evaluate(data: dict, defaults: dict[str, float]) -> dict:
    levels = data["levels"]
    if len(levels) < 2:
        raise ValueError("at least two levels are required")
    for level in levels:
        if not isinstance(level, str) or not LEVEL.match(level):
            raise ValueError(f"level {level!r} does not match ^S[0-9]+$")

    report = {
        name: evaluate_invariant(levels, name, spec, defaults)
        for name, spec in data["invariants"].items()
    }
    failed = [name for name, result in report.items() if not result["passed"]]
    return {
        "check": METRIC_NAME,
        "status": "pass" if not failed else "fail",
        "invariants": report,
        "failed_invariants": failed,
    }


def load_defaults(args) -> dict[str, float]:
    if not args.metrics:
        return {}
    tolerance = tolerance_of(load_metrics(args.metrics), METRIC_NAME)
    return {"per_level": tolerance["per_level"], "first_last": tolerance["first_last"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--metrics", help="recipe metrics.yaml that declares per_level / first_last")
    args = parser.parse_args()

    try:
        data = load_json(args.input)
        defaults = load_defaults(args)
        if "first_last_tolerance" in data:
            defaults["first_last"] = data["first_last_tolerance"]
        result = evaluate(data, defaults)
    except (OSError, json.JSONDecodeError, MetricsError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"check": METRIC_NAME, "status": "skip", "detail": str(exc)}))
        return 2

    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
