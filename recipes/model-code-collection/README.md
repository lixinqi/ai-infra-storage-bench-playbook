# 模型代码收集配方

本配方生产另外两个配方的原料：一份可复现、去重后、验证过能跑的 LLM 模型代码语料。

方法说明见 [`playbook/model-code-collection.md`](../../playbook/model-code-collection.md)。

## 目标

- 收集 1000 个以上可跑的推理模型代码，尽量配对训练代码。
- 语料可复现：给定清单与 commit，能在新机器上重建同样的文件集合。
- 覆盖度可度量：结构族、规模量级、注意力变体的覆盖矩阵可计算。

## 输入

| 输入 | 来源 | 必需 |
|---|---|---|
| 平台模型列表 | HuggingFace Hub 模型接口 | 是 |
| 机构模型清单 | 组织主页、内部模型清单 | 否 |
| 依赖镜像 | 按 `transformers` 主版本分组的镜像 | 是 |
| GPU 资源 | 可被分时占用的单卡 | 是 |

## 输出

| 产物 | 位置 | 说明 |
|---|---|---|
| 模型代码 | 对象存储 `models/<org>/<name>/<commit>/` | 只含代码与配置，不含权重 |
| 清单 | 对象存储 `manifests/model-code-<version>.json` | 结构见 `schemas/model-manifest.schema.json` |
| 覆盖度清单 | 对象存储 `coverage/model-code-<version>.json` | 结构见 `schemas/coverage.schema.json` |
| 回链 | 本目录 `recipe.yaml` 的 `latest_run` | 由评估服务写入 |

## 步骤

### 1. 抓取候选

调用平台模型列表接口，按 `pipeline_tag`、`library_name`、下载量与创建时间筛选，写入候选清单。每个候选记录 model id、组织、许可证、tags、创建时间。

截止条件：候选数量达到目标数量的 3 倍后停止抓取，进入下一步。多抓的部分用于补偿下载失败与去重淘汰。

### 2. 建立工作区

按 `transformers` 主版本把候选分组，每组一个工作区镜像。工作区里：

- 一套独立依赖；
- 固定的磁盘配额与清理规则；
- 一个下载器，按白名单取文件。

### 3. 下载代码与配置

白名单见 `playbook/model-code-collection.md` 的「只取代码与配置」。下载后：

- 计算每个文件的 sha256；
- 记录仓库的当前 commit；
- 校验文件数与清单一致；
- 失败按网络、权限、不存在、许可未接受四类分别记录。

### 4. 判定代码角色

对每个模型产出 `code_role`（`inference` / `pretrain` / `both` / `unknown`）与 `code_role_evidence`。判定顺序与证据等级见方法文档的「区分推理代码与预训练代码」。

证据不足时写 `unknown`，不要猜。`unknown` 计入覆盖缺口。

### 5. 结构指纹与去重

提取配置层与代码层特征，按架构族分组，组内计算加权距离，按最大边际覆盖保留代表样本。去重决定写进清单的 `dedup` 字段。

阈值初始值 0.15，标定前不对外引用去重率。

### 6. 可跑性验证

对每个保留样本：

1. 用固定 rank 数（默认 2）初始化 mock 的进程组。
2. 每个 rank 单独起进程，分时占用同一张卡。
3. 每个 rank 跑一次前向，输入维度用配置允许的小值。
4. 记录结果：`yes` / `no` / `partial`，以及失败步骤与错误摘要。
5. 超时统一设为 10 分钟，超时单独归类。

### 7. 训练代码配对

按方法文档的四条规则配对，产出 `paired_training.status`（`paired` / `external` / `unpaired`）与 `ref`。配对证据不足时一律 `unpaired`。

### 8. 覆盖度统计与验收

用 `checks/check_coverage.py` 计算覆盖矩阵与缺口清单，按 [`acceptance-checklist.md`](acceptance-checklist.md) 逐项确认。

## 验收

| 指标 | 口径 | 目标 |
|---|---|---|
| 可跑模型数 | `runnable=yes` 且 `dedup.decision=kept` | ≥ 1000 |
| 可跑率 | `runnable=yes` / 全部保留样本 | ≥ 85% |
| 架构族覆盖 | 至少 3 个样本的架构族数 | ≥ 20 |
| 规模覆盖 | 6 个量级分桶，每桶 ≥ 10 | 全部满足 |
| 注意力变体覆盖 | 6 类变体各 ≥ 5 | 全部满足 |
| 训练代码配对率 | `paired` + `external` 占比 | ≥ 40% |
| 语料可复现 | 重跑后文件集合与 sha256 完全一致 | 100% |

## 负责人

`owner` 字段见 [`recipe.yaml`](recipe.yaml)。语料版本升级前必须由负责人确认覆盖缺口清单。

## 开放问题

见 [`playbook/model-code-collection.md`](../../playbook/model-code-collection.md) 的「开放问题」。
