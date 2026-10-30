"""配方执行入口模板。

复制到 recipes/<评估集名>/build.py 后，按配方的实际流程实现三个阶段：

1. prepare：校验输入，准备模型代码、配置、依赖与数据布局。
2. run：按 recipe.yaml 声明的旁路方式执行，保持存储与传输路径真实。
3. collect：采集 IO pattern，写出与 schemas/io-pattern.schema.json 一致的记录。

本文件只给出骨架与约束检查，不包含任何真实实现。真实实现属于具体配方。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RECIPE_DIR = Path(__file__).resolve().parent
REPO_ROOT = RECIPE_DIR.parents[1]


def prepare() -> dict:
    """校验输入并返回运行规格。"""
    raise NotImplementedError("按配方 README 的步骤实现")


def run(spec: dict) -> dict:
    """执行一次评估，返回运行句柄与产物位置。"""
    raise NotImplementedError("接入旁路实现，保持存储与传输路径真实")


def collect(handle: dict) -> dict:
    """采集 IO pattern，返回与 io-pattern.schema.json 一致的记录。"""
    raise NotImplementedError("按 playbook/methodology.md 的度量项采集")


def main() -> int:
    raise NotImplementedError("串联 prepare / run / collect，并写出产物清单")


if __name__ == "__main__":
    sys.exit(main())
