# 校验脚本

本目录放通用校验。只对这个评估集成立的校验放 `recipes/<name>/checks/`。

## 脚本

| 脚本 | 作用 | 入参 | 退出码 |
|---|---|---|---|
| `validate_repo.py` | 校验配方与 schema、指标登记表、阈值引用的一致性 | 无 | 0 通过，1 不通过，2 缺依赖 |
| `selftest.py` | 用 `examples/` 与 `examples/invalid/` 证明检查会通过、也会拒绝 | 无 | 0 符合预期，1 不符合，2 缺依赖 |
| `check_io_pattern.py` | 比较真实运行与旁路运行的 IO pattern | `--real`、`--bypassed`，阈值来自 `--metrics`，可用 `--tolerance` 逐项覆盖 | 0 通过，1 不通过，2 输入非法或缺阈值 |
| `check_coverage.py` | 从覆盖度清单计算覆盖度与缺口 | `--manifest`，阈值来自 `--metrics` 的 `coverage_ratio_min`，可用 `--min-coverage` 覆盖 | 0 达标，1 未达标，2 输入非法或缺阈值 |
| `check_scaling_consistency.py` | 计算逐级偏差与单调漂移 | `--input`，默认容差来自 `--metrics` 的 `per_level` 与 `first_last` | 0 一致，1 不一致，2 输入非法或缺阈值 |

## 阈值只有一个来源

阈值写在 `recipes/<name>/metrics.yaml` 的 `tolerance` 里，由评审把关。脚本通过 `--metrics` 读取同一份文件，不在代码里保留默认值。

- 值可以是小数（`0.08` 表示 8%）或百分号字符串（`"8%"`）。
- `tolerance` 的键必须是该 check 支持的度量项名，未知键直接报错退出 2。
- `items` 声明本配方判定哪些项，必须与 `tolerance` 的键完全一致；没有 `items` 时以 `tolerance` 的键为准。
- `--tolerance` 与 `--min-coverage` 只用于临时排查，不能作为结论依据。

`check_io_pattern.py` 支持的度量项：`request_size_distribution`、`read_write_ratio_bytes`、`read_write_ratio_ops`、`concurrency_p50`、`concurrency_p95`、`concurrency_max`、`sequentiality`、`hotness`、`per_token_kv_bytes`、`timing_peak`。

## 输入结构

- `--tolerance` 文件：一个 JSON 对象，键是指标项名，值是数字或百分号字符串，例如 `{"concurrency_p95": "20%"}`。
- `--input` 文件（scaling）：`{"levels": ["S0", ...], "invariants": {"<name>": {"values": [...], "tolerance": 0.1}}}`。`tolerance` 可省略，省略时用 `metrics.yaml` 的 `per_level`。
- `--manifest` 文件（coverage）：结构见 `schemas/coverage.schema.json`。

## 输出约定

`check_*.py` 与 `selftest.py` 在标准输出打印**一行** JSON，至少包含 `check` 与 `status`：

```json
{"check": "io-pattern-alignment", "status": "pass"}
```

通过、失败、跳过三态必须区分。**跳过不等于通过**：缺依赖、输入缺失、阈值缺失都算跳过，退出码 2。

`validate_repo.py` 打印人读的逐项结果与错误清单，不使用单行 JSON。

## 目录约定

- `recipes/` 下以 `_` 开头的目录是模板，`validate_repo.py` 跳过它们。
- 负例放在 `examples/invalid/`，由 `selftest.py` 使用；不作为正向样例。
- 新增检查时同时补一条正向与一条负向用例，否则 `selftest` 覆盖不到。

## 依赖

```text
pip install -r ../requirements.txt
```

缺依赖时脚本以退出码 2 结束，不假装通过。

## 与指标文档的关系

每个脚本对应 `metrics/` 的一篇文档，公式必须一致。改公式时两边一起改，并在指标文档的变更记录里写一行。
