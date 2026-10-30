# 配方模板

复制本目录到 `recipes/<评估集名>/`，然后逐项替换尖括号内的占位内容。复制后不要保留尖括号。

## 六个文件各管什么

| 文件 | 内容 | 谁看 |
|---|---|---|
| `recipe.yaml` | 元信息、旁路范围、保真边界、不变量、scaling 计划、兼容的指标版本 | 评估服务、校验脚本 |
| `metrics.yaml` | 选用的指标、参数、阈值 | 评估服务、对齐判定 |
| `README.md` | 目标、输入、输出、步骤、验收、负责人 | 人 |
| `acceptance-checklist.md` | 阶段门 G0–G4 的勾选项 | 评审 |
| `checks/` | 本配方专属校验脚本 | CI |
| `build.py` | 配方入口：prepare / run / collect 三个阶段 | 实现者 |

## 填写的硬要求

1. `fidelity_boundary` 中凡是存储与传输路径，`fidelity` 不允许是 `L0`。
2. `io_pattern_invariants` 写 3–6 条，每条都要有可计算的定义与容差。
3. `scaling_plan` 至少两级，且必须写明固定哪些维度、放大哪个维度。
4. `compatible_metrics` 按指标名列出版本，且必须覆盖 `metrics.yaml` 里实际使用的版本。
5. 阈值只写在 `metrics.yaml` 的 `tolerance`，不要在别处再抄一份。
5. `latest_run` 初始为 `null`，由评估服务在首次运行后写入，不要手填。

## 复制之后

```text
python3 scripts/new_recipe.py <评估集名>
```

该脚本会完成复制与基础替换，并检查新目录是否满足以上五条要求。
