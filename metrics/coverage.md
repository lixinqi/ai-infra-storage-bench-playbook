# 覆盖度

版本 1.0.0。

## 定义

评估集在目标维度矩阵上的填充程度。用于判断"还有哪些场景没测过"，是 playbook 生成下一版评估集的输入。

## 口径

覆盖度按矩阵计算。轴由配方声明（`metrics.yaml` 的 `params.axes`），至少三项，且必须包含 `arch_family`。

```text
格子 = (arch_family, model_scale, attention, framework, parallel, cluster, io_feature, storage_backend, storage_adapter)
```

轴的具体取值由配方决定，不在 schema 里固定。每个格子的状态：

| 状态 | 含义 | 是否计入分母 | 是否计入已覆盖 |
|---|---|---|---|
| `covered` | 至少一个用例，最近一次运行通过 | 是 | 是 |
| `failed` | 有用例，最近一次运行不通过 | 是 | 否 |
| `stale` | 有用例，超过一个版本周期未运行 | 是 | 否 |
| `gap` | 应该有但没有 | 是 | 否 |
| `exempt` | 明确判定不需要覆盖，有理由与复核日期 | 否 | 否 |

计算：

```text
覆盖度 = covered格子数 / (covered + failed + stale + gap)格子数
缺口率 = gap格子数 / 分母
```

`exempt` 不进分母。豁免过期（超过复核日期）时自动转为 `gap`。

## 阈值

阈值只有一个：`coverage_ratio_min`，写在配方的 `metrics.yaml`：

```yaml
tolerance:
  coverage_ratio_min: 0.6
```

阶段目标（例如"架构族每个至少 3 个用例"）写在 `params.targets`，是规划目标，不参与通过判定。

## 采集

输入是一份覆盖度清单（JSON），结构见 `schemas/coverage.schema.json`，由评估服务在每次运行后更新。清单放对象存储，仓库里只放 schema 与计算脚本。

## 判定

| 情况 | 结论 |
|---|---|
| 覆盖度 ≥ `coverage_ratio_min` | 通过 |
| 覆盖度低于阈值 | 不通过，缺口按优先级排序 |
| 豁免过期 | 转为缺口，重新计算 |
| 清单非法（缺轴、状态未知） | 不可比，重跑 |

## 已知限制

- 轴是人定的，轴选错了，覆盖度再高也测不到真正的风险。
- "覆盖"只表示通过用例存在，不表示该格子的 IO 特征被充分覆盖；同一格子内样本可能高度相似。
- 覆盖度对用例数量敏感，批量加入相似用例会让覆盖度虚高，需要配合结构距离分布一起看。

## 变更记录

| 版本 | 变更 |
|---|---|
| 1.0.0 | 首版；轴改为配方声明，阈值统一为 coverage_ratio_min |
