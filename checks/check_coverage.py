#!/usr/bin/env python3
"""Compute coverage from a coverage manifest.

Usage:
    python3 checks/check_coverage.py --manifest coverage.json \
        --metrics recipes/model-code-collection/metrics.yaml

The coverage threshold comes from the recipe's metrics.yaml (coverage_ratio_min),
optionally overridden with --min-coverage. Expired exemptions count as gaps,
as described in metrics/coverage.md.

Output: one JSON object on stdout. Exit 0 at or above the threshold, 1 below,
2 when the manifest or the metrics file cannot supply what is needed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

try:
    import jsonschema
    from _metrics import MetricsError, load_metrics, tolerance_of
except ImportError as exc:  # pragma: no cover - depends on environment
    print(
        json.dumps(
            {
                "check": "coverage",
                "status": "skip",
                "detail": f"missing dependency: {exc.name}; install with pip install -r requirements.txt",
            }
        )
    )
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "coverage.schema.json"
METRIC_NAME = "coverage"
COUNTED = ("covered", "failed", "stale", "gap")
STATUSES = ("covered", "failed", "stale", "gap", "exempt")


def load_json(path: str) -> dict:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def validate(manifest: dict) -> None:
    with SCHEMA.open(encoding="utf-8") as handle:
        schema = json.load(handle)
    try:
        jsonschema.validate(manifest, schema)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise ValueError(f"manifest does not match schemas/coverage.schema.json at {location}: {exc.message}")


def effective_status(cell: dict, today: dt.date) -> str:
    status = cell["status"]
    if status != "exempt":
        return status
    review_due = cell.get("review_due")
    if not review_due:
        return "gap"
    try:
        due = dt.date.fromisoformat(review_due)
    except ValueError:
        return "gap"
    return "exempt" if due >= today else "gap"


def summarize(manifest: dict, today: dt.date) -> dict:
    counts = Counter({status: 0 for status in STATUSES})
    gaps: list[dict] = []
    for cell in manifest["cells"]:
        status = effective_status(cell, today)
        if status not in STATUSES:
            raise ValueError(f"unknown cell status {status!r}")
        counts[status] += 1
        if status == "gap":
            gaps.append({"axes": cell["axes"], "cases": cell.get("cases", [])})

    denominator = sum(counts[status] for status in COUNTED)
    covered = counts["covered"]
    ratio = covered / denominator if denominator else 0.0
    gap_ratio = counts["gap"] / denominator if denominator else 0.0
    return {
        "check": METRIC_NAME,
        "counts": dict(counts),
        "denominator": denominator,
        "coverage_ratio": round(ratio, 4),
        "gap_ratio": round(gap_ratio, 4),
        "gaps": gaps,
    }


def resolve_threshold(args) -> float:
    if args.min_coverage is not None:
        return args.min_coverage
    if args.metrics:
        return tolerance_of(load_metrics(args.metrics), METRIC_NAME)["coverage_ratio_min"]
    raise MetricsError(
        "no threshold: pass --metrics <recipe>/metrics.yaml or --min-coverage <ratio>"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--metrics", help="recipe metrics.yaml that declares coverage_ratio_min")
    parser.add_argument("--min-coverage", type=float)
    parser.add_argument("--today", help="override today's date, format YYYY-MM-DD")
    args = parser.parse_args()

    try:
        manifest = load_json(args.manifest)
        validate(manifest)
        threshold = resolve_threshold(args)
        today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
        result = summarize(manifest, today)
    except (OSError, json.JSONDecodeError, MetricsError, ValueError) as exc:
        print(json.dumps({"check": METRIC_NAME, "status": "skip", "detail": str(exc)}))
        return 2

    result["min_coverage"] = threshold
    result["status"] = "pass" if result["coverage_ratio"] >= threshold else "fail"
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
