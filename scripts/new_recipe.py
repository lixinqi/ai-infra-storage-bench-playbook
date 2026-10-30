#!/usr/bin/env python3
"""Create a new recipe directory from recipes/_template.

Usage:
    python3 scripts/new_recipe.py kvcache-layered-cache

The script copies the template, replaces the recipe name, and rewrites remaining
placeholders as TODO markers. It does not invent values: every TODO has to be
filled by the recipe owner, and scripts/validate_repo.py will fail until it is.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "recipes" / "_template"
NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
PLACEHOLDER = re.compile(r"<[^<>\n]+>")


def replace_placeholders(target: Path, name: str) -> int:
    todo_count = 0
    for path in sorted(target.rglob("*")):
        if not path.is_file() or path.suffix not in {".md", ".yaml", ".py"}:
            continue
        text = path.read_text(encoding="utf-8").replace("<recipe-name>", name)
        text, replaced = PLACEHOLDER.subn("TODO", text)
        todo_count += replaced
        path.write_text(text, encoding="utf-8")
    return todo_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="recipe name, lowercase with hyphens")
    parser.add_argument("--force", action="store_true", help="overwrite an existing directory")
    args = parser.parse_args()

    if not NAME_PATTERN.match(args.name):
        print(f"invalid recipe name {args.name!r}: use lowercase letters, digits and hyphens")
        return 2

    target = ROOT / "recipes" / args.name
    if target.exists() and not args.force:
        print(f"{target} already exists; pass --force to overwrite")
        return 1

    shutil.copytree(TEMPLATE, target, dirs_exist_ok=args.force)
    todo_count = replace_placeholders(target, args.name)
    print(f"created recipes/{args.name} with {todo_count} placeholders to fill")
    print("next steps:")
    print(f"  1. edit recipes/{args.name}/recipe.yaml and metrics.yaml")
    print(f"  2. read recipes/{args.name}/README.md")
    print("  3. run python3 scripts/validate_repo.py until it passes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
