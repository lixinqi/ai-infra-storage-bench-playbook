# 存储表现：按评估集判定

## 1. 两个问题，两套指标

| 问题 | 产出 | 定义在哪 |
|---|---|---|
| 这个样本向存储提出了什么要求 | IO pattern：请求大小、读写比、并发、时序 | [`methodology.md`](methodology.md) 的「IO pattern 的度量项」 |
| 存储在这个要求下给得怎么样 | 存储表现：SLO 是否达成，不达成时卡在哪 | 本篇 |

关键点：**三类评估集关注的 SLO 不一样，指标不能通用。** checkpoint 看"写一次多久、训练停多久"；dataset 看"训练等数据的比例、P99 batch 取数时长"；kvcache 看"TTFT、TPOT、跨节点搬运"。用统一的吞吐/延迟去判三类负载，会把真正的瓶颈掩盖掉。

因此本篇分两层：

- **SLO 指标**：判定用。每类评估集一组，见第 3 节。
- **底层指标**：归因用。SLO 没达成时，回答"卡在带宽、排队、元数据还是尾延迟"，见第 2 节。

## 2. 底层指标：用于归因，不用于判定

| 指标 | 定义 | 采集点 | 单位 |
|---|---|---|---|
| 吞吐 | 稳态窗口内完成的字节数 / 窗口时长；读、写分开 | 存储侧优先，系统层兜底 | B/s |
| IOPS | 完成的请求数 / 窗口时长；按请求大小分桶 | 存储侧 | 次/s |
| 延迟 | 请求从发起到完成的时长；P50/P95/P99/P999，读、写、元数据分开 | 客户端计时，存储侧交叉核对 | ms |
| 排队深度 | 同一时刻未完成的请求数分布 | 系统层 | 个 |
| 饱和度 | 设备利用率；聚合吞吐随并发增长是否已走平 | 存储侧 | 百分比 |
| 公平性 | rank 间吞吐的最大/最小比、Gini 系数 | 存储侧按 rank 拆分 | 比值 |
| 错误 | 超时率、重试率、错误码分布 | 客户端与存储侧 | 次/s、比例 |
| 元数据 | 创建、stat、列目录的 op rate 与 P99 | 存储侧 | 次/s、ms |
| 稳定性 | 稳态窗口内每秒吞吐的变异系数 | 存储侧 | 百分比 |
| 效率 | 实测聚合吞吐 / 上限；上限取链路、后端、客户端三者的最小值 | 计算 | 百分比 |

这些指标单独出现时**不能**回答"存储行不行"。存储侧吞吐很高，SLO 仍可能失败：checkpoint 的总时长被元数据提交卡住，dataset 的 P99 batch 被长尾样本拖住，kvcache 的 TTFT 被跨节点搬运卡住。判定一律用第 3 节的 SLO 指标，底层指标只在归因时使用。

## 3. 三类评估集各自的 SLO

阈值都是示例，必须按配方标定后写进 `recipe.yaml`，判定时才生效。

### 3.1 checkpoint：写一次多久，训练停多久

| SLO 指标 | 定义 | 为什么是它 |
|---|---|---|
| `checkpoint_duration_s` | 一次 checkpoint 从开始写到元数据提交完成的总时长 | 同步写入时这段时间训练完全停摆 |
| `training_stall_s` | 训练实际被阻塞的时长；异步写入时扣掉与计算重叠的部分 | 用户真正感知的是停顿，不是写入时长 |
| `restore_duration_s` | 从 checkpoint 恢复到可继续训练的时间 | 故障恢复的 SLO，和写入是两条路径 |
| `write_throughput_bytes_s` | 写入期间聚合与每 rank 吞吐 | 判断是否受限于存储带宽 |
| `metadata_commit_ms` | 分片元数据从开始提交到可见的时长 | 分片多时它常先于数据饱和 |
| `write_latency_p99` | 单个写请求的 P99 | 尾延迟决定最后一批 rank 何时完成 |

示例阈值（待标定）：`checkpoint_duration_s` ≤ 60；`training_stall_s` ≤ 5；`restore_duration_s` ≤ 120；`metadata_commit_ms` ≤ 2000。

判定顺序：先看 `checkpoint_duration_s` 是否达标；不达标再拆 `training_stall_s` 与 `metadata_commit_ms`，判断是数据带宽、元数据还是尾延迟；最后用底层指标定位到具体后端或分片。

### 3.2 dataset：训练等数据的比例，以及最慢的那一批

| SLO 指标 | 定义 | 为什么是它 |
|---|---|---|
| `data_stall_ratio` | 训练 step 因等待数据而空转的时间 / 总 step 时间 | 直接对应训练吞吐损失 |
| `time_to_first_batch_s` | 从启动到拿到第一个 batch 的时长 | 冷启动与弹性伸缩的 SLO |
| `batch_latency_p99` | 取一个 batch 的 P99 时长 | 平均值达标但尾部长，仍会拖慢 step |
| `sample_latency_p99` | 单个样本的读取与解码 P99 | 长尾样本决定 batch 完成时间 |
| `read_throughput_bytes_s` | 聚合与每 rank 读取吞吐；对照 `全局 batch 字节 / step 预算` | 判断是否够用，而不是越大越好 |
| `metadata_ops_rate` | 小文件与列目录的 op rate 与 P99 | shuffle 与小文件场景的瓶颈 |
| `read_amplification` | 实际读取字节 / 逻辑需要字节 | 缓存与预取是否有效 |
| `cache_hit_ratio` | 页缓存、本地盘、分布式缓存的分层命中率 | 解释远端请求量 |

示例阈值（待标定）：`data_stall_ratio` ≤ 1%；`time_to_first_batch_s` ≤ 30；`batch_latency_p99` ≤ step 预算的 80%；`metadata_ops_rate` 不低于需求的 1.2 倍。

dataset 的判定要先算"需求"：`全局 batch 字节 / step 预算` 得到所需吞吐，再对照实测。脱离 step 预算谈吞吐没有意义。

### 3.3 kvcache：首 token 等待，以及每个 token 的间隔

| SLO 指标 | 定义 | 为什么是它 |
|---|---|---|
| `ttft_p99` | 首 token 延迟的 P99 | 用户感知的响应速度 |
| `tpot_p99` | 相邻 token 间隔的 P99（也称 ITL） | 流式输出的顺滑程度 |
| `request_success_rate` | 成功完成的请求比例 | 超时、驱逐失败、传输失败都计入 |
| `kv_read_bytes_s` / `kv_write_bytes_s` | KV 读写吞吐 | 判断带宽是否成为瓶颈 |
| `prefix_hit_ratio` | 前缀复用命中的块占比 | 命中率直接改变 TTFT |
| `eviction_rate` | 单位时间驱逐的块数 | 显存不足的信号 |
| `offload_bytes_s` | 换出到下一层缓存的字节速率 | 分层缓存的代价 |
| `cross_node_transfer_latency_p99` | 跨节点 KV 搬运的 P99 | 预填充与解码分离时的关键路径 |
| `block_alloc_latency_p99` | 块分配与释放的 P99 | 调度抖动会直接反映在 TPOT 上 |

示例阈值（待标定）：`ttft_p99` ≤ 2 s；`tpot_p99` ≤ 50 ms；`request_success_rate` ≥ 99.9%；`cross_node_transfer_latency_p99` ≤ 20 ms。

kvcache 的判定按 prefill 与 decode 分开：TTFT 由 prefill 与 KV 写入决定，TPOT 由 decode 的 KV 读取与调度决定。合在一起看，会把两类问题混成一个。

## 4. 怎么采

三层，至少两层，优先"存储侧 + 系统层"：

| 层 | 能拿到 | 局限 |
|---|---|---|
| 应用层 | 请求的逻辑含义、SLO 起点与终点（如首个 token 的时间） | 看不到合并、排队与重试 |
| 系统层 | 真实下发、队列深度、重传 | 丢失逻辑归属 |
| 存储侧 | 服务端吞吐、延迟、错误、按 rank 拆分 | 采样率与聚合粒度受限 |

采集规则：

1. **预热。** 丢弃前 10% 的窗口或前 N 轮，取稳态。预热规则写进配方。
2. **窗口长度。** 至少 60 秒或至少固定字节数，取较长者。
3. **稳态判定。** 窗口内每秒吞吐的变异系数 > 10% 时延长窗口；仍不达标标记"不稳"，不出结论。
4. **重复。** 同一配置至少 3 次；报告 min / median / max。3 次中位数极差超过 10% 视为不可比。
5. **独占。** 同一后端同一时刻只跑一个高带宽样本。
6. **观测开销。** 开关观测各跑一次，关键指标变化 ≤ 3%；超过则降采样或改用系统层。
7. **SLO 起止点。** 在应用层打点：checkpoint 记开始写与元数据可见；dataset 记 step 开始等数据与 batch 就绪；kvcache 记请求到达、首 token、末 token。打点定义写进配方，不能只靠系统层推断。

## 5. 怎么判

判定必须在运行前声明：用哪些 SLO 指标、阈值多少、模式是什么。写进配方 `recipe.yaml`（当前用 `notes` 承载，schema 后续加字段）。

三种模式：

| 模式 | 比较对象 | 阈值来源 |
|---|---|---|
| `sla` | 绝对要求 | 需求或服务等级 |
| `baseline` | 上一个通过验收的版本 | 噪声带宽（默认 5%） |
| `efficiency` | 理论上限 | 效率百分比下限（初始 60%，待标定） |

判定表：

| 情况 | 结论 |
|---|---|
| 声明过的 SLO 全部达标 | 通过 |
| 任一 SLO 未达标，归因清楚且不影响目标结论 | 有条件通过，需评审 |
| 任一 SLO 未达标，归因不明 | 不通过 |
| 窗口不稳、重复不足、观测开销超限、配置变化 | 不可比，重跑 |
| 存储侧与客户端数据偏差 > 5% | 不可比，先解释偏差 |

**阈值与指标集不允许结果出来后调整。** 觉得阈值不合理，改配方、走评审、重跑。

## 6. 一个样本的报告

`performance.json`，与 `metrics.json` 并列存放：

```json
{
  "run_id": "...",
  "workload": "kvcache",
  "verdict_mode": "sla",
  "window": {"warmup_s": 30, "steady_start": "...", "steady_end": "...", "cv": 0.04},
  "slo": {
    "ttft_p99_ms": 1850,
    "tpot_p99_ms": 42,
    "request_success_rate": 0.9995,
    "cross_node_transfer_latency_p99_ms": 18
  },
  "storage": {
    "read_bytes_s": 0,
    "write_bytes_s": 0,
    "latency_p99_ms": 0,
    "saturation": {},
    "fairness": {},
    "errors": {},
    "metadata": {}
  },
  "verdict": "pass",
  "evidence": {"manifest": "...", "io_pattern": "...", "raw": "...", "sha256": "..."}
}
```

`slo` 的字段随 `workload` 变化：checkpoint 填 3.1 的指标，dataset 填 3.2 的，kvcache 填 3.3 的。`storage` 是归因用的底层指标，不参与判定。

报告只引用，不入库；回链写进配方的 `latest_run`。

## 7. 常见错误

| 错误 | 后果 | 处置 |
|---|---|---|
| 用通用吞吐/延迟代替 SLO | 存储看着很忙，用户侧仍然慢 | 判定只看 SLO 指标 |
| 三类负载套同一组阈值 | checkpoint 的 60 秒要求套到 kvcache 上毫无意义 | 按第 3 节分别声明 |
| 只报平均 TTFT | 尾延迟被掩盖 | 分位优先 |
| dataset 脱离 step 预算谈吞吐 | 无法判断够不够 | 先算需求吞吐 |
| 窗口包含预热 | 数据失真 | 固定预热规则 |
| 与其它样本并行跑 | 测到的是争用 | 同后端串行 |
| 单次运行当结论 | 噪声被当成信号 | 至少 3 次 |
| 事后调整阈值 | 结论不可比 | 运行前声明 |

## 8. 与其它文档的关系

- IO pattern 定义在 [`methodology.md`](methodology.md)，本篇消费它的输出。
- 单级内的判定在本篇；放大到多级规模时，SLO 随规模的变化由 [`scaling.md`](scaling.md) 处理。
- 判定阈值属于配方，写在 `recipes/<name>/` 下，与本篇的口径一致。
- 评估集自身是否可信（对齐、覆盖、scaling 一致性）由 `metrics/` 定义，不要和这一篇混。
