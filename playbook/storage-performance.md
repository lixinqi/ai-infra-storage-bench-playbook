# 存储表现：SLI、SLO 与存储版本对比

## 1. SLI 与 SLO 是两件事

| | SLI | SLO |
|---|---|---|
| 范围 | 全部样本 | 重保子集 |
| 有没有阈值 | 没有 | 有，部署时由使用方指定 |
| 每次运行做什么 | 测量并留存 | 用 SLI 值对照阈值判定 |
| 回答的问题 | 这次存储表现如何 | 这批重保负载是否达标 |
| 谁定义 | 本仓库（指标口径） | 使用方（阈值） |

混用会同时坏两件事：把 SLI 当 SLO，就等于没有标准也要判通过；把 SLO 当 SLI，就只测重保子集，丢掉全集随时间变化的趋势。

## 2. 存储版本：backend 与 adapter 两层

存储系统拆成两层，分别独立记录版本：

| 层 | 是什么 | 例子 | 环境变量 |
|---|---|---|---|
| backend | 纯存储系统 | GPFS、HDFS、Alluxio、Ceph、JuiceFS | `AI_INFRA_STORAGE_BACKEND` |
| adapter | AI Infra 存储传输适配层组件 | mooncake、torchstore、bytecheckpoint | `AI_INFRA_STORAGE_ADAPTER` |

规则：

1. **每个样本必须同时声明两者。** 运行请求的 `storage.backend` 与 `storage.adapter` 都要填。
2. **服务在样本进程里注入这两个环境变量**，值是组件名。样本代码必须读取它们；未设置时直接报错退出，不允许默认值——默认值会让"测的是哪个后端"变成隐式信息。
3. **版本与配置单独记录**：`name`、`version`、`config_ref` 写进运行清单。环境变量只传名字，不传版本。
4. **比较两个存储版本时，只允许一层不同**，或者两层都不同但结论按层分别归因。两层一起变却只报一个总账，等于没测。

组合维度进入覆盖矩阵：`storage_backend` × `storage_adapter` 是评估集的两根轴。

## 3. SLI：每个样本都测

SLI 只有指标与测量值，没有阈值。三类负载各自一组：

### 3.1 checkpoint

| SLI | 定义 | 单位 |
|---|---|---|
| `checkpoint_duration_s` | 开始写到元数据可见的总时长 | s |
| `training_stall_s` | 训练实际被阻塞的时长；异步写入扣除重叠部分 | s |
| `restore_duration_s` | 从 checkpoint 恢复到可继续训练的时间 | s |
| `write_throughput_bytes_s` | 写入期间聚合与每 rank 吞吐 | B/s |
| `metadata_commit_ms` | 分片元数据提交到可见的时长 | ms |
| `write_latency_p99_ms` | 单个写请求的 P99 | ms |

### 3.2 dataset

| SLI | 定义 | 单位 |
|---|---|---|
| `data_stall_ratio` | 训练 step 因等数据空转的时间 / 总 step 时间 | 比例 |
| `time_to_first_batch_s` | 启动到拿到第一个 batch 的时长 | s |
| `batch_latency_p99_ms` | 取一个 batch 的 P99 | ms |
| `sample_latency_p99_ms` | 单个样本读取与解码的 P99 | ms |
| `read_throughput_bytes_s` | 聚合与每 rank 读取吞吐 | B/s |
| `metadata_ops_rate` | 小文件与列目录的 op rate | 次/s |
| `read_amplification` | 实际读取字节 / 逻辑需要字节 | 比值 |
| `cache_hit_ratio` | 页缓存、本地盘、分布式缓存的分层命中率 | 比例 |

### 3.3 kvcache

| SLI | 定义 | 单位 |
|---|---|---|
| `ttft_p99_ms` | 首 token 延迟的 P99 | ms |
| `tpot_p99_ms` | 相邻 token 间隔的 P99 | ms |
| `request_success_rate` | 成功完成的请求比例 | 比例 |
| `kv_read_bytes_s` / `kv_write_bytes_s` | KV 读写吞吐 | B/s |
| `prefix_hit_ratio` | 前缀复用命中的块占比 | 比例 |
| `eviction_rate` | 单位时间驱逐的块数 | 次/s |
| `offload_bytes_s` | 换出到下一层缓存的字节速率 | B/s |
| `cross_node_transfer_latency_p99_ms` | 跨节点 KV 搬运的 P99 | ms |
| `block_alloc_latency_p99_us` | 块分配与释放的 P99 | µs |

### 3.4 归因用的底层 SLI

吞吐、IOPS、延迟分位、排队深度、饱和度、rank 间公平性、错误与重试、元数据 op rate、窗口稳定性、相对上限的效率。它们解释"为什么这个 SLI 是这个值"，不参与 SLO 判定，也不单独作为结论。

## 4. SLI 的留存与版本对比

### 4.1 留存

每次运行都写一份 `sli.json`，**全部保留**，不覆盖。存放：

```text
sli/<sample_key>/<storage_id>/<run-id>.json
```

- `sample_key` = hash(recipe, model id + commit, framework, load, topology, level)。同一份负载换存储版本时，它不变。
- `storage_id` = `backend.name@version+config_hash` / `adapter.name@version+config_hash`。

保留期至少覆盖比较窗口（默认一年）。只留最新一份，就无法回答"换后端前后差多少"。

### 4.2 比较两个存储版本

同一 `sample_key`、两份 `sli.json`、不同 `storage_id`：

1. 逐指标算差值：绝对差与相对差。
2. 与噪声带比较：噪声带由同一存储版本的重复运行导出（k × 变异系数，k 与次数写进标定记录），不是固定百分比。
3. 结论三选一：提升、退化、不可比（差值落在噪声带内，或任一侧运行不稳）。
4. 按层归因：`storage.backend` 变了归 backend，`storage.adapter` 变了归 adapter，两层同时变则分别报告。

比较报告只做"哪边好、差多少"，不做通过/不通过——那是 SLO 的事。

## 5. SLO：重保子集，阈值由使用方给

### 5.1 选择子集

重保负载是评估集的一个子集，例如某几个模型族的推理、某类训练任务。选择器写在部署的 `slo.yaml` 里：

```yaml
selector:
  recipe: kvcache
  model_family: [llama-like]
  scale: ["7B", "70B"]
  storage_backend: [gpfs]
```

### 5.2 阈值不由本仓库提供

SLO 阈值由使用方在部署评估集时指定，来源必须是三者之一：需求文档、基线测量、上限与效率目标。仓库只定义记录阈值的字段结构：

```yaml
slos:
  - metric: ttft_p99_ms
    comparator: "<="
    target: TBD            # 部署方填写，仓库不提供数字
    unit: ms
    provenance: {kind: requirement, ref: "<需求编号>", date: 2026-10-30}
    valid_for: {backend: [gpfs], adapter: [torchstore], topology: "S0–S2"}
    review_due: 2027-01-30
```

没有 `provenance` 或 `valid_for` 的阈值不允许用于判定。

### 5.3 判定

- 只对选择器选中的样本判定，其余样本只产 SLI。
- 用 SLI 值对照阈值；置信区间跨过阈值时判"不可比"，不判通过。
- 阈值过期、超出 `valid_for` 范围、存储版本变更未重标，一律判"不可比"。
- 判定结果写 `slo-result.json`，并且必须引用所用的阈值版本与 SLI 回链。

## 6. 采集与统计要求

1. **预热**：丢弃前 10% 或前 N 轮，规则写进配方。
2. **窗口**：至少 60 秒或固定字节数，取较长者；窗口内吞吐变异系数 > 10% 判不稳。
3. **重复**：同一配置至少 3 次，报告 min / median / max；极差 > 10% 判不可比。
4. **尾延迟样本量**：P99 至少 10⁴ 次请求，P999 至少 10⁵ 次；不足时只报区间。
5. **独占**：同一后端同一时刻只跑一个高带宽样本。
6. **观测开销**：开关观测各跑一次，关键指标变化 ≤ 3%。
7. **打点**：SLI 的起止点在应用层定义（checkpoint 开始写与元数据可见；step 等数据与 batch 就绪；请求到达、首 token、末 token），写进配方。
8. **环境变量**：样本启动时校验 `AI_INFRA_STORAGE_BACKEND` 与 `AI_INFRA_STORAGE_ADAPTER` 均非空。

## 7. 报告

### 7.1 `sli.json`（每个样本每次运行）

| 字段 | 内容 |
|---|---|
| `sample_key` | 负载身份，跨存储版本稳定 |
| `run_id` | 运行标识 |
| `workload` | `checkpoint` / `dataset` / `kvcache` |
| `storage` | backend 与 adapter 的 name、version、config_ref |
| `window` | 预热、稳态起止、变异系数 |
| `metrics` | 第 3 节的 SLI 值 |
| `attribution` | 底层 SLI，解释用 |
| `evidence` | manifest、io-pattern、原始数据位置与 sha256 |

### 7.2 `slo-result.json`（只对重保子集）

| 字段 | 内容 |
|---|---|
| `sample_key` | 被选中的样本 |
| `slo_ref` | 阈值文件版本与条目 |
| `metric` / `target` / `observed` | 对照结果 |
| `verdict` | `pass` / `fail` / `inconclusive` |
| `sli_uri` | 对应 `sli.json` 的回链 |

两份报告都只引用，不入库。

## 8. 常见错误

| 错误 | 后果 | 处置 |
|---|---|---|
| 用 SLI 判通过 | 没有标准，永远算过 | 判定只走 SLO |
| 只测重保子集 | 丢掉全集趋势 | SLI 覆盖全部样本 |
| 只存最新 SLI | 无法跨版本比较 | 全量留存 |
| backend 与 adapter 同时换只报一个总账 | 无法归因 | 按层分别报告 |
| 样本用默认后端 | 测的存储说不清 | 环境变量缺失即报错 |
| 阈值事后调整 | 结论不可比 | 阈值带版本，改动走评审 |
| 固定百分比当噪声带 | 换环境就不成立 | 用重复运行导出噪声带 |

## 9. 与其它文档的关系

- IO pattern 定义在 [`methodology.md`](methodology.md)，本篇消费它的输出。
- 单级内的 SLI/SLO 与版本比较在本篇；放大到多级规模时由 [`scaling.md`](scaling.md) 处理。
- 判定阈值属于部署配置，不在本仓库；`slo.yaml` 用选择器绑定到样本，配方本身不存阈值。
- 评估集自身是否可信（对齐、覆盖、scaling 一致性）由 `metrics/` 定义。
