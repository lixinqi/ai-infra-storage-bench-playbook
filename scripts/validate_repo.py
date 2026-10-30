#!/usr/bin/env python3
"""Entry point for repository validation. See checks/validate_repo.py for the rules."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    spec = importlib.util.spec_from_file_location("validate_repo", ROOT / "checks" / "validate_repo.py")
    if spec is None or spec.loader is None:
        print("cannot load checks/validate_repo.py")
        return 2
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main()


if __name__ == "__main__":
    sys.exit(main())
