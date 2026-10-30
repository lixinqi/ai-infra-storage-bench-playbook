#!/usr/bin/env python3
"""Validate repository metadata against the JSON schemas in schemas/.

Checks performed:
  1. every recipes/<name>/recipe.yaml validates against schemas/recipe.schema.json
  2. every recipes/<name>/metrics.yaml validates against schemas/metrics.schema.json
  3. required files exist in each recipe directory
  4. recipe name matches its directory name; metrics file names its recipe
  5. metric name, version and gate agree with metrics/registry.yaml
  6. every metric gate appears in the recipe's acceptance.gates
  7. every metric and version appears in the recipe's compatible_metrics
  8. declared items are backed by a tolerance entry
  9. depends_on entries point at existing recipe directories
 10. examples/run-spec.json validates against schemas/run-spec.schema.json

Exit codes: 0 all checks pass, 1 validation failed, 2 dependencies missing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import yaml
    from jsonschema import Draft202012Validator
except ImportError as exc:  # pragma: no cover - depends on environment
    print(
        json.dumps(
            {
                "check": "validate_repo",
                "status": "skip",
                "detail": f"missing dependency: {exc.name}; install with pip install -r requirements.txt",
            }
        )
    )
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"
SCHEMAS = ROOT / "schemas"
REGISTRY = ROOT / "metrics" / "registry.yaml"
REQUIRED_FILES = ("README.md", "recipe.yaml", "metrics.yaml", "acceptance-checklist.md")


def load_yaml(path: Path) -> object:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_schema(name: str) -> dict:
    with (SCHEMAS / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def schema_errors(instance: object, schema: dict) -> list[str]:
    validator = Draft202012Validator(schema)
    messages = []
    for error in sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path)):
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        messages.append(f"{location}: {error.message}")
    return messages


def load_registry() -> dict[str, dict]:
    data = load_yaml(REGISTRY)
    if not isinstance(data, dict) or not isinstance(data.get("metrics"), list):
        raise ValueError("metrics/registry.yaml must contain a metrics list")
    return {
        entry["name"]: {
            "version": entry["version"],
            "supported": set(entry.get("supported", [entry["version"]])),
            "gates": set(entry.get("gates", [])),
        }
        for entry in data["metrics"]
    }


def validate_schemas(name: str, recipe: object, metrics: object, errors: list[str]) -> None:
    for message in schema_errors(recipe, load_schema("recipe.schema.json")):
        errors.append(f"recipes/{name}/recipe.yaml {message}")
    for message in schema_errors(metrics, load_schema("metrics.schema.json")):
        errors.append(f"recipes/{name}/metrics.yaml {message}")


def validate_identity(name: str, recipe: dict, metrics: dict, errors: list[str]) -> None:
    if recipe.get("name") != name:
        errors.append(f"recipes/{name}: recipe name is {recipe.get('name')!r}, expected {name!r}")
    if metrics.get("recipe") != name:
        errors.append(f"recipes/{name}: metrics recipe is {metrics.get('recipe')!r}, expected {name!r}")


def validate_files(name: str, errors: list[str]) -> None:
    directory = RECIPES / name
    for filename in REQUIRED_FILES:
        if not (directory / filename).is_file():
            errors.append(f"recipes/{name}: required file {filename} is missing")


def validate_compatible_keys(recipe: dict, registry: dict[str, dict], errors: list[str], name: str) -> None:
    for metric_name in recipe.get("compatible_metrics", {}):
        if metric_name not in registry:
            errors.append(f"recipes/{name}: compatible_metrics names unknown metric {metric_name!r}")


def validate_publication(
    name: str, entry: dict, recipe: dict, registry: dict[str, dict], errors: list[str]
) -> None:
    metric_name = entry.get("name")
    published = registry.get(metric_name)
    if published is None:
        errors.append(f"recipes/{name}: metric {metric_name!r} is not registered in metrics/registry.yaml")
        return

    version, gate = entry.get("version"), entry.get("gate")
    if version not in published["supported"]:
        errors.append(
            f"recipes/{name}: metric {metric_name} version {version} is not published "
            f"(supported: {sorted(published['supported'])})"
        )
    if gate not in published["gates"]:
        errors.append(
            f"recipes/{name}: metric {metric_name} declares gate {gate}, "
            f"but the registry serves gates {sorted(published['gates'])}"
        )
    if gate not in set(recipe.get("acceptance", {}).get("gates", [])):
        errors.append(
            f"recipes/{name}: metric {metric_name} is judged at {gate}, "
            f"but acceptance.gates does not list it"
        )


def validate_binding(name: str, entry: dict, recipe: dict, errors: list[str]) -> None:
    metric_name, version = entry.get("name"), entry.get("version")
    compatible = recipe.get("compatible_metrics", {}).get(metric_name)
    if compatible is None:
        errors.append(f"recipes/{name}: metric {metric_name} is missing from compatible_metrics")
    elif version not in compatible:
        errors.append(
            f"recipes/{name}: metric {metric_name} uses version {version}, "
            f"not listed in compatible_metrics[{metric_name!r}]"
        )

    items = set(entry.get("items", []))
    tolerance = set(entry.get("tolerance", {}))
    if items and items != tolerance:
        errors.append(
            f"recipes/{name}: metric {metric_name} item list and tolerance keys differ: "
            f"missing tolerance {sorted(items - tolerance)}, unused tolerance {sorted(tolerance - items)}"
        )


def validate_metric_entry(
    name: str, entry: dict, recipe: dict, registry: dict[str, dict], errors: list[str]
) -> None:
    validate_publication(name, entry, recipe, registry, errors)
    if entry.get("name") in registry:
        validate_binding(name, entry, recipe, errors)


def validate_metric_refs(
    name: str, recipe: dict, metrics: dict, registry: dict[str, dict], errors: list[str]
) -> None:
    validate_compatible_keys(recipe, registry, errors, name)
    for entry in metrics.get("metrics", []):
        validate_metric_entry(name, entry, recipe, registry, errors)


def validate_dependencies(name: str, recipe: dict, errors: list[str]) -> None:
    for dependency in recipe.get("depends_on", []):
        if not (ROOT / dependency).is_dir():
            errors.append(f"recipes/{name}: depends_on entry {dependency!r} does not exist")


def check_recipe(name: str, registry: dict[str, dict], errors: list[str]) -> None:
    directory = RECIPES / name
    recipe_path, metrics_path = directory / "recipe.yaml", directory / "metrics.yaml"
    validate_files(name, errors)
    if not recipe_path.is_file() or not metrics_path.is_file():
        return

    recipe = load_yaml(recipe_path)
    metrics = load_yaml(metrics_path)
    if not isinstance(recipe, dict) or not isinstance(metrics, dict):
        errors.append(f"recipes/{name}: recipe.yaml and metrics.yaml must be mappings")
        return

    validate_schemas(name, recipe, metrics, errors)
    validate_identity(name, recipe, metrics, errors)
    validate_metric_refs(name, recipe, metrics, registry, errors)
    validate_dependencies(name, recipe, errors)


EXAMPLE_FILES = (
    ("run-spec.json", "run-spec.schema.json"),
    ("sli.json", "sli.schema.json"),
)


def check_examples(errors: list[str]) -> None:
    for filename, schema_name in EXAMPLE_FILES:
        example = ROOT / "examples" / filename
        if not example.is_file():
            errors.append(f"examples/{filename} is missing")
            continue
        with example.open(encoding="utf-8") as handle:
            instance = json.load(handle)
        for message in schema_errors(instance, load_schema(schema_name)):
            errors.append(f"examples/{filename} {message}")


def recipe_directories() -> list[str]:
    return [
        directory.name
        for directory in sorted(RECIPES.iterdir())
        if directory.is_dir() and not directory.name.startswith("_")
    ]


def report(checked: list[str], errors: list[str]) -> int:
    for name in checked:
        failed = any(error.startswith(f"recipes/{name}") for error in errors)
        print(f"recipe {name}: {'failed' if failed else 'ok'}")
    if errors:
        print("")
        for error in errors:
            print(f"error: {error}")
        return 1
    print(f"\nall checks passed ({len(checked)} recipes)")
    return 0


def main() -> int:
    if not RECIPES.is_dir():
        print("recipes/ directory not found")
        return 1

    checked = recipe_directories()
    if not checked:
        print("no recipe directories found under recipes/")
        return 1

    registry = load_registry()
    errors: list[str] = []
    for name in checked:
        check_recipe(name, registry, errors)
    check_examples(errors)
    return report(checked, errors)


if __name__ == "__main__":
    sys.exit(main())
