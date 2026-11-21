# research-pipeline

> 一个可以 `pip install`、脱离 WorkBuddy 独立运行的命令行工具：arXiv 检索 → Zotero 去重导入 → 按 11 节模板生成 Obsidian 笔记。
> **零强制依赖**——全部基于 Python 标准库，任何 Python 3.8+ 环境都能跑。

## 它解决什么问题

一条命令跑通科研论文流水线：**arXiv 检索 → Zotero 去重导入 → 按 11 节模板生成 Obsidian 笔记**。

- 数据源是 [Zotero](https://www.zotero.org/)（通过 [Zotero MCP Plugin](https://github.com/cookjohn/zotero-mcp) 的本地 Streamable HTTP 接口读写）
- 产物是 Obsidian 库里的结构化 Markdown 笔记
- 需要语义提炼时（如"从摘要里总结创新点/局限"），由你或外部 AI 填好 JSON 后交给 `notes` 命令渲染；程序本身是确定性的，不做语义理解

## 安装

```bash
# 方式 A：开发模式安装（推荐，改代码即时生效）
python -m pip install -e .

# 方式 B：普通安装
python -m pip install .

# 方式 C：不安装，直接跑（需设 PYTHONPATH）
PYTHONPATH=src python -m research_pipeline --help
```

安装后有两个命令：`research-pipeline` 和简写 `rp`。

## 快速开始

```bash
# 0. 环境自检（会尝试连 Zotero MCP）
rp doctor

# 1. 生成配置示例，然后按注释改成你的路径
rp init research-pipeline.json

# 2. 检索 arXiv（不需要 Zotero）
rp search 'all:"small object detection"' --max 5 --out candidates.json

# 3. 导入标识符到 Zotero 分类（需 Zotero 运行中）
rp import arXiv:2401.01234 arXiv:2402.05678 --collection "小目标检测"

# 4. 从论文 JSON 生成 Obsidian 笔记
rp notes candidates.json --out "D:/MyVault/精读笔记" --overwrite

# 5. 一条命令跑完整流水线
rp run --query 'all:"infrared object detection"' \
       --collection "红外目标检测" --max 5

# 5b. 多主题：按子目录分门别类
rp run --topics topics.json --collection "目标检测" --max 5
```

`topics.json` 示例（每个键会成为 Obsidian 里的子目录名）：

```json
{
  "红外目标检测": ["all:\"infrared object detection\""],
  "三维点云目标检测": ["all:\"3D object detection\" AND all:\"point cloud\""],
  "小目标检测": ["all:\"small object detection\""]
}
```

## 配置

按优先级从高到低：

1. 命令行 `--config` 指定的文件
2. 当前目录的 `research-pipeline.json`
3. 用户目录的 `~/.research-pipeline.json`
4. 环境变量 `ZOTERO_MCP_URL` / `OBSIDIAN_VAULT` / `NOTE_OUTPUT_DIR` / `DEFAULT_COLLECTION`
5. 内置默认值

```json
{
  "zotero_mcp_url": "http://127.0.0.1:23120/mcp",
  "obsidian_vault": "D:/MyVault",
  "template_path": "D:/MyVault/Templates/论文精读模板.md",
  "note_output_dir": "D:/MyVault/精读笔记",
  "default_collection": "目标检测",
  "save_attachments": false,
  "batch_size": 3,
  "request_timeout": 60
}
```

> `save_attachments` 默认关闭：抓 OA PDF 受网络影响可能卡住，先确保题录入库更稳妥。
> `batch_size` 默认 3：超过 3 篇 Zotero 会转后台任务，故分批同步导入。

## 命令一览

| 命令 | 作用 | 依赖 Zotero？ |
|---|---|---|
| `doctor` | 检查 Python、配置、Zotero 连接与可用工具 | 是 |
| `init [路径]` | 生成配置示例文件 | 否 |
| `search <检索式>` | 检索 arXiv，输出/保存结构化 JSON | 否 |
| `import <标识符...>` | 按 arXiv ID/DOI 导入 Zotero 分类，自动去重 | 是 |
| `notes <JSON>` | 从论文数据生成 11 节 Obsidian 笔记 | 否 |
| `run` | 端到端：检索 → 导入 → 笔记 | 是 |

通用选项：`--config` 指定配置、`-v` 详细日志；各子命令用 `rp <命令> --help` 看完整参数。

## 前置条件

- Python 3.8+（仅标准库，无需 pip 装第三方包）
- 用 Zotero 相关功能时：Zotero 正在运行，且 Zotero MCP Plugin 已启用服务器（默认端口 23120）、需要写入时勾选「启用写入操作」
- `search` / `notes` 命令不需要 Zotero

## 包结构

```
research-pipeline/
├── pyproject.toml              # 包元数据、CLI 入口、零依赖声明
├── README.md                   # 本文件
├── research-pipeline.example.json  # 配置示例
├── examples/
│   └── 论文精读模板.md         # 11 节模板示例（可自定义后传给 --template）
├── src/research_pipeline/
│   ├── __init__.py             # 版本信息
│   ├── __main__.py             # python -m research_pipeline 入口
│   ├── cli.py                  # 命令行解析与子命令
│   ├── config.py               # 配置加载（文件 + 环境变量）
│   ├── models.py               # Paper / Collection / ImportResult 数据模型
│   ├── logger.py               # 日志
│   ├── zotero.py               # Zotero MCP 客户端（会话/SSE/工具封装）
│   ├── arxiv.py                # arXiv 检索与 Atom XML 解析
│   ├── notes.py                # 11 节模板渲染与写盘
│   └── pipeline.py             # 三步流水线编排
└── tests/
    └── test_pipeline.py        # 13 个单元测试（unittest，mock 网络）
```

## 测试

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
# Ran 13 tests ... OK
```

测试覆盖：Atom XML 解析（含 HTML 实体、空白规范化）、笔记渲染与占位符替换、文件名清理、覆盖/跳过逻辑、配置校验与环境变量覆盖、分类 key 提取、分批导入统计、CLI 的 init/notes 命令。

## 设计说明

- **零依赖**：Atom XML 解析、MCP Streamable HTTP 客户端、模板渲染全部用标准库实现，任何 Python 3.8+ 环境开箱即用。
- **确定性**：程序本身不做语义理解。笔记里的"创新点/局限性/研究问题"等字段需要你（或外部 AI）填进论文 JSON；`search` 命令输出的候选 JSON 已留好这些字段，可直接补全后交给 `notes`。
- **可组合**：`search` / `import` / `notes` 可单独使用，也可 `run` 一次跑完；`--topics` 支持一次检索多个子方向并按子目录归档。

## License

MIT
