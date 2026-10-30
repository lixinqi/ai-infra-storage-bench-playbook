# 最小模型样例

这个目录演示"语料里的一条记录长什么样"。它不是评估目标，只用于：

- 演示清单条目的字段；
- 让 `checks/` 的脚本有一个可以跑通的最小输入；
- 让新同学在五分钟内看懂收集与验证流程。

## 文件

| 文件 | 说明 |
|---|---|
| `config.json` | 一个极小模型的配置 |
| `modeling_tiny.py` | 对应的建模代码，能在 meta device 上跑一次前向 |
| `manifest-entry.json` | 与 `schemas/model-manifest.schema.json` 一致的清单条目 |

## 核对方法

```text
python3 -m json.tool examples/tiny-model/config.json
python3 -c "import json; json.load(open('examples/tiny-model/manifest-entry.json'))"
```

`modeling_tiny.py` 需要 PyTorch；没有安装时跳过运行，不要把它写进任何结论。
