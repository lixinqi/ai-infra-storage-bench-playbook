# 变更记录

本文件记录手册自身的变更。评估集的版本由各自的 `recipe.yaml` 记录，不写在这里。

## Unreleased

- 新增 [`playbook/storage-performance.md`](playbook/storage-performance.md)：按评估集分别定义 SLO——checkpoint 看写入时长与训练停顿，dataset 看数据停顿比例与 batch 尾延迟，kvcache 看 TTFT 与 TPOT；底层存储指标只用于归因。
- 新增 [`meta-evaluation/method.md`](meta-evaluation/method.md)：评估 playbook 自身的五个问题、测量方法与判定标准。
- 澄清静态产物与生成程序：评估集是带版本的静态用例清单，扩展由 playbook 完成；`playbook/self-evolution.md` 改名 `extension.md`。
- scaling 上限从万卡改为十万卡：阶梯扩为 S0–S5，S4 = 万卡（实测上限），S5 = 十万卡（外推目标）；配方、指标参数、检查清单与相关文档同步。
- 阈值单一来源：`check_io_pattern`、`check_coverage`、`check_scaling_consistency` 改从 `recipes/*/metrics.yaml` 读取，删除代码里的默认值；百分号与小数两种写法统一解析，未知键报错。
- 指标一致性加固：`validate_repo` 校验指标版本、gate、`compatible_metrics` 与登记表一致；`compatible_metrics` 改为按指标名列出版本。
- 扩展点放开：指标名、框架名、配方类别、阶段门改为 pattern；覆盖度轴改为配方声明；`run-spec` 的 `scale` 改名 `level`。
- 新增 `checks/selftest.py` 与 `examples/invalid/`，证明检查会拒绝非法输入。
- 新增 `playbook/appendix-glossary.md`，补齐并行策略、模型结构、存储与 IO 的基础词。
- `metrics/metric-schema.yaml` 改名 `metrics/registry.yaml`；`examples/tiny-model/entry.json` 改名 `manifest-entry.json`。
- 章节顺序调整：methodology 的阶段门前移；principles 的三类评估集关系前移；evaluation-service 的失败处理紧跟生命周期。
- 评估服务与扩展回归机制仍只有设计，没有实现；现有可执行部分是 `checks/`、`scripts/` 与 `examples/`。
- `playbook/methodology.md` 明确为方法的唯一出处：三类评估集只引用、只写差异，不复制定义。
- README 与 principles 明确本仓库是生成器（playbook），产物是 bench；仓库更名为 `ai-infra-storage-bench-playbook`（此前用过 `ai-infra-storage-rsi`、`ai-infra-storage-bench`、`ai-infra-storage-playbook`）；项目目标的表述只保留在 README 的「为什么要做这件事」里。
- 待定：评估服务接口的第一版实现。

## v0.1.0

首版草案。

- `playbook/`：定位与边界、核心方法论（旁路计算保真 IO）、三类评估集的方法（模型代码收集、checkpoint/dataset、kvcache）、scaling、评估服务、扩展闭环、已知坑。
- `recipes/`：三类评估集的配方模板与初始配方，每份包含保真边界表、scaling 不变量表、验收指标。
- `metrics/`：IO pattern 对齐度、覆盖度、scaling 一致性三个指标的定义与口径。
- `checks/`、`scripts/`：仓库规范校验、schema 校验、覆盖度计算。
- `meta-evaluation/`：评估手册本身的指标定义。
