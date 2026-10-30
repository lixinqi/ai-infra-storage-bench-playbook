"""Helpers shared by the check scripts.

The rule these helpers exist to enforce: a threshold has exactly one home, the
recipe's metrics.yaml. Check scripts read that file through here and never keep
their own copy of the numbers.
"""

from __future__ import annotations

from pathlib import Path

import yaml


class MetricsError(ValueError):
    """Raised when a metrics file cannot supply what the check needs."""


def load_metrics(path: str) -> dict:
    with Path(path).open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("metrics"), list):
        raise MetricsError(f"{path}: no metrics list")
    return data


def find_metric(data: dict, name: str) -> dict:
    for entry in data["metrics"]:
        if entry.get("name") == name:
            return entry
    raise MetricsError(f"metric {name!r} is not declared in this recipe's metrics.yaml")


def tolerance_of(data: dict, name: str) -> dict:
    entry = find_metric(data, name)
    tolerance = entry.get("tolerance")
    if not isinstance(tolerance, dict) or not tolerance:
        raise MetricsError(f"metric {name!r} has no tolerance block")
    return {key: parse_threshold(value) for key, value in tolerance.items()}


def parse_threshold(value: object) -> float:
    """Accept 0.08 (ratio) or "8%" (percent). Anything else is an error, not a default."""
    if isinstance(value, bool):
        raise MetricsError(f"tolerance {value!r} is not a number")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("%"):
            return float(text[:-1]) / 100.0
        return float(text)
    raise MetricsError(f"tolerance {value!r} is neither a number nor a percent string")
