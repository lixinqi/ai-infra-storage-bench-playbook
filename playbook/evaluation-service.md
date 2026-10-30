# 评估服务

评估集不能只是一堆配方。配方解决"怎么测"，服务解决"谁来跑、跑完放哪、结论怎么回到配方上"。

## 1. 服务边界

| 服务负责 | 服务不负责 |
|---|---|
| 接收运行请求，校验参数 | 决定评估集该覆盖什么 |
| 按配方准备环境、调度资源、执行 | 修改配方里的口径与阈值 |
| 采集、校验、聚合结果 | 解释结论的业务含义 |
| 把产物写入对象存储并生成清单 | 长期保存原始 trace（按保留期清理） |
| 把回链写回配方的 `latest_run` | 自动合并任何口径变更 |

判断标准：服务可以做任何"按配方执行"的事，不能做任何"改变配方语义"的事。

## 2. 接口

### 2.1 运行请求

一份运行请求包含：

| 字段 | 含义 |
|---|---|
| `recipe` | 配方标识，形如 `kvcache`，对应 `recipes/kvcache/` |
| `recipe_version` | 配方版本，必须与仓库里的版本一致 |
| `model` | 模型标识 + commit |
| `framework` | 框架名 + 版本（仅 kvcache 需要） |
| `level` | 规模档位，对应 `scaling.md` 的 S0–S5 |
| `topology` | 节点数、每节点卡数、网络与存储挂载方式 |
| `load` | 负载配置：并发、序列长度、到达间隔、持续时长 |
| `observe` | 观测配置：开关、采样率、采集层 |
| `seed` | 随机种子 |

请求不允许有"其它"字段。新增字段先改 schema，再改服务。

### 2.2 命令行

```text
eval run --spec <path-to-run-spec.yaml>
eval status <run-id>
eval result <run-id> --format json
eval cancel <run-id>
```

命令行是薄封装，行为与 HTTP 接口一致。

### 2.3 HTTP

```text
POST /v1/runs            提交运行，返回 run-id
GET  /v1/runs/{run-id}   查询状态与摘要
GET  /v1/runs/{run-id}/artifacts   列出产物
POST /v1/runs/{run-id}/cancel      取消
```

接口返回结构固定：`run_id`、`state`、`started_at`、`finished_at`、`error`、`artifacts`。

## 3. 运行的生命周期

```text
submitted → validating → queued → preparing → running → collecting → completed
                 │           │                     │
                 └─ rejected └─ cancelled           └─ failed
```

| 状态 | 含义 | 可观察的产出 |
|---|---|---|
| `submitted` | 已接收 | run-id |
| `validating` | 校验请求与配方版本 | 校验报告 |
| `queued` | 等待资源 | 排队位置与预计开始时间 |
| `preparing` | 拉代码、装依赖、准备数据、预热 | 环境清单 |
| `running` | 执行负载 | 运行中指标 |
| `collecting` | 采集收尾、校验、聚合 | 度量文件 |
| `completed` | 成功 | 产物清单与回链 |
| `failed` | 失败 | 错误分类与日志回链 |
| `rejected` | 请求不合法 | 拒绝原因 |
| `cancelled` | 用户取消 | 已产生的部分产物 |

失败必须分类：环境失败、依赖失败、代码不可跑、资源不足、超时、观测失败、断言失败。笼统的"失败"无法用于缺口分析。

## 4. 失败处理

| 失败类型 | 处理 |
|---|---|
| 环境失败 | 自动重试 2 次；仍失败则标记为环境问题并通知维护者 |
| 代码不可跑 | 不重试，记录到模型清单的缺口 |
| 资源不足 | 重新排队，不消耗重试次数 |
| 超时 | 记录超时点，保留已采集的度量 |
| 观测失败 | 重跑一次；仍失败则标记该次运行无效，不进入对齐统计 |
| 断言失败 | 保留现场，不重试，进入缺口分析 |

**无效运行不能算通过，也不能算失败。** 它没有结论，只是没有数据。这一点在统计里必须分开。

## 5. 调度

资源是 GPU 与存储带宽，两者都要调度。

| 策略 | 规则 |
|---|---|
| 队列 | 按优先级（回归 > 新用例 > 探索）+ 提交时间排序 |
| 分时 | 单卡可以被多个 rank 分时复用，同一时刻只允许一个 rank 占用，切换时清空显存 |
| 隔离 | 不同运行不共享工作目录；共享存储的写入路径按 run-id 隔离 |
| 配额 | 按团队配额限制并发与总卡时 |
| 抢占 | 只允许抢占探索类运行，回归类不可抢占 |
| 并发上限 | 同一存储后端上的高带宽运行串行执行，避免互相干扰导致测量失真 |

最后一条容易被忽略：两个高带宽评估并行跑，测出来的都是"争用下的性能"，不是评估结论。**同一时刻在同一存储后端上只跑一个高带宽用例**，是硬约束。

## 6. 产物与回链

### 5.1 目录布局

```text
s3://example-bucket/
  runs/<run-id>/
    manifest.json         运行清单：全部输入、版本、拓扑、观测配置
    metrics.json          本次运行的度量值
    alignment.json        对齐结果与容差对比
    report.html           人读的报告
    trace/                原始 trace（按保留期清理）
    artifacts/            产物：生成的配置、检查点片段、日志
```

### 5.2 清单

`manifest.json` 是回链的核心，至少包含：

```json
{
  "run_id": "...",
  "recipe": "checkpoint-dataset",
  "recipe_version": "0.1.0",
  "service_version": "0.1.0",
  "model": {"id": "...", "commit": "..."},
  "framework": null,
  "level": "S2",
  "topology": {"nodes": 8, "gpus_per_node": 8, "network": "...", "storage": "..."},
  "observe": {"enabled": true, "sample_rate": 0.1, "layers": ["app", "sys"]},
  "started_at": "...",
  "finished_at": "...",
  "state": "completed",
  "artifacts": [{"path": "metrics.json", "sha256": "..."}]
}
```

### 5.3 写回配方

运行完成后，服务把回链写进对应配方的 `latest_run`：

```yaml
latest_run:
  run_id: "..."
  report_uri: "s3://example-bucket/runs/<run-id>/report.html"
  metrics_uri: "s3://example-bucket/runs/<run-id>/metrics.json"
  sha256: "..."
  status: passed
  finished_at: "..."
```

写回只能由服务执行，且只能写 `latest_run` 的六个字段；配方里的口径、阈值、流程，服务无权修改。

## 7. 版本

四条版本必须同时记录，缺一条历史结果就不可比：

| 版本 | 存在哪 | 变了会怎样 |
|---|---|---|
| 配方版本 | `recipe.yaml` 的 `version` | 流程或口径变了 |
| 指标版本 | `metrics/*/version` | 度量定义变了 |
| 服务版本 | `manifest.json` 的 `service_version` | 执行方式变了 |
| 框架与模型版本 | `manifest.json` | 被评估对象变了 |

配方的 `compatible_metrics` 按指标名声明兼容的版本列表。服务在运行前校验三者兼容，不兼容直接拒绝，不允许"先跑再说"。

## 8. CI 集成

| 场景 | 触发 | 运行内容 |
|---|---|---|
| 配方改动 | 提交时 | 该配方的最小用例（S0），验证配方可执行 |
| 框架升级 | 每日 | 三个框架的适配用例 |
| 存储后端变更 | 变更时 | 受影响后端的对齐用例 |
| 回归 | 每周 | 全部 S0 + 抽样 S1，对比基线 |
| 探索 | 持续 | 新发现的模型与场景 |

CI 里只跑小规模，大规模运行走队列人工触发。CI 的结论也要回链，不允许"CI 里跑过但没留记录"。

## 9. 服务自身的观测

服务要能被观察，否则无法判断"评估结果变了"是系统变了还是服务坏了：

- 运行成功率、平均排队时长、平均执行时长；
- 每类失败的数量；
- 回链完整率；
- 观测开销（开启与关闭的指标差异）；
- 资源利用率。

## 10. 开放问题

- 分时复用单卡时，显存清理不彻底会导致后续 rank OOM，清理策略需要更严格的验证。
- 大规模运行的排队时长可能超过一天，是否需要预留资源池。
- 观测配置不同会导致结果不可比，是否强制固定观测配置。
- 服务版本升级时，历史结果是否需要重跑以保持可比。

