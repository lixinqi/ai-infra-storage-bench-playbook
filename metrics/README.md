# 指标定义

本目录只放**口径**，不放实现。每个指标一篇文档，实现放在 `checks/`。

## 为什么先定口径

同一个名字在不同人手里会算出不同数。例如"IO pattern 对齐度"，可以按请求数算，也可以按字节数算；可以取平均，也可以取 P95。口径不统一，历史结果就不可比，回归全部失效。

因此：**任何进入 `recipes/*/metrics.yaml` 的指标，必须先在 `metrics/` 里有定义，并在 `metrics/registry.yaml` 登记。**

## 指标清单

| 指标 | 文档 | 版本 | 用途 |
|---|---|---|---|
| IO pattern 对齐度 | [`io-pattern-alignment.md`](io-pattern-alignment.md) | 1.0.0 | 判断旁路运行能否代表真实运行（阶段门 G2） |
| 覆盖度 | [`coverage.md`](coverage.md) | 1.0.0 | 判断评估集是否覆盖了目标维度 |
| scaling 一致性 | [`scaling-consistency.md`](scaling-consistency.md) | 1.0.0 | 判断外推依据是否成立（阶段门 G3） |

## 登记表

`registry.yaml` 是机器可读的登记表：每个指标的当前版本、支持的版本、可服务的阶段门、文档位置。新增指标时三者都要改：文档、登记表、引用它的配方配置。

`checks/validate_repo.py` 用登记表校验配方：

- 指标必须已登记；
- 配方使用的版本必须在登记表的 `supported` 里；
- 配方声明的 gate 必须是登记表为该指标列出的 gate；
- 该 gate 必须出现在配方的 `acceptance.gates` 里；
- 该指标与版本必须出现在配方的 `compatible_metrics` 里。

## 阈值放在配方，不放在文档

`metrics/` 的文档只定义口径与初始值。某个配方实际使用的阈值写在 `recipes/<name>/metrics.yaml` 的 `tolerance` 里，check 脚本通过 `--metrics` 读取同一份文件。文档里的数值是参考，不是执行值。

## 每篇指标的必填结构

1. **定义**：一句话说清它度量什么。
2. **口径**：计算公式、统计范围、时间窗口、单位、方向。
3. **阈值**：从哪读、怎么标定。
4. **采集**：需要哪些原始数据，由哪一层提供。
5. **判定**：通过 / 不通过 / 不可比。
6. **已知限制**：这个指标测不出什么。
7. **变更记录**：口径变更历史，旧口径保留在文档末尾。

## 兼容声明

配方的 `compatible_metrics` 按指标名声明版本列表：

```yaml
compatible_metrics:
  io-pattern-alignment: ["1.0.0"]
  scaling-consistency: ["1.0.0"]
```

服务在运行前校验：配方用的版本必须在该指标的列表里，且列表里的版本必须是登记表发布过的。两处都没有"猜"的空间。

## 不在本目录的内容

- 实现代码：放 `checks/`。
- 某次运行的实测值：放对象存储，仓库里只写回链。
- 业务结论：放配方的 `README.md`。
