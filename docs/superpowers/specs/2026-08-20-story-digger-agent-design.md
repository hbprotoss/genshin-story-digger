# Story Digger Agent 设计文档

日期：2026-08-20

## 背景与目标

原神游戏内剧情文本分散在多类资料中（任务对白、圣遗物、武器、地图可交互文本、角色资料、书籍）。目标是：给定一个故事线名称，由一个 agent 从这些零散文本中尽量完整地整理出该故事线的中文 Markdown 文档（结构化梳理 + 原文出处）。

实现形态：Python + uv 项目，基于 claude-code-sdk 驱动 MiMo 模型（`mimo-v2.5-pro`，Anthropic 兼容端点 `https://api.xiaomimimo.com/anthropic`），交互式 CLI REPL。

## 数据现状

MongoDB `mihoyo` 库（配置见 `/root/.story-digger-agent/config.toml`）：

| 集合（原始） | 集合（精简） | 文档数 | 说明 |
|---|---|---|---|
| mission | mission_filtered | 986 | 任务对白 |
| book | book_filtered | 90 | 书籍 |
| artifact | artifact_filtered | 61 | 圣遗物 |
| weapon | weapon_filtered | 234 | 武器 |
| map_text | map_text_filtered | 653 | 地图可交互文本 |
| character | character_filtered | 130 | 角色资料 |

- `_filtered` 集合字段：`id`、`name`、`text`（清洗后正文，另有 `mission` 数组字段，普遍为空）
- 原始集合带元数据（版本号、地区、类型筛选等，主要在 `ext.fe_ext` 字段）
- 中文 `$regex` 包含匹配检索 <0.1s，无需全文索引
- kg 开头的知识图谱集合不使用
- 认证注意：`MongoClient` 不在 URI 中指定目标库（认证默认走 `admin`），再按名称取 `mihoyo` 库；或在 URI 加 `authSource=admin`，二选一

## 总体架构

```
用户（REPL） ──输入故事线关键词──▶ story-digger 主程序（Python, asyncio）
                                        │
                                        │  claude-code-sdk (query, stream)
                                        ▼
                                 ┌─ 主 Agent（MiMo）─────────────┐
                                 │ 1. 关键词澄清：调 MCP 工具检索  │
                                 │    name 字段，列出候选故事线，   │
                                 │    等用户选择确认               │
                                 │ 2. 规划：拆分子课题             │
                                 │ 3. 并行派发 Task sub agent      │
                                 │    （每个子课题一个）            │
                                 │ 4. 汇总各 sub agent 产出        │
                                 │ 5. 综合成带出处的 Markdown      │
                                 └───────┬───────────────────────┘
                                         │ MCP (stdio)
                                         ▼
                                 Mongo MCP Server（FastMCP + pymongo）
                                   search_texts / get_text / get_meta / stats
                                         │
                                         ▼
                                   MongoDB (mihoyo)
```

流程：

1. **关键词澄清阶段**：主 agent 拿到用户输入后，先用 `search_texts` 对六类集合的 `name` 字段做包含匹配，同时抽几条命中正文看语境，生成候选列表（如输入"渊下" -> 候选：渊下宫·白夜国剧情线 / 常世国 / 龙骨血睦…），以编号列表输出给用户选择。用户可多选、可自己补充描述。此阶段由主 agent 在对话中完成，不进 sub agent（需要与用户来回确认）。
2. **规划阶段**：用户确认后，主 agent 先读 3-5 篇核心文本建立框架，产出故事线大纲（章节/子课题划分），展示给用户后派发。
3. **并行挖掘**：主 agent 用 Claude Code 内置 Task 工具一次性并行派发多个 sub agent，每个负责一个子课题，各自独立滚雪球检索（提炼关键词 -> 检索 -> 读原文 -> 再扩展）。Task 工具天然继承 MCP 工具且可多个并行。
4. **汇总撰写**：sub agent 返回结构化产出（摘录 + 出处 + 覆盖说明），主 agent 去重合并、补漏（发现遗漏可再派一轮），按大纲写成最终文档，保存 `.md`。
5. **迭代**：用户在 REPL 里继续追问/补充，agent 可再派 sub agent 补挖，更新文档。

## 目录结构

```
/opt/src/story-digger-agent/
├── pyproject.toml          # claude-agent-sdk, mcp(fastmcp), pymongo, tomli
├── src/
│   ├── __main__.py         # REPL 入口
│   ├── config.py           # 读 config.toml -> SDK env + mongo 连接
│   ├── mcp_server.py       # Mongo MCP server
│   └── prompts.py          # 主 agent / sub agent 的 system prompt
└── tests/
```

## MCP 工具设计

FastMCP（stdio），随主程序以子进程方式由 SDK 拉起（`mcpServers` 配置指向 `src/mcp_server.py`，连接串等参数经启动参数传入，不在 MCP 进程里重复读配置）。所有 agent（主 + sub）共用：

### `search_texts(keywords: list[str], collections: list[str] | None, limit: int = 20)`

- 对指定集合（默认全部六类 `_filtered`）的 `name` 和 `text` 做关键词包含匹配（`$regex`，多关键词 OR）
- 返回 `{collection, id, name, 命中关键词列表, text 总字数, 命中处上下文片段（每关键词约 100 字）}`，按命中关键词数排序，截断到 `limit`
- 滚雪球检索的主力工具，返回摘要让 agent 决定哪些值得读全文

### `get_text(collection: str, id: str, offset: int = 0, length: int = 8000)`

- 取单个文档全文，超长分页（书籍/任务对白可能上万字，避免撑爆上下文）
- 返回带总长度标记，agent 可续读

### `get_meta(collection: str, id: str)`

- 到对应的原始集合查该 id 的元数据：版本号、地区、类型筛选（`ext.fe_ext`），用于标注"此任务为 5.5 版本纳塔地区世界任务"类信息

### `stats()`

- 各集合文档数，供 agent 起步时了解数据全貌

工具刻意保持少而正交：检索、取文、查元数据、看统计。MCP server 内部维护 pymongo 连接池，正则全部走服务端 `$regex`。对 MongoDB 纯只读。

## Agent 编排与提示词

### 主 agent system prompt 核心约束

1. **澄清优先**：收到故事线关键词后禁止直接开挖。必须先 `search_texts` 查 name 字段 + 抽样正文，输出编号候选列表（含每个候选的一句话说明和出处集合），明确问用户"选哪个/多选/补充描述"。用户确认前不派 sub agent。
2. **规划**：确认后先读 3-5 篇核心文本建立框架，产出大纲（章节划分 + 每章要回答的问题），展示给用户后派发。
3. **并行派发**：用 Task 工具一次性并行派发所有子课题的 sub agent（而非串行），每个 sub agent 的任务书包含：子课题说明、已知的种子关键词/实体别名、产出格式要求。派发数量不超过配置的 `max_subagents`（默认 5）。
4. **汇总去重撰写**：sub agent 产出统一格式（`## 章节内容 + [出处: 集合·名称 (collection:id)]` + 覆盖说明：检索过哪些关键词、哪些集合无命中）。主 agent 合并去重、补漏（发现遗漏可再派一轮），写成最终文档。
5. **写文件**：最终文档用 Write 工具保存到输出目录。

### sub agent 提示词要点

- 只负责自己那一章
- 滚雪球纪律：每读一篇提炼新关键词再检索，直到连续 2 轮检索无新增命中才可收尾
- 原文摘录必须逐字保留并带出处
- 明确"没找到"也是有效结论

### 产出文档结构（模板，agent 可灵活）

```markdown
# <故事线名称>
> 涉及版本/地区概览、一句话概述
## 概述
## 第一章 <主题>
<梳理后的叙事，关键处引用原文>
[出处: 任务·xxx (mission_filtered:50123)]
## 人物/势力表
## 时间线（如可考）
## 资料来源清单
- 集合·名称 (collection:id) - 一句话说明贡献了什么
## 检索覆盖说明
<检索过的关键词、各集合命中情况、已知可能的遗漏>
```

"检索覆盖说明"一节是完整性的自检，也方便用户判断要不要让 agent 再挖。

## 主程序 REPL

- asyncio 事件循环：读用户输入 -> `claude_agent_sdk.query()`（system prompt + MCP 配置）-> 流式打印 agent 回复（含工具调用进度显示，如 `⟐ search_texts(["渊下宫"]) …`）
- 一次会话一个 conversation（SDK session 模式，`--resume` 保持上下文），用户随时可打断（Ctrl+C 中断当前轮，不退出）
- 每轮结束提示可继续追问；`exit`/`quit` 退出

## 配置

`/root/.story-digger-agent/config.toml`：

```toml
[mongo]
host = "localhost"
port = 27017
database = "mihoyo"
username = "..."
password = "..."
# auth_source 可选，默认 admin（实现时二选一：URI 加 authSource 或
# MongoClient 不在 URI 指定目标库、按名称取库）

[chat]
stream = true
base_url = "https://api.xiaomimimo.com/anthropic"   # 改为 Anthropic 兼容端点
api_key = "..."
model = "mimo-v2.5-pro"
temperature = 0.2
debug_llm = true

[agent]
output_dir = "./output/"
max_subagents = 5
```

`[chat]` 到 SDK 的映射：

| 配置项 | SDK 映射 |
|---|---|
| `base_url` | `ANTHROPIC_BASE_URL` 环境变量 |
| `api_key` | `ANTHROPIC_AUTH_TOKEN` |
| `model` | query 的 `model` 参数 |
| `temperature` | query 的 `temperature` 参数 |

`stream`/`debug_llm` 保留：`debug_llm` 控制是否打印请求调试日志。

## 错误处理

- **LLM API 失败**：SDK 自带重试；连续失败则该轮终止，向用户报告错误，会话保留可重试
- **Mongo 连接失败**：MCP server 启动时连一次验证，失败则整体拒绝启动并明确报错
- **sub agent 失败/超时**：主 agent 提示词约定--某子课题 sub agent 失败时重试一次，仍失败则在"检索覆盖说明"里如实标注未完成，不静默吞掉
- **长文本保护**：`get_text` 分页（默认 8000 字/页），prompt 明确要求不要一次性反复拉全文
- **用户打断**：优雅终止当前 agent 轮次，回到输入提示符

## 测试

- **单元测试**（pytest，直连真实 Mongo，数据只读）：
  - `search_texts`：已知关键词（如"坎瑞亚"）命中预期文档；多关键词 OR；limit 截断
  - `get_text`：分页正确性、超长文档
  - `get_meta`：能取出原始集合的版本/地区元数据
  - `config.py`：配置解析与 SDK 环境映射
- **集成冒烟**：脚本方式跑一个固定小故事线（限定不派 sub agent 或限一轮），验证端到端能产出 `.md` 文件--标记为手动/可选，因为依赖 MiMo API 质量
- 检索质量（召回率）靠"检索覆盖说明"一节人工审阅，不做自动化断言

## 不做的事（YAGNI）

- 不做向量检索/嵌入（正则已够快，集合规模小）
- 不做 Web UI / API 服务，只有 CLI REPL
- 不做文档增量更新缓存，每次重新生成
- 不改 Mongo 里的数据（纯只读）
- 不使用 kg 知识图谱集合
