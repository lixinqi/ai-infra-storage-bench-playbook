#!/usr/bin/env python3
"""Compare two IO pattern records and report per-item alignment.

Usage:
    python3 checks/check_io_pattern.py --real real.json --bypassed bypassed.json \
        --metrics recipes/kvcache/metrics.yaml

The real record is the baseline; the bypassed record is what the bypass
implementation produced. Tolerances come from the recipe's metrics.yaml (the
single source of truth), optionally overridden with --tolerance.

Output: one JSON object on stdout. Exit code 0 when every compared item passes,
1 when any item fails, 2 when inputs are missing, invalid, or a declared
tolerance key is not supported.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import jsonschema
    from _metrics import MetricsError, load_metrics, parse_threshold, tolerance_of
except ImportError as exc:  # pragma: no cover - depends on environment
    print(
        json.dumps(
            {
                "check": "io-pattern-alignment",
                "status": "skip",
                "detail": f"missing dependency: {exc.name}; install with pip install -r requirements.txt",
            }
        )
    )
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
RECORD_SCHEMA = ROOT / "schemas" / "io-pattern.schema.json"
METRIC_NAME = "io-pattern-alignment"


def load_json(path: str) -> dict:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_record(record: dict, schema: dict, label: str) -> None:
    try:
        jsonschema.validate(record, schema)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise ValueError(
            f"{label} does not match schemas/io-pattern.schema.json at {location}: {exc.message}"
        )


def l1_distance(left: list[int], right: list[int]) -> float:
    if len(left) != len(right):
        raise ValueError("histograms have different bucket counts; align them before comparing")
    left_total, right_total = sum(left), sum(right)
    if left_total == 0 or right_total == 0:
        raise ValueError("histogram is empty; cannot compute L1 distance")
    return sum(abs(a / left_total - b / right_total) for a, b in zip(left, right))


def relative_deviation(observed: float, baseline: float) -> float:
    if baseline == 0:
        return abs(observed)
    return abs(observed - baseline) / abs(baseline)


def ratio(record: dict, unit: str) -> float:
    totals = record["totals"]
    denominator = totals[f"write_{unit}"]
    if denominator == 0:
        raise ValueError(f"write_{unit} is zero; read/write ratio is undefined")
    return totals[f"read_{unit}"] / denominator


def kv_bytes_per_token(record: dict) -> float:
    tokens = record.get("tokens_generated")
    if not tokens:
        raise ValueError("tokens_generated is required to judge per_token_kv_bytes")
    return record["totals"]["write_bytes"] / tokens


def peak_bytes(record: dict) -> float:
    timing = record.get("timing")
    if not timing:
        raise ValueError("timing.peak_bytes_per_second is required to judge timing_peak")
    return timing["peak_bytes_per_second"]


def compare_histograms(real: dict, bypassed: dict) -> float:
    left = real["request_size_histogram"]
    right = bypassed["request_size_histogram"]
    if left["bucket_edges"] != right["bucket_edges"]:
        raise ValueError("the two records use different bucket edges; they are not comparable")
    return l1_distance(left["counts"], right["counts"])


def compare_concurrency(real: dict, bypassed: dict, percentile: str) -> float:
    real_value = real.get("concurrency", {}).get(percentile)
    bypassed_value = bypassed.get("concurrency", {}).get(percentile)
    if real_value is None or bypassed_value is None:
        raise ValueError(f"concurrency.{percentile} is missing in one of the records")
    return relative_deviation(bypassed_value, real_value)


def compare_scalar(real: dict, bypassed: dict, key: str) -> float:
    if key not in real or key not in bypassed:
        raise ValueError(f"{key} is missing in one of the records")
    return abs(bypassed[key] - real[key])


def compare_hotness(real: dict, bypassed: dict) -> float:
    real_value = real.get("hotness", {}).get("top_k_share")
    bypassed_value = bypassed.get("hotness", {}).get("top_k_share")
    if real_value is None or bypassed_value is None:
        raise ValueError("hotness.top_k_share is missing in one of the records")
    return abs(bypassed_value - real_value)


ITEMS = {
    "request_size_distribution": compare_histograms,
    "read_write_ratio_bytes": lambda real, bypassed: relative_deviation(
        ratio(bypassed, "bytes"), ratio(real, "bytes")
    ),
    "read_write_ratio_ops": lambda real, bypassed: relative_deviation(
        ratio(bypassed, "ops"), ratio(real, "ops")
    ),
    "concurrency_p50": lambda real, bypassed: compare_concurrency(real, bypassed, "p50"),
    "concurrency_p95": lambda real, bypassed: compare_concurrency(real, bypassed, "p95"),
    "concurrency_max": lambda real, bypassed: compare_concurrency(real, bypassed, "max"),
    "sequentiality": lambda real, bypassed: compare_scalar(real, bypassed, "sequentiality_ratio"),
    "hotness": compare_hotness,
    "per_token_kv_bytes": lambda real, bypassed: relative_deviation(
        kv_bytes_per_token(bypassed), kv_bytes_per_token(real)
    ),
    "timing_peak": lambda real, bypassed: relative_deviation(peak_bytes(bypassed), peak_bytes(real)),
}


def evaluate(real: dict, bypassed: dict, tolerances: dict[str, float]) -> dict:
    unknown = sorted(set(tolerances) - set(ITEMS))
    if unknown:
        raise ValueError(f"unsupported tolerance keys: {unknown}; supported: {sorted(ITEMS)}")

    results: dict[str, dict] = {}
    failed: list[str] = []
    for item, threshold in sorted(tolerances.items()):
        observed = round(ITEMS[item](real, bypassed), 4)
        passed = observed <= threshold
        results[item] = {"value": observed, "tolerance": threshold, "passed": passed}
        if not passed:
            failed.append(item)

    return {
        "check": METRIC_NAME,
        "status": "pass" if not failed else "fail",
        "items": results,
        "failed_items": failed,
    }


def load_tolerances(args) -> dict[str, float]:
    tolerances: dict[str, float] = {}
    if args.metrics:
        tolerances.update(tolerance_of(load_metrics(args.metrics), METRIC_NAME))
    if args.tolerance:
        with Path(args.tolerance).open(encoding="utf-8") as handle:
            override = json.load(handle)
        tolerances.update({key: parse_threshold(value) for key, value in override.items()})
    if not tolerances:
        raise MetricsError(
            "no tolerances: pass --metrics <recipe>/metrics.yaml or --tolerance <json>"
        )
    return tolerances


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", required=True, help="IO pattern record of the real run")
    parser.add_argument("--bypassed", required=True, help="IO pattern record of the bypassed run")
    parser.add_argument("--metrics", help="recipe metrics.yaml that declares the tolerances")
    parser.add_argument("--tolerance", help="JSON file overriding individual tolerances")
    args = parser.parse_args()

    try:
        real = load_json(args.real)
        bypassed = load_json(args.bypassed)
        with RECORD_SCHEMA.open(encoding="utf-8") as handle:
            schema = json.load(handle)
        validate_record(real, schema, "real record")
        validate_record(bypassed, schema, "bypassed record")
        tolerances = load_tolerances(args)
        result = evaluate(real, bypassed, tolerances)
    except (OSError, json.JSONDecodeError, MetricsError, ValueError) as exc:
        print(json.dumps({"check": METRIC_NAME, "status": "skip", "detail": str(exc)}))
        return 2

    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
