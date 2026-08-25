# 🏗️ Story Digger Agent — 架构文档

> 本文档描述 story-digger-agent 的系统架构、组件设计、数据流和关键设计决策。

---

## 概览

story-digger-agent 是一个基于 Claude Code SDK 驱动的交互式 CLI agent，从 MongoDB 中的原神六类游戏文本里挖掘指定故事线，生成带原文出处的中文 Markdown 文档。

核心思路：**主 Agent 负责规划调度，Sub Agent 负责并行深耕，MCP Server 提供只读数据检索**。

---

## 架构图

```
                          ┌──────────────────────┐
                          │      用户 (终端)       │
                          │   prompt_toolkit REPL │
                          └──────────┬───────────┘
                                     │ 输入故事线关键词
                                     │ 流式输出 agent 回复
                                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         repl.py (主程序)                              │
│                                                                     │
│  • asyncio 事件循环                                                  │
│  • config.py 载入配置 → ClaudeAgentOptions                           │
│  • prompts.py 组装 system prompt                                     │
│  • claude_agent_sdk.query() + session resume 实现多轮对话             │
│  • 流式打印 agent 回复 + 工具调用摘要                                 │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               │ claude_agent_sdk (HTTP/SSE)
                               │ ANTHROPIC_BASE_URL + AUTH_TOKEN
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      MiMo 模型 (mimo-v2.5-pro)                       │
│                  Anthropic 兼容端点 (api.xiaomimimo.com)              │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                      主 Agent                                  │  │
│  │                                                               │  │
│  │  ① 关键词澄清：search_texts → 候选列表 → 等待用户选择           │  │
│  │  ② 规划大纲：读 3-5 篇核心文本 → 章节划分 + 每章核心问题       │  │
│  │  ③ 并行派发：Task × N（每个章节一个 Sub Agent）                │  │
│  │  ④ 汇总去重：合并产出、发现遗漏补挖 → Write 保存 Markdown      │  │
│  └──────────┬────────────────────────────────────────────────────┘  │
│             │                                                       │
│             │  Task 工具 (claude_agent_sdk 内置)                    │
│             │  并行派发，继承 MCP 工具                               │
│             ▼                                                       │
│  ┌─────────────────────┐  ┌─────────────────────┐                   │
│  │  Sub Agent (章节 1)  │  │  Sub Agent (章节 2)  │  ... (最多 N 个) │
│  │                     │  │                     │                   │
│  │ 滚雪球检索：         │  │ 滚雪球检索：         │                   │
│  │ search_texts        │  │ search_texts        │                   │
│  │   → get_text (分页)  │  │   → get_text (分页)  │                   │
│  │   → 提炼新关键词     │  │   → 提炼新关键词     │                   │
│  │   → 再检索           │  │   → 再检索           │                   │
│  │   → 直到无新增命中   │  │   → 直到无新增命中   │                   │
│  │                     │  │                     │                   │
│  │ 产出：章节内容        │  │ 产出：章节内容        │                   │
│  │ + 出处标注            │  │ + 出处标注            │                   │
│  │ + 覆盖说明            │  │ + 覆盖说明            │                   │
│  └──────────┬──────────┘  └──────────┬──────────┘                   │
└─────────────┼────────────────────────┼──────────────────────────────┘
              │                        │
              │  MCP (stdio)           │  MCP (stdio)
              │  共享同一 server 进程   │
              ▼                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   mcp_server.py (FastMCP, stdio)                     │
│                                                                     │
│  ┌──────────────┬──────────────────┬──────────────┬──────────────┐  │
│  │  stats()     │  search_texts()  │  get_text()  │  get_meta()  │  │
│  │  文档统计     │  关键词检索       │  分页取正文   │  元数据查询   │  │
│  └──────────────┴──────────────────┴──────────────┴──────────────┘  │
│                                                                     │
│  连接参数经 argv 传入 (--uri / --database)，不读配置文件              │
│  启动时 ping 验证连接，失败则拒绝启动                                 │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               │  pymongo (连接池, 只读)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        MongoDB (mihoyo)                              │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  _filtered 集合 (正文检索)                                     │   │
│  │  • mission_filtered    (986)  任务对白                         │   │
│  │  • book_filtered       (90)   书籍                            │   │
│  │  • artifact_filtered   (61)   圣遗物                          │   │
│  │  • weapon_filtered     (234)  武器                            │   │
│  │  • map_text_filtered   (653)  地图可交互文本                   │   │
│  │  • character_filtered  (130)  角色资料                        │   │
│  │  字段: id, name, text                                          │   │
│  ├──────────────────────────────────────────────────────────────┤   │
│  │  原始集合 (元数据查询)                                          │   │
│  │  • mission / book / artifact / weapon / map_text / character  │   │
│  │  字段: id, name, version, ext.fe_ext, filter_values, ...      │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 组件详解

### 1. `repl.py` — 主程序与 REPL

**职责**：交互式入口，连接用户输入与 Agent 运行时。

```
┌─ 启动 ──────────────────────────────────────────────────────────┐
│ 1. 解析命令行参数 (--config)                                     │
│ 2. load_config() 载入配置                                        │
│ 3. output_dir 转绝对路径、mkdir                                   │
│ 4. 注入 ANTHROPIC_BASE_URL / AUTH_TOKEN 到 os.environ            │
│ 5. build_options() 组装 ClaudeAgentOptions                       │
│ 6. 启动 prompt_toolkit PromptSession (async)                     │
└────────────────────────────────────────────────────────────────┘
┌─ 每轮对话 ──────────────────────────────────────────────────────┐
│ 1. 读取用户输入 (prompt_toolkit, 中文 IME 兼容)                   │
│ 2. claude_agent_sdk.query(prompt, options, resume=session_id)     │
│ 3. 流式迭代 async for msg in query(...)                          │
│ 4. format_message() 提取 TextBlock + ToolUseBlock 摘要并打印      │
│ 5. 记录 session_id 供下一轮 resume                               │
│ 6. Ctrl+C → 打断本轮 (asyncio.CancelledError)                    │
│ 7. API 异常 → 打印错误，保留会话，可重试                           │
└────────────────────────────────────────────────────────────────┘
```

**关键设计决策**：

- 使用 `query()` 一次性调用而非 `ClaudeSDKClient` 长连接——该端点下长连接多轮交互不稳定，`query()` + `resume` 经实测可靠
- `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` 直接注入 `os.environ` 而非仅靠 `opts.env`——SDK 子进程继承父进程环境变量，`opts.env` 合并逻辑在此端点下不可靠
- 使用 `prompt_toolkit` 而非 `input()`——解决中文输入时光标删除错乱问题
- 工具白名单 (`allowed_tools`) 而非 `bypassPermissions`——root 下 CLI 硬性拒绝 `--dangerously-skip-permissions`

### 2. `config.py` — 配置系统

**职责**：解析 TOML 配置文件，映射为运行时对象。

```
AppConfig
├── MongoConfig
│   ├── host, port, database, username, password, auth_source
│   └── uri() → "mongodb://user:pass@host:port/?authSource=admin"
├── ChatConfig
│   ├── base_url, api_key, model
│   ├── stream, debug_llm
│   └── temperature (保留字段，当前实现忽略)
└── AgentConfig
    ├── output_dir (默认 ./output/)
    └── max_subagents (默认 5)
```

**配置映射**：

| 配置项 | 运行时映射 |
|--------|-----------|
| `chat.base_url` | `ANTHROPIC_BASE_URL` 环境变量 |
| `chat.api_key` | `ANTHROPIC_AUTH_TOKEN` 环境变量 |
| `chat.model` | `ClaudeAgentOptions.model` |
| `agent.output_dir` | system prompt 中的 `{output_dir}` 占位符 |
| `agent.max_subagents` | system prompt 中的 `{max_subagents}` 占位符 |

### 3. `prompts.py` — 提示词系统

**职责**：定义主 Agent 和 Sub Agent 的行为约束。

**组装机制**：

```
SUBAGENT_TASK_TEMPLATE          _MAIN_PROMPT_TEMPLATE
(含 {topic}, {chapter_title},    (含 {subagent_task}, {max_subagents},
 {seed_keywords} 占位符)          {output_dir} 占位符)
           │                              │
           │  str.replace()               │
           └──────────┬───────────────────┘
                      ▼
              MAIN_SYSTEM_PROMPT
              (只剩 {max_subagents} / {output_dir} 两个占位符)
                      │
                      │  repl.py 用 str.replace() 注入
                      ▼
              最终 system prompt
```

> 为什么用 `str.replace` 而非 `str.format`？  
> 因为 `SUBAGENT_TASK_TEMPLATE` 中含 `{topic}` 等占位符，若用 `.format()` 会因缺少对应参数而抛 `KeyError`。

**主 Agent 提示词核心约束**：

| 阶段 | 约束 |
|------|------|
| 澄清 | 禁止直接开挖，必须先用 `search_texts` 检索 name 字段、输出编号候选列表、等待用户选择 |
| 规划 | 确认后读 3-5 篇核心文本建立框架，产出大纲展示给用户 |
| 派发 | 用 Task 工具一次性并行派发所有章节，不串行 |
| 汇总 | 合并去重、发现遗漏补挖、写出文档 |
| 纪律 | 原文逐字保留、出处精确到 `(collection:id)`、失败透明标注 |

**Sub Agent 提示词核心约束**：

| 规则 | 说明 |
|------|------|
| 职责边界 | 只做自己的章节，不越界 |
| 滚雪球纪律 | 检索 → 读原文 → 提炼新关键词 → 再检索，直到连续 2 轮无新增命中 |
| 全集合覆盖 | 每轮检索覆盖全部六类集合 |
| 产出格式 | `## 章节标题` + 叙事 + `[出处: ...]` + 覆盖说明 |
| 诚实透明 | "没找到"也是有效结论 |

### 4. `mcp_server.py` — MCP Server

**职责**：对 MongoDB 提供只读检索接口，以 stdio 子进程方式由 SDK 拉起。

**4 个工具，少而正交**：

| 工具 | 用途 | 关键特性 |
|------|------|----------|
| `stats()` | 各集合文档数一览 | 了解数据全貌 |
| `search_texts(keywords, collections?, limit?)` | 跨集合关键词检索 | 滚雪球主力；`$regex` 匹配 name+text；多关键词 OR；返回上下文片段；按命中关键词数排序；每集合封顶 `limit*3` 候选 |
| `get_text(collection, id, offset?, length?)` | 分页取全文 | 默认 8000 字/页；含 `has_more` 标记；支持 offset 续读 |
| `get_meta(collection, id)` | 元数据查询 | 到原始集合（去 `_filtered` 后缀）查版本/地区/类型；`fe_ext` JSON 字符串自动解析 |

**安全设计**：

- 纯只读——所有工具不写库
- `$regex` 参数经 `re.escape()` 防注入
- 连接参数经 argv 传入，不读配置文件
- 启动时 `ping` 验证，失败则拒绝启动（fast-fail）

**连接管理**：模块级全局 `_client` / `_db`，`init_client()` 初始化，`db()` 取用。pymongo 自带连接池。

---

## 数据流

### 一次完整的故事线挖掘流程

```
时间线 →

用户输入          主 Agent                            Sub Agent(s)              MCP Server          MongoDB
  │                │                                     │                        │                  │
  │ "渊下"         │                                     │                        │                  │
  │───────────────▶│                                     │                        │                  │
  │                │──── search_texts(["渊下"]) ─────────────────────────────────▶│                  │
  │                │◀────────────────────────────────────────────────────────────│                  │
  │                │                                     │                        │                  │
  │                │──── get_text (抽读 2-3 条) ─────────────────────────────────▶│                  │
  │                │◀────────────────────────────────────────────────────────────│                  │
  │                │                                     │                        │                  │
  │  候选列表       │                                     │                        │                  │
  │◀───────────────│                                     │                        │                  │
  │                │                                     │                        │                  │
  │ "1 + 海祇岛"   │                                     │                        │                  │
  │───────────────▶│                                     │                        │                  │
  │                │──── get_text (读 3-5 篇核心) ──────────────────────────────▶│                  │
  │                │◀────────────────────────────────────────────────────────────│                  │
  │                │                                     │                        │                  │
  │  大纲          │                                     │                        │                  │
  │◀───────────────│                                     │                        │                  │
  │                │                                     │                        │                  │
  │                │── Task("白夜国建立") ───────────────▶│                        │                  │
  │                │── Task("海祇岛崛起") ───────────────▶│                        │                  │
  │                │── Task("深海龙蜥")  ────────────────▶│                        │                  │
  │                │                                     │                        │                  │
  │                │                                     │── search_texts ───────▶│                  │
  │                │                                     │◀── 命中摘要 ───────────│                  │
  │                │                                     │── get_text (分页) ────▶│                  │
  │                │                                     │◀── 全文 ───────────────│                  │
  │                │                                     │  (提炼新关键词, 再检索)  │                  │
  │                │                                     │  ... (循环直到无新增)   │                  │
  │                │                                     │                        │                  │
  │                │◀── 章节 1 产出 ─────────────────────│                        │                  │
  │                │◀── 章节 2 产出 ─────────────────────│                        │                  │
  │                │◀── 章节 3 产出 ─────────────────────│                        │                  │
  │                │                                     │                        │                  │
  │                │ 合并去重 + 补漏 (可能再派一轮)         │                        │                  │
  │                │                                     │                        │                  │
  │                │──── Write(output/渊下宫.md) ───────────────────────────────────────────────▶ 📄
  │                │                                     │                        │                  │
  │  完成          │                                     │                        │                  │
  │◀───────────────│                                     │                        │                  │
```

---

## 错误处理策略

| 场景 | 处理方式 |
|------|----------|
| MongoDB 连接失败 | MCP server 启动时 ping 验证，失败则拒绝启动，明确报错 |
| LLM API 失败 | SDK 自带重试；连续失败则该轮终止，打印错误，会话保留可重试 |
| Sub Agent 失败 | 主 Agent 提示词约定：重试一次，仍失败则在"检索覆盖说明"中标注 |
| 用户打断 (Ctrl+C) | 优雅终止当前轮 (asyncio.CancelledError)，回到输入提示符，会话不丢失 |
| 长文本 | `get_text` 分页（默认 8000 字/页），提示词禁止反复从头拉取 |
| 空关键词搜索 | `search_texts` 返回 `{"error": "keywords 不能为空"}` |
| 未知集合 | `search_texts` / `get_text` / `get_meta` 返回 `{"error": "未知集合: ..."}` |

---

## 关键设计决策

### 1. 为什么用 MCP 而非直连 MongoDB？

- **安全隔离**：MCP server 以子进程运行，纯只读，Agent 无法直接操作数据库
- **工具语义化**：4 个工具覆盖检索、取文、查元数据、看统计，Agent 调用更自然
- **复用**：主 Agent 和所有 Sub Agent 共享同一 MCP server，无需各自维护连接

### 2. 为什么用 `query()` 而非长连接？

该 Anthropic 兼容端点下 `ClaudeSDKClient` 的 connect/query 多轮交互不稳定，`query()` + `resume` session 路径经实测可靠。

### 3. 为什么不做向量检索？

- 数据集规模小（~2154 篇文档）
- 中文 `$regex` 包含匹配 < 0.1s
- 关键词精确匹配更利于滚雪球策略（能精确判断"无新增命中"）

### 4. 为什么输出目录要 `resolve()` 转绝对路径？

Agent 的 Write 工具工作目录可能与启动目录不同，相对路径会导致文档写到意料之外的位置。启动时 `resolve()` 转绝对路径并 `mkdir` 确保可写。

### 5. 为什么输出文档要求"检索覆盖说明"？

这是完整性的自检机制——让读者知道哪些方向搜过了、哪些没找到资料，方便判断要不要让 Agent 再挖。也是对抗 LLM 幻觉的一种手段。

---

## 目录结构

```
src/
├── __main__.py         # 入口：from repl import main
├── config.py           # 配置解析：MongoConfig, ChatConfig, AgentConfig, AppConfig
├── mcp_server.py       # MCP Server：stats, search_texts, get_text, get_meta
├── prompts.py          # 提示词：MAIN_SYSTEM_PROMPT, SUBAGENT_TASK_TEMPLATE
└── repl.py             # REPL：build_options, format_message, run_repl

tests/
├── conftest.py         # 共享 fixtures（MongoDB 连不上则 skip）
├── fixtures/
│   └── config.toml     # 测试用配置
├── test_config.py      # 配置解析 + SDK env 映射
├── test_mcp_stats.py   # stats 工具
├── test_mcp_search.py  # search_texts 工具（5 个测试）
├── test_mcp_get_text.py # get_text 分页测试
├── test_mcp_get_meta.py # get_meta 元数据测试
├── test_prompts.py     # 提示词模板验证
└── test_repl.py        # build_options + format_message 单元测试
```

---

## 相关文档

- [设计规格](superpowers/specs/2026-08-20-story-digger-agent-design.md)
- [实施计划](superpowers/plans/2026-08-20-story-digger-agent.md)