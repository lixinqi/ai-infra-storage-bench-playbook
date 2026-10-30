# ai-infra-storage-bench-playbook

本仓库是 **playbook**：生成、运行与校验 AI Infra 存储传输侧评估集的程序。

它的产物是 **bench**：三类带版本的静态评估集——模型代码收集、checkpoint / dataset 存储评估、kvcache 存储评估。评估集本身不会变化；让它变化的是这里的配方、指标与扩展流程。

评估用**真实模型代码产生的 IO**，测存储与传输在训练、推理、集群规模下的行为。

## playbook 产出的三类评估集

| 评估集 | 测什么 | 用例从哪来 | 产出 | 配方目录 |
|---|---|---|---|---|
| 模型代码收集 | 语料是否够多、够全、能跑 | HuggingFace 等平台的 model id | 清单（manifest）、覆盖矩阵 | `recipes/model-code-collection/` |
| checkpoint / dataset | 训练侧 checkpoint 写读、dataset 读取的 IO | 模型代码收集产出的训练代码 + 训练框架 | IO pattern 记录、对齐结果、scaling 结果 | `recipes/checkpoint-dataset/` |
| kvcache | 推理侧 KV 分配、读写、复用、驱逐、跨节点搬运 | 模型代码收集产出的推理代码 + vllm / sglang / deepinfer | 同上，prefill 与 decode 分开 | `recipes/kvcache/` |

### 模型代码收集

- 输入：从 HuggingFace 等平台抓 model id，下载代码与配置，不下载权重。
- 处理：按结构指纹去重；mock 分布式进程组，分时占用单卡把每个 rank 跑一次前向。
- 产出：每个模型一条清单记录（model id、commit、结构指纹、可跑性结论、训练代码配对结论），外加架构族 × 规模 × 注意力变体 × 框架的覆盖矩阵。
- 验收（初始目标）：推理模型 1000+，可跑率 85%，架构族 20+，6 个参数量级每级至少 10 个样本，训练代码配对率 40%。
- 它不产出 IO 数据。它是另外两类的原料。

### checkpoint / dataset 存储评估

- 评估对象：checkpoint 写入、checkpoint 读取、dataset 读取三条真实路径。
- 做法：meta device 旁路 forward / backward / optimizer；checkpoint 与 DataLoader 保持真实。每个 rank 的分片、字节数、并发、时序照实记录。
- 产出：一次运行的 IO pattern 记录（请求大小直方图、读写比、并发度、时序），SLO 表现（`checkpoint_duration_s`、`training_stall_s`、`restore_duration_s`），与真实运行的对齐结果，以及逐级 scaling 结果。
- 规模阶梯：S0 单机 8 卡 → S1 双机 → S2 64–128 卡 → S3 千卡 → S4 万卡 → S5 十万卡。
- 验收：对齐分项在阈值内；每参数字节数误差 ≤ 2%；每一级的不变量保持。

### kvcache 存储评估

- 评估对象：块分配与释放、KV 写入与读取、前缀复用、驱逐与 offload、跨节点传输。
- 做法：meta device 旁路 prefill / decode 计算；占位 attention 仍按真实块表与偏移读写 KV。调度器、块管理器、缓存与传输层不改。
- 覆盖：三种推理框架（vllm / sglang / deepinfer）× 多种模型结构、KV 头数与规模。
- 验收：每 token KV 写入字节误差 ≤ 1%；前缀命中率一致；prefill 与 decode 分别对齐；逐级 scaling 通过。
- 产出与 checkpoint 评估相同：IO pattern、SLO 表现（`ttft_p99`、`tpot_p99`、请求成功率）、对齐结果、scaling 结果。

以上数字是配方的验收目标与初始阈值，改动以 `recipes/<name>/recipe.yaml` 与 `metrics.yaml` 为准；README 只是摘要。

## 一次运行是什么样

输入是一份运行请求（结构见 [`schemas/run-spec.schema.json`](schemas/run-spec.schema.json)）：

```yaml
recipe: kvcache
recipe_version: 0.1.0
model: {id: example/tiny-64, commit: "0123456789abcdef0123456789abcdef01234567"}
framework: {name: vllm, version: 0.0.0-example}
level: S1
topology: {nodes: 2, gpus_per_node: 8, network: rdma, storage: local-nvme}
load: {concurrency: 8, input_len: 128, output_len: 64, duration_s: 60}
observe: {enabled: true, sample_rate: 0.1, layers: [app, sys]}
seed: 20261030
```

评估服务按配方执行，产出：

```text
runs/<run-id>/
  manifest.json     本次运行的全部输入、版本、拓扑
  metrics.json      度量值
  alignment.json    与真实运行的对齐结果
  report.html       人读报告
```

回链写进配方的 `latest_run`，仓库里只留 URI、sha256、状态。产物本身在对象存储。

## 为什么要做这件事

计算侧已经有成体系的 benchmark 与自动回归：模型能力有持续的评测集，代码优化有自动的搜索与回归，训练与推理性能有固定的套件。存储传输侧没有对应的东西：

- 评估对象是**真实模型代码产生的 IO**，不是合成负载。合成负载可以随便调参，测不出真实场景的破坏点。
- 评估要能**从一张卡外推到十万卡**，否则单机结论回答不了集群规模的问题。
- 扩展要由 **playbook** 完成：评估集是静态产物，不会自己变化；新模型、新框架、新并行策略出现时，由 playbook 发现覆盖缺口并生成新版本。

这三件事合起来，才构成存储传输侧的 RSI 闭环。

## 本仓库是什么，不是什么

| 是 | 不是 |
|---|---|
| 三类评估集的配方与运行规范（`playbook/`、`recipes/`） | 评估报告的归档处 |
| 指标口径与可执行校验（`metrics/`、`checks/`） | 原始数据、模型权重、checkpoint 的存放处 |
| 运行请求、产物与回链的 schema（`schemas/`） | 运行日志、trace 文件、大产物的存放处 |
| 最小可跑样例与负例（`examples/`） | 生产集群的运维手册 |
| 结果回链规范（URI + sha256 + 状态） | 一次性的调优记录 |

边界判断只有一条：**依赖手册运行产生的东西，不等于属于手册。** 运行结果放对象存储或 CI artifact，仓库里只留回链。

## 结构

```text
.
├── playbook/                 跨评估集的方法论与三类评估集的方法
│   ├── principles.md         定位、目标、边界、为什么做这套 benchmark
│   ├── methodology.md        唯一的方法出处：旁路、保真、IO pattern、对齐、阶段门
│   ├── model-code-collection.md   模型代码收集
│   ├── checkpoint-dataset.md      训练侧 checkpoint / dataset 评估
│   ├── kvcache.md                 推理侧 kvcache 评估
│   ├── scaling.md                 不变量、外推规则、逐级验证
│   ├── evaluation-service.md      评估服务
│   ├── extension.md               扩展：从缺口到新版本
│   ├── pitfalls.md                已知坑与开放问题
│   ├── storage-performance.md    存储表现：checkpoint / dataset / kvcache 各自的 SLO 与判定
│   └── appendix-glossary.md       基础术语：并行策略、模型结构、存储与 IO
├── recipes/                  三类评估集的可执行配方，一个评估集一个目录
│   ├── _template/            新配方的脚手架
│   ├── model-code-collection/
│   ├── checkpoint-dataset/
│   └── kvcache/
├── metrics/                  指标定义与登记表
├── checks/                   校验脚本：指标与仓库规范的可执行实现
├── schemas/                  recipe / metrics / io-pattern / run-spec 的 JSON Schema
├── scripts/                  维护脚本：新建配方、批量校验
├── meta-evaluation/          评估这套 playbook 自身：指标、方法、问卷
├── decisions/                关键取舍的决策记录（ADR）
├── examples/                 最小可跑样例与负例
├── requirements.txt          校验脚本的依赖
├── CONTRIBUTING.md           新增配方、修改指标、记录决策的流程
└── CHANGELOG.md              手册自身的版本变更
```

## 怎么跑校验

```text
python3 -m pip install -r requirements.txt
python3 scripts/validate_repo.py     # 配方、指标登记表、schema 的一致性
python3 scripts/run_checks.py        # 上面这项 + selftest + examples/ 样例
```

退出码：0 通过，1 不通过，2 缺依赖。缺依赖不算通过。校验脚本的阈值来自 `recipes/*/metrics.yaml`，不在代码里留默认值。

## 先读哪几篇

| 你要做的事 | 先读 |
|---|---|
| 判断这套 bench 能不能用 | [`playbook/principles.md`](playbook/principles.md)、[`metrics/coverage.md`](metrics/coverage.md) |
| 搭某个评估集 | [`playbook/methodology.md`](playbook/methodology.md) → 对应的 `recipes/<name>/README.md` |
| 验收别人的结论 | [`playbook/storage-performance.md`](playbook/storage-performance.md) + [`metrics/`](metrics/README.md) 三篇 + [`checks/README.md`](checks/README.md) |
| 评估这套 playbook 自身 | [`meta-evaluation/method.md`](meta-evaluation/method.md) |
| 把评估跑成服务 | [`playbook/evaluation-service.md`](playbook/evaluation-service.md) |
| 扩展评估集 | [`playbook/extension.md`](playbook/extension.md) |
| 查不认识的领域词 | [`playbook/appendix-glossary.md`](playbook/appendix-glossary.md) |

## 术语

- **bench（评估集套件）**：本仓库维护的整套设施，由 playbook、当前版本的评估集与回链规范组成，与"一次性测跑"相对。
- **playbook**：生成与维护评估集的方法与可执行配方，包括旁路方法、指标、评估服务与扩展流程。它是评估集的生成程序，文档在 `playbook/`。
- **评估集**：playbook 的产物，一个带版本的静态用例清单，每个用例包含模型代码、配置、运行参数与验收口径。构建完成后不变，扩展即由 playbook 生成新版本。
- **配方（recipe）**：构建与运行某个评估集的完整说明加可执行入口，一个评估集一份。
- **旁路**：把计算替换成不产生真实计算的实现（meta device、模块 mock），同时保留其余代码路径。
- **保真**：旁路之后，存储与传输代码产生的 IO 请求序列仍能代表真实运行；保真的程度用「保真边界表」逐项登记。
- **IO pattern**：一次运行产生的 IO 请求的可度量特征集合，见 [`playbook/methodology.md`](playbook/methodology.md) 的「IO pattern 的度量项」。
- **scaling 不变量**：从较小规模外推到较大规模时，必须保持稳定的那部分 IO 特征。
- **回链**：仓库里指向外部运行产物的引用，包含 URI、sha256、状态三要素。

存储与推理领域的基础词（分片、聚合带宽、元数据操作、尾延迟、读放大、基线、DP/TP/PP/EP、MoE、GQA/MQA/MLA）见 [`playbook/appendix-glossary.md`](playbook/appendix-glossary.md)。

## 约定

- 文档用中文写；代码、配置字段、文件名用英文。
- 新增或修改配方前先读 [`CONTRIBUTING.md`](CONTRIBUTING.md)。
- 任何一篇文档都不收藏运行结果；需要引用结果时只写回链。
- 不写具体内部规模与内部系统名；需要描述规模时用档位（千卡、万卡、十万卡），不写当期真实数量。
