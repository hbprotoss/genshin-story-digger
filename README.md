# 🏔️ Story Digger Agent

> 给定一个故事线名称，自动从原神六类游戏文本中挖掘、整理出带原文出处的结构化中文 Markdown 文档。

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://www.python.org/)
[![uv](https://img.shields.io/badge/uv-package%20manager-blueviolet.svg)](https://docs.astral.sh/uv/)
[![License](https://img.shields.io/badge/license-GPLv3-green.svg)](LICENSE)

---

## ✨ 功能特色

- **🔍 智能澄清** — 输入模糊关键词（如"渊下""坎瑞亚"），主 Agent 先检索候选故事线并列出编号，等你确认后再开挖，绝不瞎猜
- **🧠 自动规划** — 确认故事线后，Agent 先读核心文本建立框架，自动产出章节大纲，展示后再派发
- **⚡ 并行挖掘** — 主 Agent 一次性并行派发多个 Sub Agent，各自负责一个章节，用「滚雪球」策略独立检索
- **❄️ 滚雪球检索** — Sub Agent 从种子关键词出发，读原文 → 提炼新实体名/别名/事件/地名 → 再检索 → 循环直到连续两轮无新增命中
- **📚 六类文本全覆盖** — 任务对白、书籍、圣遗物、武器、地图可交互文本、角色资料，一个不落
- **📎 原文出处精确标注** — 关键情节逐字引用原文，格式 `[出处: 集合·名称 (collection:id)]`，可溯源验证
- **🪟 覆盖透明化** — 产出文档含「检索覆盖说明」章节，列出所有检索过的关键词、各集合命中数、已知遗漏，诚实透明
- **💬 交互式 REPL** — 多轮对话，随时追问补充，会话状态持久保留

---

## 🏗️ 架构速览

```
你 (REPL)
  │  "渊下"
  ▼
┌─────────────────────────────────────────┐
│          主 Agent (MiMo)                 │
│                                          │
│  ① 关键词澄清：search_texts → 候选列表    │
│  ② 规划大纲：读核心文本 → 章节划分       │
│  ③ 并行派发：Task × N（每个章节一个）     │
│  ④ 汇总去重 → 写 Markdown                │
└──────────────┬──────────────────────────┘
               │ MCP (stdio)
               ▼
┌─────────────────────────────────────────┐
│     Mongo MCP Server (FastMCP)          │
│  stats | search_texts | get_text | get_meta │
└──────────────┬──────────────────────────┘
               │ pymongo (只读)
               ▼
┌─────────────────────────────────────────┐
│          MongoDB (mihoyo)                │
│  mission / book / artifact / weapon     │
│  map_text / character (共 ~2154 篇)      │
└─────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 前置条件

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) 包管理器
- 可达的 MongoDB 实例
- 原神文本数据 —— 见下方[准备文本数据](#2-准备文本数据)
- MiMo 模型 API Key（或其他 Anthropic 兼容端点）

### 1. 克隆 & 安装

```bash
git clone git@github.com:hbprotoss/genshin-story-digger.git
cd genshin-story-digger
uv sync
```

### 2. 准备文本数据

本项目**只负责挖掘**，不含游戏文本数据。文本数据请从配套仓库获取并导入 MongoDB：

**👉 [hbprotoss/genshin-story-data](https://github.com/hbprotoss/genshin-story-data)**

导入后，目标数据库（默认 `mihoyo`）应包含以下集合：

| 集合 | 用途 | 必需字段 |
|------|------|----------|
| `mission_filtered` | 任务对白正文 | `id`, `name`, `text` |
| `book_filtered` | 书籍正文 | `id`, `name`, `text` |
| `artifact_filtered` | 圣遗物文本 | `id`, `name`, `text` |
| `weapon_filtered` | 武器文本 | `id`, `name`, `text` |
| `map_text_filtered` | 地图可交互文本 | `id`, `name`, `text` |
| `character_filtered` | 角色资料 | `id`, `name`, `text` |
| `mission` / `book` / `artifact` / `weapon` / `map_text` / `character` | 元数据（版本、地区等），供 `get_meta` 查询 | `id`, `version`, `ext` … |

> 本项目对 MongoDB **纯只读**，不会修改任何数据。

### 3. 配置

创建 `/root/.story-digger-agent/config.toml`：

```toml
[mongo]
host = "localhost"
port = 27017
database = "mihoyo"
username = "your_username"
password = "your_password"
# auth_source = "admin"    # 可选，默认 admin

[chat]
base_url = "https://api.xiaomimimo.com/anthropic"
api_key = "your_api_key"
model = "mimo-v2.5-pro"
stream = true
debug_llm = false

[agent]
output_dir = "./output/"
max_subagents = 5
```

### 4. 运行

```bash
uv run python src/__main__.py
```

也可以指定配置文件路径：

```bash
uv run python src/__main__.py --config /path/to/custom-config.toml
```

---

## 🎮 使用示例

```
$ uv run python src/__main__.py
输出目录：/opt/src/story-digger-agent/output
故事挖掘员就绪（模型 mimo-v2.5-pro）。输入故事线关键词开始，exit/quit 退出。

你> 渊下

⟐ mcp__mongo__search_texts(keywords=['渊下'], collections=None, limit=20)

找到以下候选故事线：

1. 渊下宫·白夜国 — 渊下宫主线剧情，涉及白夜国历史、大日御舆、深海龙蜥
   出处：任务对白 (mission_filtered)、书籍 (book_filtered)
2. 常世国·渊下 — 涉及常世国与渊下宫的关系
   出处：书籍 (book_filtered)、武器 (weapon_filtered)
3. 龙骨血睦 — 渊下宫支线，珊瑚宫与海祇岛相关
   出处：任务对白 (mission_filtered)

请选择（可多选，或补充描述）：

你> 1，再加上海祇岛相关的内容

## 渊下宫·白夜国与海祇岛

### 概述
渊下宫是位于提瓦特地下的古代文明遗迹...

### 第一章 白夜国的建立
白夜国起源于...（原文引用）
[出处: 任务·常世国 (mission_filtered:50123)]

### 第二章 海祇岛的崛起
海祇岛与渊下宫的联系在于...（原文引用）
[出处: 武器·珊瑚宫之誓 (weapon_filtered:10234)]

...

### 人物/势力表
| 人物 | 势力 | 简述 |
|------|------|------|
| ...  | ...  | ...  |

### 检索覆盖说明
检索关键词：渊下宫、白夜国、大日御舆、海祇岛、珊瑚宫...
- mission_filtered：命中 47 篇
- book_filtered：命中 12 篇
- ...
```

文档保存到 `output/渊下宫·白夜国与海祇岛.md`。

---

## ⚙️ 配置详解

### `[mongo]` — MongoDB 连接

| 字段 | 类型 | 说明 |
|------|------|------|
| `host` | string | MongoDB 主机地址 |
| `port` | int | MongoDB 端口 |
| `database` | string | 数据库名（如 `mihoyo`） |
| `username` | string | 用户名 |
| `password` | string | 密码 |
| `auth_source` | string | 认证库，默认 `admin` |

### `[chat]` — 模型端点

| 字段 | 类型 | 说明 |
|------|------|------|
| `base_url` | string | Anthropic 兼容 API 端点 |
| `api_key` | string | API 密钥 |
| `model` | string | 模型名（如 `mimo-v2.5-pro`） |
| `stream` | bool | 是否流式输出 |
| `debug_llm` | bool | 是否打印 LLM 调试日志 |

### `[agent]` — Agent 行为

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `output_dir` | string | `./output/` | 产出文档输出目录 |
| `max_subagents` | int | `5` | 并行 Sub Agent 上限 |

---

## 📄 输出文档格式

每份产出文档包含以下结构：

```markdown
# <故事线名称>
> 涉及版本/地区概览、一句话概述

## 概述
<故事线整体脉络>

## 第一章 <主题>
<梳理后的叙事，关键情节逐字引用原文>
[出处: 任务·xxx (mission_filtered:50123)]

## 第二章 <主题>
...

## 人物/势力表
<涉及人物、势力关系梳理>

## 时间线（如可考）
<按版本/事件排序的时间线>

## 资料来源清单
- 集合·名称 (collection:id) — 贡献说明

## 检索覆盖说明
<检索过的关键词、各集合命中数、已知遗漏>
```

实际产出示例可参考：

- [影域的本质与起源](output/影域的本质与起源.md)
- [白沙皇](output/白沙皇.md)
- [至冬女皇](output/至冬女皇.md)

---

## 🧪 测试

```bash
uv run --with pytest pytest tests/ -v
```

测试需要 MongoDB 可达——连不上时相关用例自动 skip。端到端 LLM 交互为手动冒烟，不在自动化测试内。

---

## 🛠️ 技术栈

| 层 | 技术 |
|---|---|
| 语言 | Python 3.13+ |
| 包管理 | uv |
| Agent 框架 | claude-agent-sdk ≥ 0.2.140 |
| 模型 | MiMo (mimo-v2.5-pro) / Anthropic 兼容端点 |
| MCP 框架 | FastMCP ≥ 3.4.7 |
| 数据库驱动 | pymongo ≥ 4.17.0 |
| REPL | prompt_toolkit ≥ 3.0.53 |
| 测试 | pytest ≥ 9.1.1 |

---

## 📁 项目结构

```
src/
├── __main__.py      # 入口
├── config.py        # 配置解析（TOML → 运行时对象）
├── mcp_server.py    # Mongo MCP Server（4 个工具）
├── prompts.py       # 主 Agent + Sub Agent 提示词
└── repl.py          # 交互式 REPL（asyncio + session resume）

tests/
├── conftest.py      # 共享 fixtures
├── test_config.py   # 配置解析测试
├── test_mcp_*.py    # MCP 工具测试
├── test_prompts.py  # 提示词模板测试
└── test_repl.py     # REPL 构建测试
```

---

## 📖 设计文档

- [架构文档](docs/architecture.md)

---

## 📜 许可证

本项目采用 [GNU General Public License v3.0](LICENSE) 或更高版本授权。

这意味着你可以自由使用、修改和分发本项目，但基于本项目的衍生作品必须同样以 GPLv3 开源。