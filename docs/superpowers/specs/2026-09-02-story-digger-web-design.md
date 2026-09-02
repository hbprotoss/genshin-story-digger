# 🖥️ Story Digger Web — 设计规格

> Story Digger Agent 的 Web 对话界面：类似 ChatGPT/grok 的主流大模型对话交互，
> 通过浏览器与现有 claude-agent-sdk 驱动的挖矿 Agent 对话。

## 1. 背景与目标

现有 `story-digger-agent` 是一个基于 Claude Code SDK 驱动的 **CLI REPL**（`repl.py`），
通过 `prompt_toolkit` 在终端流式输出 Agent 回复。本需求为其开发一个 **Web 前端**，
保留 Agent 的全部能力（关键词澄清 → 规划 → 并行挖掘 → 汇总写文档），
但把交互从终端搬到浏览器，提供 ChatGPT 式对话体验。

**核心目标：**
- 浏览器里与 Agent 多轮对话，流式渲染回复
- 侧边栏管理多个独立对话会话
- 详细展示 Agent 的检索/派发过程（工具调用）
- 捕获"最终文档保存"动作，让用户在 Web 里能查看/预览/下载生成的 Markdown 文档

**非目标（YAGNI）：**
- 不接入用户认证体系（仅预留扩展点）
- 不做多租户/权限、不做协作
- 不做向量检索、不做历史文档编辑（只读预览/下载）

## 2. 已确认的关键决策

| 决策点 | 选择 |
|--------|------|
| 后端框架 | Python **FastAPI**（复用 claude-agent-sdk / config / prompts） |
| 前端框架 | **React + Vite + TypeScript** |
| 使用范围 | 本地单用户，**预留多用户扩展** |
| MCP 进程 | **常驻 streamable-http**，web 启动时拉起共享一个进程 |
| 会话历史持久化 | **SQLite**（本地） |
| 工具调用展示 | **详细展示**检索/派发过程 |
| 文档保存改造 | Agent 保存最终文档时，前端能查看/预览/下载 |

## 3. 总体架构

```
浏览器 (React + Vite + TS)
   │  REST（会话 CRUD、发消息、中止）
   │  SSE（text_delta / tool_use / document_saved / done / error）
   ▼
FastAPI 后端 (uvicorn 单进程 asyncio)
   │
   ├─ ConversationManager   对话→agent session 映射 + SQLite 历史存取
   ├─ AgentRuntime          封装 query()+resume，流式→SSE，捕获 Write/文档保存
   └─ MongoMcp              常驻 streamable-http MCP 子进程（启动时拉起）
                               │  pymongo 只读
                               ▼
                             MongoDB
```

**三层核心：**
1. **前端** `web/`（React SPA）—— 对话界面
2. **后端** `src/web/`（FastAPI）—— 会话编排 + Agent 运行时 + SSE 桥 + SQLite
3. **常驻 MCP** —— 复用 `src/mcp_server.py`，新增 streamable-http 运行模式

### 复用与改动现有代码

- **`src/repl.py`**：复用 `sanitize_agent_env()`、`build_options()`、`format_message()`。
  改动点：`build_options()` 里的 `mcp_servers` 由 stdio 改为指向常驻 HTTP 端点
  （通过参数注入，不破坏 REPL 现有行为）。
- **`src/config.py`**：新增 web 相关配置段（`web.host/port`、`web.db_path`、MCP 常驻端口）。
- **`src/mcp_server.py`**：新增 `--transport streamable-http` 运行模式（FastMCP 原生支持），
  通过 `--host / --port` 启动为共享服务。

## 4. 组件详解

### 4.1 后端 `src/web/`

目录结构：

```
src/web/
├── __init__.py
├── main.py            # 启动编排：拉起常驻 MCP 子进程 + 启动 uvicorn
├── app.py             # FastAPI 实例 + 路由
├── agent_runtime.py   # AgentRuntime：query+resume、流式事件转换、停止
├── conversations.py   # ConversationManager + SQLite 会话/消息持久化
└── mongo_mcp.py       # 常驻 MCP 子进程生命周期管理
```

#### `AgentRuntime`（核心复用层）

- 复用 `repl.build_options()`，但 `mcp_servers` 指向常驻 HTTP 端点
  （`McpHttpServerConfig{type:"http", url:"http://127.0.0.1:{MCP_PORT}/mcp"}`）。
- 每回合一次 `query(prompt, options)`，`resume` 用该会话的 agent `session_id`。
- 流式迭代结果，转成 SSE 事件推到前端：

| SSE 事件 | 来源 | 载荷 |
|----------|------|------|
| `text_delta` | `TextBlock` | 正文增量（以块为单位） |
| `tool_use` | `ToolUseBlock` | 工具名 + 入参摘要（详细展示） |
| `document_saved` | `Write` 工具（写 `output_dir` 且后缀 `.md`） | 文件名、相对/绝对路径 |
| `done` | `ResultMessage` | 停止原因、错误标记、耗时 |
| `error` | 异常 | 错误信息（会话保留可重试） |

- **停止**：宿主 `conversation_id` 的取消令牌 → `asyncio.CancelledError`
  取消当前 `query` 流。
- **并发**：全局**单生成锁**——任一时刻只跑一个生成流，其余排队
  （可选配并发数，本期固定 1）。

#### `ConversationManager` + SQLite

- 表：
  - `conversations(id, title, owner, created_at, updated_at, agent_session_id)`
  - `messages(id, conversation_id, role, content, kind, meta_json, created_at)`
- `kind`：`user` / `assistant`（含流式正文与工具调用 JSON）/ `document`（文档保存记录）
  → 刷新页面后可完整恢复对话与文档卡片。
- `owner` 字段预留多用户扩展；本期硬编码 `"local"`。

#### FastAPI 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/conversations` | 新建（body: `title?`） |
| `GET` | `/api/conversations` | 列出 |
| `GET` | `/api/conversations/{id}` | 历史消息（含文档记录） |
| `POST` | `/api/conversations/{id}/messages` | 发消息 → SSE 流 |
| `POST` | `/api/conversations/{id}/abort` | 停止生成 |
| `GET` | `/api/projects` | 读取 `output_dir`，列出已生成文档 |
| `GET` | `/api/projects/{filename}` | 预览 / 下载某文档 |
| `DELETE` | `/api/conversations/{id}` | 删除会话（可选） |

> 多用户扩展点：路由层预留 `owner` 解析（默认读配置单用户），改动集中在中间件。

### 4.2 文档保存改造（新增需求）

现状：Agent 在"第四步：汇总撰写"用 `Write` 工具把最终文档保存到
`{output_dir}<故事线名>.md`，REPL 只打印一行工具摘要。

改造后（Web 场景）：
1. **捕获**：`AgentRuntime` 检测到写入 `output_dir` 且以 `.md` 结尾的 `Write` 调用
   → 发 `document_saved` SSE 事件，并写入 SQLite 一条 `kind=document` 消息，
   关联到当前 conversation。
2. **展示**：前端在该回合下方渲染"📄 已生成文档"卡片，含文件名 + [查看][下载]，
   链接到 `GET /api/projects/{filename}`。
3. **入口备份**：`GET /api/projects` 读取 `output_dir` 目录兜底，
   用户也能在"项目"视图浏览所有已生成文档（含未在当前对话中保存的）。
4. REPL 行为**不变**（stdio 模式仍按原样打印摘要）——改造只在 Web 后端路径生效。

### 4.3 前端 `web/`（React + Vite + TS）

```
web/
├── index.html
├── vite.config.ts
├── package.json
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── api.ts              # REST + SSE 客户端封装
    ├── types.ts            # 会话/消息/事件类型
    ├── components/
    │   ├── Sidebar.tsx     # 会话列表 + 新建/删除
    │   ├── ChatView.tsx    # 消息流 + 输入/停止
    │   ├── Message.tsx     # 单条消息（markdown 渲染 / 工具调用详情 / 文档卡片）
    │   ├── ToolCall.tsx    # 折叠的"正在检索…"详情
    │   ├── DocCard.tsx     # document_saved 卡片（查看/下载）
    │   └── ProjectsView.tsx# 项目（文档）浏览
    └── styles.css
```

**交互（ChatGPT 式）：**
- 左侧边栏：会话列表、新建、删除
- 主区：消息流，AI 消息 **markdown 渲染**（`react-markdown`），流式**增量追加**
- 工具调用：折叠条目，展开显示具体检索关键词/派发章节（详细展示）
- 文档卡片：保存完成即显示，可预览(`GET /api/projects/{name}`)与下载
- 底部输入框：Enter 发送 / 停止按钮（后者调 `POST abort` + 前端 `AbortController`）
- 生成中禁发，收到 `done`/`error` 后恢复

**SSE 消费**：前端用 `fetch` 流式读 `text/event-stream`（比 `EventSource` 更易附带 POST
与令牌），按 `event:` 分发到 reducer 累加 UI 状态。

## 5. 数据流（一次回合）

```
1. 前端 POST /api/conversations/{id}/messages {content:"渊下"}
2. 后端校验单生成锁；存 user 消息
3. AgentRuntime.start(prompt, conv.session_id)
4. async for msg in query(...)：
     TextBlock        → SSE text_delta
     ToolUseBlock     → SSE tool_use（详情） + 存历史
     Write(.md 到 output_dir) → SSE document_saved + 存 kind=document
5. ResultMessage     → SSE done（含 stop_reason）
6. 释放生成锁；前端据此结束"生成中"态
```

## 6. 错误处理

| 场景 | 处理 |
|------|------|
| LLM API 失败 | SSE `error`，会话保留可重试（沿用 REPL 语义） |
| 单锁被占 | 前端禁用发送；后端额外排队（可选 409），避免静默丢消息 |
| 用户停止 | `CancelledError` 取消当前流，回读历史，UI 恢复 |
| 常驻 MCP 崩溃 | 由 `mongo_mcp.py` 重启；查询中间失败如实报 `error` |
| MongoDB 连接失败 | 沿用 MCP 启动 fast-fail，web 返回明确错误 |
| 生成中的文档 | `Write` 未触达结束时只发部分 `tool_use`，不产生 `document_saved` |

## 7. 测试策略

- **后端 pytest**（`tests/` 扩展）
  - `test_web_conversations.py`：会话 CRUD + SQLite 持久化
  - `test_web_agent_runtime.py`：mock SDK `query`，断言 SSE 事件序列
    （text_delta / tool_use / document_saved / done / error）
  - `test_web_abort.py`：中止路径
  - `test_web_projects.py`：`output_dir` 文档列表/预览
  - 复用现有 `conftest.py` fixtures
- **前端 Vitest + Testing Library**
  - `Message`/`ToolCall`/`DocCard` 渲染
  - SSE reducer：流式累加、`document_saved` 触发卡片
  - 发送/停止交互

## 8. 目录结构落位

```
src/
├── web/                  # 新增：FastAPI 后端（见 §4.1）
├── mcp_server.py         # 改动：新增 --transport/--host/--port
├── repl.py               # 改动：build_options 支持 mcp 端点注入（向后兼容）
└── config.py             # 改动：新增 [web] 配置段
web/                      # 新增：React 前端（见 §4.3）
tests/                    # 扩展：web 后端测试
docs/superpowers/specs/   # 本设计文档
```

## 9. 启动方式

新增入口 `python -m src.web.main`（或 `uv run story-digger-web`）：
1. 载入 config → 按需新增 `[web]` 段
2. 拉起常驻 MCP 子进程（streamable-http, `127.0.0.1:{MCP_PORT}`）
3. 启动 uvicorn（`127.0.0.1:{WEB_PORT}`）
4. 前端开发期由 Vite dev server 代理 `/api` 到后端；生产由同一 FastAPI 静态托管 `web/dist`

CLI REPL 入口 **保持可用**，两条路径共用 `repl.build_options()` / `mcp_server.py`。

## 10. 未决/后续（明确排除本期）

- 用户认证与多租户：仅预留 `owner` 字段 / 中间件扩展点
- 并发生成数上限配置：本期固定 1
- 生成中的编辑器内联编辑 / 断点续挖
- WebSocket 替代 SSE（本期 SSE 足够）
