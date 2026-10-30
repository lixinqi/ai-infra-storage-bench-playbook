# 样例

这里的文件用于让校验脚本有可跑通的输入，也让新同学看到各类清单长什么样。**所有内容都是样例，不代表任何真实运行。**

## 正向样例

| 路径 | 用途 |
|---|---|
| `tiny-model/` | 最小模型代码与清单条目，演示 `recipes/model-code-collection` 的产物 |
| `io-pattern-real.json` | 真实运行的 IO pattern 记录 |
| `io-pattern-bypassed.json` | 旁路运行的记录，偏差在 kvcache 阈值内 |
| `coverage.json` | 覆盖度清单，覆盖度刚好等于阈值 0.6 |
| `scaling-levels.json` | 逐级不变量值 |
| `run-spec.json` | 提交给评估服务的运行请求，含 storage 两层 |
| `sli.json` | 一次运行的 SLI 记录，含存储两层身份 |

## 负向样例

`invalid/` 下的文件必须被拒绝。它们由 `checks/selftest.py` 使用，证明检查不只会通过。

| 文件 | 期望 |
|---|---|
| `io-pattern-bad-sources.json` | 只有一层采集来源，记录非法 |
| `metrics-unknown-tolerance.yaml` | 阈值里出现 check 不支持的键 |
| `coverage-missing-axis.json` | 格子缺 `arch_family` 轴 |
| `scaling-bad-lengths.json` | 不变量值个数与级别数不一致 |
| `run-spec-bad-level.json` | 规模档位不匹配 `^S[0-9]+$` |
| `sli-missing-storage.json` | SLI 记录缺存储两层身份 |
| `recipe-missing-field.yaml` | 配方缺 `metrics_ref` |

## 跑一遍

```text
python3 scripts/run_checks.py
```

单独跑一项时，阈值从配方读取：

```text
python3 checks/check_io_pattern.py \
  --real examples/io-pattern-real.json \
  --bypassed examples/io-pattern-bypassed.json \
  --metrics recipes/kvcache/metrics.yaml
```
