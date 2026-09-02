# Story Digger Web 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有 `story-digger-agent`（CLI REPL）改造为 FastAPI + React Web 应用：浏览器里与 Agent 多轮对话、流式渲染、侧边栏多会话、SQLite 持久化、详细展示工具调用、捕获并展示生成的 Markdown 文档。

**Architecture:** FastAPI 后端（`src/`）复用现有 `config.py`/`prompts.py`/`mcp_server.py`，移除 `repl.py`；拉起常驻 streamable-http MCP 子进程，Agent 通过 HTTP 端点共享。后端每个对话一个独立 agent `session_id` 链，`query()+resume` 流式输出转成 SSE 事件推给 React 前端。React（Vite+TS）SPA 渲染 ChatGPT 式对话。

**Tech Stack:** Python 3.13+、FastAPI、uvicorn、SQLite（stdlib `sqlite3`）、pymongo、claude-agent-sdk、FastMCP；前端 Vite、React 18、TypeScript、react-markdown、Vitest、Testing Library。

**Spec:** [docs/superpowers/specs/2026-09-02-story-digger-web-design.md](../../docs/superpowers/specs/2026-09-02-story-digger-web-design.md)

## Global Constraints

- 开发分支：`feature/web`
- 包管理：`uv`（`uv sync` / `uv add` / `uv run`）
- 后端仍为**非包结构**：`src/` 无 `__init__.py`，模块间 `from config import ...` 路径导入，`pythonpath = ["src"]`（pytest 配置已有）
- 入口：`uv run python src/__main__.py`（保留 `__main__.py`，**不创建** `__init__.py`）
- 移除 REPL：`src/repl.py` 与 `tests/test_repl.py` 删除，其逻辑迁入 `src/agent_runtime.py`
- 所有输出/回复用中文
- 提交信息遵循仓库既有风格（`feat:`/`fix:`/`docs:`/`refactor:`/`chore:`），行尾加 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- 每个任务结束 `git commit -q`

---

## 文件结构（本计划将创建/修改）

后端（`src/`）：
- Modify `src/config.py` — 新增 `WebConfig`（web 段）+ `AppConfig.web`
- Modify `src/mcp_server.py` — 新增 `--transport/--host/--port`（streamable-http 模式）
- Create `src/conversations.py` — `ConversationManager` + SQLite（conversations/messages 表）
- Create `src/agent_runtime.py` — `AgentRuntime`（迁移 repl 的 `sanitize_agent_env`/`build_options`/事件生成 `stream_turn`）
- Create `src/app.py` — FastAPI 实例、路由、SSE 端点、`create_app(cfg)` 工厂
- Create `src/mongo_mcp.py` — 常驻 MCP 子进程生命周期
- Modify `src/__main__.py` — Web 启动编排
- Delete `src/repl.py`
- Modify `pyproject.toml` — 依赖调整

测试（`tests/`）：
- Create `tests/test_web_conversations.py`
- Create `tests/test_web_agent_runtime.py`
- Create `tests/test_web_app.py`
- Create `tests/test_web_mcp.py`
- Create `tests/test_web_config.py`
- Delete `tests/test_repl.py`

前端（`web/`，新建）：
- `package.json`、`vite.config.ts`、`tsconfig.json`、`index.html`
- `src/types.ts`、`src/api.ts`、`src/sse.ts`（SSE 解析 + reducer）
- `src/components/`：`Sidebar`、`ChatView`、`Message`、`ToolCall`、`DocCard`、`ProjectsView`
- `src/App.tsx`、`src/main.tsx`、`src/styles.css`
- 测试：`src/*.test.ts(x)`（Vitest）

---

### Task 1: 依赖与配置层（`[web]` 段）

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/config.py`
- Create: `tests/test_web_config.py`
- Test: `tests/fixtures/config.toml`（加 `[web]` 节）

**Interfaces:**
- Produces: `AppConfig.web: WebConfig`，`WebConfig(host: str, port: int, mcp_port: int, db_path: Path)`
- Produces: 依赖新增 `fastapi`、`uvicorn`；dev 新增 `httpx`

- [ ] **Step 1: 调整依赖**

在 `pyproject.toml` 的 `[project].dependencies` 移除 `prompt-toolkit>=3.0.53`，加入：
```toml
    "fastapi>=0.115",
    "uvicorn>=0.30",
```
在 `[dependency-groups].dev` 加入 `httpx>=0.27`（FastAPI TestClient 需要）：
```toml
dev = [
    "pytest>=9.1.1",
    "httpx>=0.27",
]
```
然后运行 `uv sync` 更新锁文件：
```bash
uv sync
```
预期：无报错，`uv.lock` 更新。

- [ ] **Step 2: 编写配置测试（先红）**

创建 `tests/test_web_config.py`：
```python
"""[web] 配置段解析测试。"""

from pathlib import Path

from config import AppConfig, load_config


def test_load_web_config_defaults(fixtures_cfg: Path):
    cfg = load_config(fixtures_cfg)
    assert cfg.web.port == 8080
    assert cfg.web.mcp_port == 9100
    assert cfg.web.db_path == Path("/tmp/story-digger-test.db")


def test_sdk_env_unchanged(fixtures_cfg: Path):
    cfg = load_config(fixtures_cfg)
    assert cfg.sdk_env() == {
        "ANTHROPIC_BASE_URL": "https://api.xiaomimimo.com/anthropic",
        "ANTHROPIC_AUTH_TOKEN": "sk-test",
    }
```
在 `tests/conftest.py` 中加入一个模块级 fixture（供全计划复用）：
```python
@pytest.fixture()
def fixtures_cfg() -> Path:
    return Path(__file__).parent / "fixtures" / "config.toml"
```

- [ ] **Step 3: 跑测试确认失败**

```bash
uv run pytest tests/test_web_config.py -v
```
预期：失败，`AttributeError: 'AppConfig' object has no attribute 'web'`。

- [ ] **Step 4: 实现 `WebConfig` + `[web]` 解析**

在 `src/config.py` 顶部 import 后、`MongoConfig` 前新增：
```python
@dataclass
class WebConfig:
    host: str = "127.0.0.1"
    port: int = 8080
    mcp_port: int = 9100
    db_path: Path = Path("~/.story-digger-agent/story-digger.db").expanduser()
```
在 `AppConfig` 中新增字段：
```python
@dataclass
class AppConfig:
    mongo: MongoConfig
    chat: ChatConfig
    agent: AgentConfig = field(default_factory=AgentConfig)
    web: WebConfig = field(default_factory=WebConfig)
```
在 `load_config()` 里解析（`web` 段可选，缺省用默认值）：
```python
    web_data = data.get("web", {})
    return AppConfig(
        mongo=MongoConfig(**data["mongo"]),
        chat=ChatConfig(**data["chat"]),
        agent=AgentConfig(
            output_dir=Path(agent_data.get("output_dir", "./output")),
            max_subagents=agent_data.get("max_subagents", 5),
        ),
        web=WebConfig(
            host=web_data.get("host", "127.0.0.1"),
            port=web_data.get("port", 8080),
            mcp_port=web_data.get("mcp_port", 9100),
            db_path=Path(web_data.get("db_path", "~/.story-digger-agent/story-digger.db")).expanduser(),
        ),
    )
```

- [ ] **Step 5: 更新测试 fixture**

在 `tests/fixtures/config.toml` 末尾追加：
```toml
[web]
port = 8080
mcp_port = 9100
db_path = "/tmp/story-digger-test.db"
```

- [ ] **Step 6: 跑测试确认通过**

```bash
uv run pytest tests/test_web_config.py -v
```
预期：PASS。同时跑 `uv run pytest tests/test_config.py -v` 确认不回归。

- [ ] **Step 7: 提交**

```bash
git add pyproject.toml uv.lock src/config.py tests/test_web_config.py tests/conftest.py tests/fixtures/config.toml
git commit -q -m "feat(config): 新增 [web] 配置段，调整 web 依赖"
```

---

### Task 2: MCP server 增加 streamable-http 运行模式

**Files:**
- Modify: `src/mcp_server.py`
- Create: `tests/test_web_mcp.py`

**Interfaces:**
- Produces: CLI `--transport`（`stdio`|`streamable-http`，默认 `stdio`）、`--host`、`--port`
- Consumes: 现有 `init_client()` / `mcp.run()` 不变

- [ ] **Step 1: 编写失败测试（CLI 参数解析）**

创建 `tests/test_web_mcp.py`：
```python
"""mcp_server streamable-http 模式（CLI 参数解析）测试。

真实拉起 HTTP 需要 MongoDB，故只测 main 的参数解析与 transport 选择。
"""

import inspect

import mcp_server


def test_main_has_transport_option():
    main_src = inspect.getsource(mcp_server.main)
    assert "--transport" in main_src
    assert "--host" in main_src
    assert "--port" in main_src
```
（该测试断言 `main()` 声明了三个新 CLI 参数——先写它验证会失败。）

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest tests/test_web_mcp.py -v
```
预期：FAIL（`"--transport" not in source`）。

- [ ] **Step 3: 修改 `main()` 支持 transport 参数**

将 `src/mcp_server.py` 的 `main()` 改为：
```python
def main() -> None:
    parser = argparse.ArgumentParser(description="Mongo 检索 MCP server")
    parser.add_argument("--uri", required=True, help="MongoDB 连接 URI（含 authSource）")
    parser.add_argument("--database", required=True, help="数据库名")
    parser.add_argument(
        "--transport", default="stdio", choices=["stdio", "streamable-http"],
        help="传输协议（默认 stdio；streamable-http 供 web 常驻共享）",
    )
    parser.add_argument("--host", default="127.0.0.1", help="streamable-http 监听地址")
    parser.add_argument("--port", type=int, default=9100, help="streamable-http 监听端口")
    args = parser.parse_args()
    init_client(args.uri, args.database)
    if args.transport == "stdio":
        mcp.run()  # stdio
    else:
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
```

- [ ] **Step 4: 跑测试确认通过**

```bash
uv run pytest tests/test_web_mcp.py tests/test_mcp_stats.py tests/test_mcp_search.py tests/test_mcp_get_text.py tests/test_mcp_get_meta.py -v
```
预期：全 PASS（`--transport` 参数解析存在；既有工具函数测试不受影响）。

- [ ] **Step 5: 提交**

```bash
git add src/mcp_server.py tests/test_web_mcp.py
git commit -q -m "feat(mcp): 支持 --transport streamable-http 常驻模式"
```

---

### Task 3: ConversationManager + SQLite

**Files:**
- Create: `src/conversations.py`
- Create: `tests/test_web_conversations.py`

**Interfaces:**
- Consumes: `WebConfig.db_path`；提供 `ConversationConfig(app_cfg)` 由测试传入临时路径
- Produces:
  ```python
  @dataclass
  class Message:
      id: int; conversation_id: int; role: str; content: str
      kind: str; meta: dict; created_at: str

  @dataclass
  class Conversation:
      id: int; title: str; created_at: str; updated_at: str; agent_session_id: str | None

  class ConversationManager:
      def __init__(self, db_path: Path | str): ...
      def create(self, title: str | None = None) -> Conversation: ...
      def list(self) -> list[Conversation]: ...
      def get(self, conversation_id: int) -> Conversation | None: ...
      def set_session(self, conversation_id: int, agent_session_id: str | None) -> None: ...
      def append_message(self, conversation_id: int, role: str, content: str,
                         kind: str = "assistant", meta: dict | None = None) -> Message: ...
      def messages(self, conversation_id: int) -> list[Message]: ...
      def delete(self, conversation_id: int) -> None: ...
      def touch(self, conversation_id: int) -> None: ...   # 更新 updated_at
  ```

- [ ] **Step 1: 编写失败测试**

创建 `tests/test_web_conversations.py`：
```python
"""ConversationManager + SQLite 持久化测试。"""

import json
from pathlib import Path

import pytest

from conversations import ConversationManager


@pytest.fixture()
def mgr(tmp_path: Path) -> ConversationManager:
    return ConversationManager(tmp_path / "test.db")


def test_create_and_get(mgr):
    conv = mgr.create("渊下宫")
    assert conv.id > 0
    assert conv.title == "渊下宫"
    got = mgr.get(conv.id)
    assert got is not None and got.id == conv.id


def test_list_sorted_by_updated(mgr):
    a = mgr.create("甲")
    b = mgr.create("乙")
    assert len(mgr.list()) == 2
    assert {c.id for c in mgr.list()} == {a.id, b.id}


def test_append_and_messages(mgr):
    conv = mgr.create()
    user = mgr.append_message(conv.id, "user", "渊下", kind="user")
    ai = mgr.append_message(conv.id, "assistant", "你好，", meta={"stop": "plan"})
    msgs = mgr.messages(conv.id)
    assert [m.kind for m in msgs] == ["user", "assistant"]
    assert msgs[1].meta == {"stop": "plan"}


def test_append_document_message(mgr):
    conv = mgr.create()
    doc = mgr.append_message(conv.id, "assistant", "", kind="document",
                             meta={"filename": "渊下.md"})
    assert doc.kind == "document"
    assert json.loads(doc.meta)["filename"] == "渊下.md" if isinstance(doc.meta, str) else doc.meta["filename"] == "渊下.md"


def test_persists_across_reopen(mgr, tmp_path):
    conv = mgr.create("纳西妲")
    mgr.append_message(conv.id, "user", "纳西妲")
    mgr2 = ConversationManager(tmp_path / "test.db")
    assert mgr2.get(conv.id) is not None
    assert len(mgr2.messages(conv.id)) == 1


def test_set_session_id(mgr):
    conv = mgr.create()
    mgr.set_session(conv.id, "sess-abc")
    assert mgr.get(conv.id).agent_session_id == "sess-abc"
    mgr.set_session(conv.id, None)
    assert mgr.get(conv.id).agent_session_id is None


def test_delete(mgr):
    conv = mgr.create()
    mgr.delete(conv.id)
    assert mgr.get(conv.id) is None
    assert mgr.messages(conv.id) == []
```
说明：`meta` 存 SQLite 时序列化为 JSON 字符串；读回时反序列化为 dict（见 Step 2 实现）。`test_append_document_message` 的断言兼容 str 或 dict（实现保证返回 dict）。

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest tests/test_web_conversations.py -v
```
预期：FAIL（`ModuleNotFoundError: No module named 'conversations'`）。

- [ ] **Step 3: 实现 `src/conversations.py`**

```python
"""会话与消息的 SQLite 持久化。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Message:
    id: int
    conversation_id: int
    role: str
    content: str
    kind: str
    meta: dict = field(default_factory=dict)
    created_at: str = ""


@dataclass
class Conversation:
    id: int
    title: str
    created_at: str = ""
    updated_at: str = ""
    agent_session_id: str | None = None


_ROW_CONV = "id title created_at updated_at agent_session_id"
_ROW_MSG = "id conversation_id role content kind meta created_at"


class ConversationManager:
    def __init__(self, db_path: Path | str):
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '',
                owner TEXT NOT NULL DEFAULT 'local',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                agent_session_id TEXT
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'assistant',
                meta TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """
        )
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.commit()

    def create(self, title: str | None = None) -> Conversation:
        now = _now()
        cur = self._conn.execute(
            "INSERT INTO conversations (title, created_at, updated_at) VALUES (?, ?, ?)",
            (title or "", now, now),
        )
        self._conn.commit()
        return self.get(cur.lastrowid)  # type: ignore[return-value]

    def list(self) -> list[Conversation]:
        rows = self._conn.execute(
            f"SELECT {_ROW_CONV} FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
        return [self._conv(r) for r in rows]

    def get(self, conversation_id: int) -> Conversation | None:
        row = self._conn.execute(
            f"SELECT {_ROW_CONV} FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        return self._conv(row) if row else None

    def set_session(self, conversation_id: int, agent_session_id: str | None) -> None:
        self._conn.execute(
            "UPDATE conversations SET agent_session_id = ? WHERE id = ?",
            (agent_session_id, conversation_id),
        )
        self.touch(conversation_id)
        self._conn.commit()

    def touch(self, conversation_id: int) -> None:
        self._conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (_now(), conversation_id),
        )
        self._conn.commit()

    def append_message(
        self, conversation_id: int, role: str, content: str,
        kind: str = "assistant", meta: dict | None = None,
    ) -> Message:
        now = _now()
        cur = self._conn.execute(
            "INSERT INTO messages (conversation_id, role, content, kind, meta, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (conversation_id, role, content, kind, json.dumps(meta or {}, ensure_ascii=False), now),
        )
        self.touch(conversation_id)
        self._conn.commit()
        row = self._conn.execute(
            f"SELECT {_ROW_MSG} FROM messages WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return self._msg(row)

    def messages(self, conversation_id: int) -> list[Message]:
        rows = self._conn.execute(
            f"SELECT {_ROW_MSG} FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
        return [self._msg(r) for r in rows]

    def delete(self, conversation_id: int) -> None:
        self._conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        self._conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        self._conn.commit()

    @staticmethod
    def _conv(row: sqlite3.Row) -> Conversation:
        return Conversation(
            id=row["id"], title=row["title"], created_at=row["created_at"],
            updated_at=row["updated_at"], agent_session_id=row["agent_session_id"],
        )

    @staticmethod
    def _msg(row: sqlite3.Row) -> Message:
        return Message(
            id=row["id"], conversation_id=row["conversation_id"], role=row["role"],
            content=row["content"], kind=row["kind"],
            meta=json.loads(row["meta"]) if row["meta"] else {},
            created_at=row["created_at"],
        )
```
> 说明：`owner` 列本期恒为 `'local'`（预留多用户扩展），`create` 不暴露该参数。

- [ ] **Step 4: 跑测试确认通过**

```bash
uv run pytest tests/test_web_conversations.py -v
```
预期：PASS。

- [ ] **Step 5: 提交**

```bash
git add src/conversations.py tests/test_web_conversations.py
git commit -q -m "feat(conversations): SQLite 会话与消息持久化"
```

---

### Task 4: AgentRuntime（迁移 repl 逻辑 + 事件生成 + 单锁 + 停止）

**Files:**
- Create: `src/agent_runtime.py`
- Create: `tests/test_web_agent_runtime.py`

**Interfaces:**
- Consumes: `AppConfig`、`ConversationManager.Conversation`（取 `agent_session_id`）
- Produces:
  ```python
  class AgentRuntime:
      def __init__(self, cfg: AppConfig): ...
      def build_options(self, resume: str | None = None) -> ClaudeAgentOptions: ...
      async def stream_turn(
          self, prompt: str, conversation_id: int, session_id: str | None,
      ) -> AsyncIterator[dict]: ...
      def abort(self, conversation_id: int) -> None: ...
      # 事件 dict 形状: {"event": str, "data": ...}
      #   text_delta:  {"text": str}
      #   tool_use:    {"id","name","input"}
      #   document_saved: {"filename": str, "path": str}
      #   done:        {"stop_reason": str|None, "is_error": bool, "session_id": str|None}
  ```
- Produces（模块级）:`sanitize_agent_env(env: dict|None)`、`format_message(msg) -> str|None`（自 repl 迁移，签名不变）

- [ ] **Step 1: 迁移既有 repl 的纯函数到 agent_runtime**

创建 `src/agent_runtime.py`，放入迁移自 `repl.py` 的模块级常量与两个纯函数，内容与 `src/repl.py` 中的实现**逐字一致**：`_CLAUDE_CODE_ENV_LEAKS`、`sanitize_agent_env(env)`、`format_message(msg)` 及其顶部的 `from claude_agent_sdk.types import TextBlock, ToolUseBlock` 导入。

**此时先不删除 `src/repl.py`**（避免一步失误破坏 repo），正式删除统一放到 Task 7。本任务末尾（Step 9）统一提交。

- [ ] **Step 2: 迁移 `test_repl.py` 到 agent_runtime**

把 `tests/test_repl.py` 中 `test_sanitize_agent_env_*`、`test_format_message_*` 迁移到 `tests/test_web_agent_runtime.py`，顶部 `from agent_runtime import format_message, sanitize_agent_env`（替换原 `from repl import ...`）。其中 `test_build_options_wires_model_env_and_mcp`（断言 stdio 的那个）删除，会在 Task 4 以 http 形态重写。`tests/test_repl.py` 同步删除。

跑：`uv run pytest tests/test_web_agent_runtime.py -v`，预期 PASS（纯函数迁移）。

- [ ] **Step 3: 统一 `engine_cfg` fixture**

在 `tests/test_web_agent_runtime.py` 顶部加导入与一个共享 fixture（供本 Task 后续测试复用）：
```python
import asyncio
from pathlib import Path

import pytest

from agent_runtime import AgentRuntime, format_message, sanitize_agent_env
from config import load_config


@pytest.fixture()
def engine_cfg(fixtures_cfg, tmp_path):
    cfg = load_config(fixtures_cfg)
    cfg.web.db_path = tmp_path / "test.db"
    cfg.agent.output_dir = tmp_path / "output"
    return cfg
```
（`fixtures_cfg` 由 `tests/conftest.py` 在 Task 1 提供。）

- [ ] **Step 4: 编写 build_options 的 http 形态测试（先红）**

在 `tests/test_web_agent_runtime.py` 追加：
```python
def test_build_options_points_mcp_to_http(engine_cfg):
    rt = AgentRuntime(engine_cfg)
    opts = rt.build_options()
    mcp = opts.mcp_servers["mongo"]
    assert mcp["type"] == "http"
    assert mcp["url"].endswith("/mcp")
    assert str(engine_cfg.web.mcp_port) in mcp["url"]
    assert opts.setting_sources == []
    assert "{max_subagents}" not in opts.system_prompt  # 已注入
    assert str(rt._output_dir) in opts.system_prompt
```
> 说明：`AgentRuntime(engine_cfg)` 构造时会 `mkdir` output_dir；`engine_cfg.web.mcp_port` 来自 fixture（Task 1 已实现 `[web]` 解析）。本步先只写测试，跑起来应失败（`build_options` 尚未实现）。

- [ ] **Step 5: 实现 `AgentRuntime.build_options` 与构造器**

在 `src/agent_runtime.py` 中新增：
```python
import asyncio
import sys
from dataclasses import replace
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import ResultMessage, TextBlock, ToolUseBlock

from config import AppConfig
from prompts import MAIN_SYSTEM_PROMPT

_SRC_DIR = Path(__file__).resolve().parent


class AgentRuntime:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self._output_dir = Path(cfg.agent.output_dir).resolve()
        self._output_dir.mkdir(parents=True, exist_ok=True)
        # conversation_id -> 正在运行的 task（用于 abort）
        self._tasks: dict[int, asyncio.Task] = {}
        # 单生成锁：任一时刻只跑一个生成流
        self._lock = asyncio.Lock()
        # 记录每个 conversation_id 累积的正文（供消费方读取已完成文本）
        self.finished_text: dict[int, str] = {}

    def build_options(self, resume: str | None = None) -> ClaudeAgentOptions:
        system_prompt = (
            MAIN_SYSTEM_PROMPT
            .replace("{max_subagents}", str(self.cfg.agent.max_subagents))
            .replace("{output_dir}", str(self._output_dir).rstrip("/") + "/")
        )
        opts = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=self.cfg.chat.model,
            permission_mode="default",
            setting_sources=[],
            allowed_tools=[
                "Read", "Glob", "Grep", "LSP",
                "Write", "Edit",
                "Task",
                "Bash",
                "mcp__mongo__*",
            ],
            forward_subagent_text=True,
            mcp_servers={
                "mongo": {
                    "type": "http",
                    "url": f"http://127.0.0.1:{self.cfg.web.mcp_port}/mcp",
                },
            },
            env=self.cfg.sdk_env(),
            **({} if not self.cfg.chat.debug_llm else {"debug_stderr": sys.stderr}),
        )
        if resume:
            opts = replace(opts, resume=resume)
        return opts
```
> `mcp_servers` 的 `type: "http"` + `url` 满足 SDK `McpHttpServerConfig`。

跑：`uv run pytest tests/test_web_agent_runtime.py -v`，预期 PASS（build_options http 形态现绿）。

- [ ] **Step 6: 编写 `stream_turn` 事件流测试（先红）**

在 `tests/test_web_agent_runtime.py` 追加（mock SDK `query`，复用 Step 3 已含 `output_dir` 的 `engine_cfg` fixture）：

追加测试：
```python
import asyncio
import agent_runtime as ar_module


async def _collect(agen):
    out = []
    async for ev in agen:
        out.append(ev)
    return out


def test_stream_turn_emits_text_tool_and_done(engine_cfg, monkeypatch):
    from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

    async def fake_query(prompt, options):
        yield AssistantMessage(
            content=[
                TextBlock(text="线索如下："),
                ToolUseBlock(id="t1", name="mcp__mongo__search_texts",
                             input={"keywords": ["坎瑞亚"]}),
            ],
            model="x",
        )
        yield ResultMessage(subtype="success", session_id="s9",
                            stop_reason="end_turn", is_error=False, num_turns=1)

    monkeypatch.setattr(ar_module, "query", fake_query)
    rt = ar_module.AgentRuntime(engine_cfg)

    events = asyncio.run(_collect(rt.stream_turn("渊下", 1, None)))
    kinds = [e["event"] for e in events]
    assert "text_delta" in kinds
    assert "tool_use" in kinds
    assert "done" in kinds
    done = [e for e in events if e["event"] == "done"][0]["data"]
    assert done["stop_reason"] == "end_turn"
    assert done["session_id"] == "s9"
    tool = [e for e in events if e["event"] == "tool_use"][0]["data"]
    assert tool["name"] == "mcp__mongo__search_texts"


def test_stream_turn_captures_document_saved(engine_cfg, monkeypatch, tmp_path):
    from claude_agent_sdk.types import AssistantMessage, ResultMessage, ToolUseBlock

    target = tmp_path / "output" / "纳西妲.md"
    target.parent.mkdir(parents=True, exist_ok=True)

    async def fake_query(prompt, options):
        yield AssistantMessage(
            content=[ToolUseBlock(id="w1", name="Write",
                                  input={"file_path": str(target),
                                         "content": "# 纳西妲"})],
            model="x",
        )
        yield ResultMessage(subtype="success", session_id="s1",
                            stop_reason="end_turn", is_error=False, num_turns=1)

    monkeypatch.setattr(ar_module, "query", fake_query)
    rt = ar_module.AgentRuntime(engine_cfg)
    events = asyncio.run(_collect(rt.stream_turn("纳西妲", 1, None)))
    docs = [e for e in events if e["event"] == "document_saved"]
    assert len(docs) == 1
    assert docs[0]["data"]["filename"] == "纳西妲.md"


def test_stream_turn_not_document_for_other_dir(engine_cfg, monkeypatch, tmp_path):
    from claude_agent_sdk.types import AssistantMessage, ResultMessage, ToolUseBlock

    outside = tmp_path / "其他目录" / "x.md"
    outside.parent.mkdir(parents=True, exist_ok=True)

    async def fake_query(prompt, options):
        yield AssistantMessage(
            content=[ToolUseBlock(id="w1", name="Write",
                                  input={"file_path": str(outside), "content": "x"})],
            model="x",
        )
        yield ResultMessage(subtype="success", session_id="s1",
                            stop_reason="end_turn", is_error=False, num_turns=1)

    monkeypatch.setattr(ar_module, "query", fake_query)
    rt = ar_module.AgentRuntime(engine_cfg)
    events = asyncio.run(_collect(rt.stream_turn("x", 1, None)))
    assert not any(e["event"] == "document_saved" for e in events)


def test_stream_turn_emits_error_on_api_failure(engine_cfg, monkeypatch):
    async def fake_query(prompt, options):
        raise RuntimeError("LLM API 挂了")
        yield  # pragma: no cover

    monkeypatch.setattr(ar_module, "query", fake_query)
    rt = ar_module.AgentRuntime(engine_cfg)
    events = asyncio.run(_collect(rt.stream_turn("渊下", 1, None)))
    kinds = [e["event"] for e in events]
    assert "error" in kinds
    assert "done" in kinds  # 即使出错也收尾
```

- [ ] **Step 7: 实现 `stream_turn` 事件生成 + 锁 + abort**

在 `src/agent_runtime.py` 追加：
```python
    async def stream_turn(
        self, prompt: str, conversation_id: int, session_id: str | None,
    ) -> AsyncIterator[dict]:
        """单回合：持有生成锁跑一次 query，流式产出事件 dict。

        正常结束 / API 出错都产出 done 收尾；被取消（abort）则直接 Re-raise，
        不产出 done（调用方已中断连接）。
        """
        async with self._lock:
            task = asyncio.current_task()
            self._tasks[conversation_id] = task
            new_sid = session_id
            self.finished_text[conversation_id] = ""
            errored = False
            try:
                opts = self.build_options(resume=session_id)
                async for msg in query(prompt=prompt, options=opts):
                    text = self._emit_text(msg)
                    if text:
                        yield {"event": "text_delta", "data": {"text": text}}
                        self.finished_text[conversation_id] += text
                    for ev in self._tool_events(msg):
                        yield ev
                    if new_sid is None:
                        new_sid = getattr(msg, "session_id", None)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                errored = True
                yield {"event": "error", "data": {"message": str(exc)}}
            finally:
                self._tasks.pop(conversation_id, None)
            # 正常收尾（或已发 error）都发 done
            yield {"event": "done", "data": {
                "stop_reason": None, "is_error": errored, "session_id": new_sid,
            }}

    def _emit_text(self, msg) -> str | None:
        content = getattr(msg, "content", None)
        if not content:
            return None
        parts = [b.text for b in content if isinstance(b, TextBlock)]
        return "\n".join(p for p in parts if p) or None

    def _tool_events(self, msg) -> list[dict]:
        """把消息里的 ToolUseBlock 转成 tool_use / document_saved 事件。"""
        events: list[dict] = []
        for block in getattr(msg, "content", []) or []:
            if isinstance(block, ToolUseBlock):
                events.append({"event": "tool_use", "data": {
                    "id": block.id, "name": block.name, "input": block.input,
                }})
                if self._is_document_write(block):
                    path = block.input.get("file_path", "")
                    filename = Path(path).name
                    events.append({"event": "document_saved", "data": {
                        "filename": filename, "path": str(path),
                    }})
        return events

    def _is_document_write(self, block: ToolUseBlock) -> bool:
        if block.name != "Write":
            return False
        path = block.input.get("file_path", "")
        p = Path(path)
        return p.is_absolute() and p.resolve().is_relative_to(self._output_dir) \
            and p.suffix == ".md"

    def abort(self, conversation_id: int) -> None:
        task = self._tasks.get(conversation_id)
        if task:
            task.cancel()
```
> 说明：`stream_turn` 是**纯事件生成器**，不写 SQLite——历史持久化由 `app.py` 消费事件时完成（Task 5）。`document_saved` 判定要求绝对路径且位于 `output_dir` 内（与 agent 实际 `Write` 行为一致：`build_options` 注入的 output_dir 是绝对路径）。

> 导入补充：`StreamingResponse` 不需要；`AsyncIterator` 需 `from collections.abc import AsyncIterator`。

- [ ] **Step 8: 跑全部 web_agent_runtime 测试**

```bash
uv run pytest tests/test_web_agent_runtime.py -v
```
预期：PASS（build_options http 形态、事件序列、document_saved 捕获、error 分支）。

- [ ] **Step 9: 提交**

```bash
git add src/agent_runtime.py tests/test_web_agent_runtime.py tests/test_repl.py
git commit -q -m "feat(agent_runtime): 迁移 repl 逻辑，事件流生成与单锁/中止"
```

---

### Task 5: FastAPI app 路由 + SSE

**Files:**
- Create: `src/app.py`
- Create: `tests/test_web_app.py`

**Interfaces:**
- Consumes: `ConversationManager`、`AgentRuntime`；`AppConfig`
- Produces: `create_app(cfg: AppConfig, mgr: ConversationManager, rt: AgentRuntime) -> FastAPI`
- Produces 端点（见 spec §4.1 表）：`POST/GET /api/conversations`、`GET /api/conversations/{id}`、`POST /api/conversations/{id}/messages`（SSE）、`POST /api/conversations/{id}/abort`、`GET /api/projects`、`GET /api/projects/{filename}`

- [ ] **Step 1: 编写失败测试（TestClient 路由 + SSE）**

创建 `tests/test_web_app.py`：
```python
"""FastAPI 路由与 SSE 集成测试（mock SDK query）。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

import agent_runtime as ar_module
from app import create_app
from config import load_config
from conversations import ConversationManager


@pytest.fixture()
def client(tmp_path, monkeypatch):
    cfg = load_config(Path(__file__).parent / "fixtures" / "config.toml")
    cfg.web.db_path = tmp_path / "test.db"
    cfg.agent.output_dir = tmp_path / "output"

    async def fake_query(prompt, options):
        yield AssistantMessage(
            content=[TextBlock(text="候选："),
                     ToolUseBlock(id="t1", name="mcp__mongo__search_texts",
                                  input={"keywords": ["渊下"], "limit": 5})],
            model="x",
        )
        yield ResultMessage(subtype="success", session_id="s-x",
                            stop_reason="end_turn", is_error=False, num_turns=1)

    monkeypatch.setattr(ar_module, "query", fake_query)
    mgr = ConversationManager(cfg.web.db_path)
    rt = ar_module.AgentRuntime(cfg)
    return TestClient(create_app(cfg, mgr, rt))


def test_create_and_list(client):
    r = client.post("/api/conversations", json={"title": "渊下"})
    assert r.status_code == 200
    cid = r.json()["id"]
    r = client.get("/api/conversations")
    assert any(c["id"] == cid for c in r.json())


def test_send_message_streams_sse(client):
    cid = client.post("/api/conversations", json={}).json()["id"]
    with client.stream("POST", f"/api/conversations/{cid}/messages", json={"content": "渊下"}) as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())
    assert "text_delta" in body
    assert "tool_use" in body
    assert "done" in body


def test_abort_inactive_returns_ok(client):
    assert client.post("/api/conversations/1/abort").status_code == 200


def test_projects_lists_output_dir(client, tmp_path):
    out = tmp_path / "output"
    out.mkdir(parents=True, exist_ok=True)
    (out / "纳西妲.md").write_text("# 纳西妲", encoding="utf-8")
    r = client.get("/api/projects")
    assert r.status_code == 200
    names = [d["filename"] for d in r.json()]
    assert "纳西妲.md" in names


def test_projects_preview(client, tmp_path):
    out = tmp_path / "output"
    out.mkdir(parents=True, exist_ok=True)
    (out / "纳西妲.md").write_text("# 纳西妲", encoding="utf-8")
    r = client.get("/api/projects/纳西妲.md")
    assert r.status_code == 200
    assert "# 纳西妲" in r.text
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest tests/test_web_app.py -v
```
预期：FAIL（`ModuleNotFoundError: No module named 'app'`）。

- [ ] **Step 3: 实现 `src/app.py`**

```python
"""FastAPI 应用：REST 端点 + SSE 消息流。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from agent_runtime import AgentRuntime
from config import AppConfig
from conversations import ConversationManager


SSE = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _sse_event(event: dict) -> str:
    data = event.get("data", "")
    if isinstance(data, (dict, list)):
        data = json.dumps(data, ensure_ascii=False)
    return f"event: {event['event']}\ndata: {data}\n\n"


def create_app(cfg: AppConfig, mgr: ConversationManager, rt: AgentRuntime) -> FastAPI:
    app = FastAPI(title="story-digger-web")

    @app.post("/api/conversations")
    def create_conversation(body: dict | None = None):
        title = (body or {}).get("title")
        conv = mgr.create(title=title)
        return {"id": conv.id, "title": conv.title,
                "created_at": conv.created_at, "updated_at": conv.updated_at}

    @app.get("/api/conversations")
    def list_conversations():
        return [{"id": c.id, "title": c.title, "created_at": c.created_at,
                 "updated_at": c.updated_at} for c in mgr.list()]

    @app.get("/api/conversations/{cid}")
    def get_conversation(cid: int):
        conv = mgr.get(cid)
        if conv is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        return {"id": conv.id, "title": conv.title, "created_at": conv.created_at,
                "updated_at": conv.updated_at,
                "messages": [{"id": m.id, "role": m.role, "content": m.content,
                              "kind": m.kind, "meta": m.meta, "created_at": m.created_at}
                             for m in mgr.messages(cid)]}

    @app.post("/api/conversations/{cid}/messages")
    async def send_message(cid: int, body: dict):
        content = (body.get("content") or "").strip()
        if not content:
            raise HTTPException(status_code=400, detail="内容不能为空")
        conv = mgr.get(cid)
        if conv is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        mgr.append_message(cid, "user", content, kind="user")

        async def gen() -> AsyncIterator[str]:
            session_id = conv.agent_session_id
            new_sid = session_id
            pending: list[str] = []          # 累积 assistant 正文
            docs: list[dict] = []
            async for ev in rt.stream_turn(content, cid, session_id):
                data = ev.get("data", {})
                if ev["event"] == "text_delta":
                    pending.append(data.get("text", ""))
                elif ev["event"] == "document_saved":
                    docs.append(data)
                elif ev["event"] == "done":
                    new_sid = data.get("session_id") or new_sid
                yield _sse_event(ev)
            # 回合结束：把累积的 assistant 正文与文档消息写入历史
            if pending:
                mgr.append_message(cid, "assistant", "".join(pending), kind="assistant")
            for d in docs:
                mgr.append_message(cid, "assistant", "", kind="document", meta=d)
            # 持久化最新 agent session_id
            mgr.set_session(cid, new_sid)

        return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE)

    @app.post("/api/conversations/{cid}/abort")
    def abort_conversation(cid: int):
        rt.abort(cid)
        return {"ok": True}

    @app.get("/api/projects")
    def list_projects():
        out = Path(cfg.agent.output_dir)
        items = []
        if out.is_dir():
            for p in sorted(out.glob("*.md")):
                items.append({"filename": p.name,
                              "size": p.stat().st_size,
                              "mtime": p.stat().st_mtime})
        return items

    @app.get("/api/projects/{filename}")
    def get_project(filename: str):
        out = Path(cfg.agent.output_dir).resolve()
        target = (out / filename).resolve()
        if out != target.parent or not target.is_file():
            raise HTTPException(status_code=404, detail="文档不存在")
        return FileResponse(target, media_type="text/markdown", filename=filename)

    return app
```
> 说明：`stream_turn` 完成后把 `pending`/`docs` 写历史、`set_session` 更新——刷新页面可恢复（spec §4.1）。`get_project` 用 `out != target.parent` 限制只能访问 `output_dir` 直接子文件（防目录穿越）。

- [ ] **Step 4: 跑测试确认通过**

```bash
uv run pytest tests/test_web_app.py -v
```
预期：PASS。

- [ ] **Step 5: 提交**

```bash
git add src/app.py tests/test_web_app.py
git commit -q -m "feat(api): FastAPI 路由与 SSE 消息流"
```

---

### Task 6: 常驻 MCP 生命周期 + Web 入口

**Files:**
- Create: `src/mongo_mcp.py`
- Modify: `src/__main__.py`

**Interfaces:**
- Consumes: `AppConfig`（`mongo.uri()`、`mongo.database`、`web.mcp_port`）
- Produces: `MongoMcpManager` / 启动函数 `spawn_mongo_mcp(cfg) -> subprocess.Popen`
- Produces: `__main__.main()` 无参、启动 uvicorn 前拉起常驻 MCP

- [ ] **Step 1: 编写失败测试（子进程命令构造）**

创建 `tests/test_web_mcp.py` 追加：
```python
def test_spawn_command_points_to_http(mongo_cfg_prereq, cfg):
    from mongo_mcp import mcp_cmd
    cmd = mcp_cmd(cfg)
    assert "--transport" in cmd
    assert "streamable-http" in cmd
    assert f"--port={cfg.web.mcp_port}" in cmd or str(cfg.web.mcp_port) in cmd
    assert "--uri" in cmd
```
（`mcp_cmd(cfg)` 返回常驻命令 argv 列表，纯函数便于测试，不真正拉起进程。）

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest tests/test_web_mcp.py -v
```
预期：FAIL（`No module named 'mongo_mcp'`）。

- [ ] **Step 3: 实现 `src/mongo_mcp.py`**

```python
"""常驻 Mongo MCP 子进程生命周期（streamable-http）。"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

from config import AppConfig

_SRC_DIR = Path(__file__).resolve().parent


def mcp_cmd(cfg: AppConfig) -> list[str]:
    """构造常驻 MCP 子进程命令行（streamable-http）。"""
    return [
        sys.executable,
        str(_SRC_DIR / "mcp_server.py"),
        "--uri", cfg.mongo.uri(),
        "--database", cfg.mongo.database,
        "--transport", "streamable-http",
        "--host", "127.0.0.1",
        "--port", str(cfg.web.mcp_port),
    ]


def wait_http_ready(url: str, timeout: float = 10.0) -> bool:
    """轮询 streamable-http 端点直到可连（GET 返回非 5xx 即视为就绪）。"""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                return resp.status < 500
        except Exception:
            time.sleep(0.2)
    return False


class MongoMcp:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.proc: subprocess.Popen | None = None

    def start(self) -> None:
        self.proc = subprocess.Popen(
            mcp_cmd(self.cfg),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not wait_http_ready(f"http://127.0.0.1:{self.cfg.web.mcp_port}/mcp"):
            self.stop()
            raise RuntimeError("Mongo MCP server 未能就绪")

    def stop(self) -> None:
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None
```

- [ ] **Step 4: 修正 step1 测试（去掉不存在的 fixture 依赖）**

`test_spawn_command_points_to_http` 不依赖 DB，直接用 `load_config(fixtures_cfg)`：
```python
def test_spawn_command_points_to_http(fixtures_cfg):
    from mongo_mcp import mcp_cmd
    cfg = load_config(fixtures_cfg)
    cmd = mcp_cmd(cfg)
    assert "--transport" in cmd
    assert "streamable-http" in cmd
    assert str(cfg.web.mcp_port) in cmd
```
跑：`uv run pytest tests/test_web_mcp.py -v`，PASS。

- [ ] **Step 5: 实现 `__main__.py` 启动编排**

将 `src/__main__.py` 全量替换为：
```python
"""Web 入口：拉起常驻 MCP + 启动 uvicorn。"""

from __future__ import annotations

import argparse
import os
import sys

import uvicorn

from agent_runtime import AgentRuntime, sanitize_agent_env
from config import DEFAULT_CONFIG_PATH, load_config
from conversations import ConversationManager
from mongo_mcp import MongoMcp


def main() -> None:
    parser = argparse.ArgumentParser(description="Story Digger Agent Web 服务")
    parser.add_argument(
        "--config", default=str(DEFAULT_CONFIG_PATH),
        help="配置文件路径（默认 ~/.story-digger-agent/config.toml）",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    cfg.agent.output_dir = cfg.agent.output_dir.resolve()
    cfg.agent.output_dir.mkdir(parents=True, exist_ok=True)

    sanitize_agent_env()
    for k, v in cfg.sdk_env().items():
        os.environ[k] = v

    mcp = MongoMcp(cfg)
    mcp.start()

    mgr = ConversationManager(cfg.web.db_path)
    rt = AgentRuntime(cfg)

    from app import create_app
    app = create_app(cfg, mgr, rt)

    try:
        uvicorn.run(app, host=cfg.web.host, port=cfg.web.port)
    finally:
        mcp.stop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 冒烟验证（无 Mongo 时可预期启动失败但退出干净）**

```bash
uv run timeout 5 python src/__main__.py --config tests/fixtures/config.toml
```
若本机无 MongoDB，预期：MongoMcp 因 `wait_http_ready` 超时抛 `RuntimeError` 并干净退出（不悬挂）。若本机有 Mongo，预期：打印启动后由 timeout 结束。两种都算通过冒烟。

- [ ] **Step 7: 提交**

```bash
git add src/mongo_mcp.py src/__main__.py tests/test_web_mcp.py
git commit -q -m "feat(web): 常驻 MCP 生命周期与 Web 启动编排"
```

---

### Task 7: 清理 REPL 残留与测试

**Files:**
- Modify: `tests/test_web_app.py`、`tests/test_web_agent_runtime.py`（确认无 `from repl` / `"stdio"` 断言）
- Delete: `src/repl.py`、`tests/test_repl.py`（若 Task 4 未删）
- Modify: `README.md`

- [ ] **Step 1: 全仓搜索残留引用**

```bash
grep -rn "from repl\|import repl\|repl\.\|stdio" src tests README.md | grep -v "streamable"
```
预期：无 `from repl` / `import repl` / `repl.` 引用，无 `"stdio"` 断言残留（`streamable-http` 除外）。

- [ ] **Step 2: 清理文件（若存在）**

```bash
rm -f src/repl.py src/__pycache__/repl*.pyc tests/test_repl.py
```

- [ ] **Step 3: 更新 README 入口说明**

阅读 `README.md` 中 "快速开始/运行" 章节，把 `uv run python src/__main__.py` 的描述从"REPL"改为"启动 Web 服务（常驻 MCP + FastAPI，默认 http://127.0.0.1:8080）"。加一句：前端开发 `cd web && uv run npm run dev`（或说明用构建产物由后端托管）。

- [ ] **Step 4: 全量后端测试通过**

```bash
uv run pytest tests/ -v
```
预期：全部 PASS（无 Mongo 时 MCP-真实库测试 skip）。

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -q -m "refactor: 移除 REPL，仅保留 Web 入口"
```

---

### Task 8: 前端脚手架 + 类型

**Files:**
- Create: `web/package.json`、`web/vite.config.ts`、`web/tsconfig.json`、`web/index.html`
- Create: `web/src/types.ts`
- Create: `web/src/main.tsx`（占位渲染 App）

**Interfaces:**
- Produces: NPM scripts `dev`/`build`/`test`
- Produces: `types.ts` 导出 `Conversation`、`Message`、`ProjectItem`、`SSEEvent`

- [ ] **Step 1: 创建 `web/package.json`**

```json
{
  "name": "story-digger-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-markdown": "^9.0.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "typescript": "^5.6.3",
    "vite": "^6.0.0",
    "vitest": "^2.1.8",
    "@testing-library/react": "^16.1.0",
    "@testing-library/jest-dom": "^6.6.3",
    "jsdom": "^25.0.1"
  }
}
```

- [ ] **Step 2: 创建 `web/vite.config.ts`**

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8080',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/setupTests.ts'],
  },
})
```
> `test` 字段需 `/// <reference types="vitest" />` 或单独 `vitest.config`；此处直接内联 vitest 配置需借助类型合并。为简单，改用 `web/vitest.config.ts` 单独配置 test 段，`vite.config.ts` 只保留 server.proxy 与插件。

实际采用：`web/vitest.config.ts`：
```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/setupTests.ts'],
  },
})
```
并在 `vite.config.ts` 只留：
```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8080' } },
})
```

- [ ] **Step 3: 创建 `web/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "vite.config.ts", "vitest.config.ts"]
}
```

- [ ] **Step 4: 创建 `web/index.html`**

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Story Digger</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: 创建 `web/src/types.ts`**

```ts
export interface Conversation {
  id: number
  title: string
  created_at: string
  updated_at: string
}

export type MessageKind = 'user' | 'assistant' | 'document'

export interface Message {
  id: number
  conversation_id: number
  role: string
  content: string
  kind: MessageKind
  meta: Record<string, unknown>
  created_at: string
}

export interface ProjectItem {
  filename: string
  size: number
  mtime: number
}

export type SSEEventType = 'text_delta' | 'tool_use' | 'document_saved' | 'done' | 'error'

export interface SSEEvent<T = unknown> {
  event: SSEEventType
  data: T
}

export interface ToolUseData {
  id: string
  name: string
  input: Record<string, unknown>
}

export interface DocSavedData {
  filename: string
  path: string
}

export interface DoneData {
  stop_reason: string | null
  is_error: boolean
  session_id: string | null
}
```

- [ ] **Step 6: 创建占位 `main.tsx` + `setupTests.ts` + 最小 App**

`web/src/main.tsx`：
```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```
`web/src/setupTests.ts`：
```ts
import '@testing-library/jest-dom'
```
`web/src/App.tsx`（最小占位，Task 11 完善）：
```tsx
export default function App() {
  return <div className="app">Story Digger</div>
}
```
`web/src/styles.css`：
```css
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, -apple-system, sans-serif; }
```

- [ ] **Step 7: 安装依赖并跑一个冒烟测试**

```bash
cd web && npm install
npm run build
npx vitest run
```
预期：build 通过；无测试时 vitest 退出码 0（或加一个 `App.test.tsx` 渲染断言）。创建 `web/src/App.test.tsx`：
```tsx
import { render, screen } from '@testing-library/react'
import App from './App'

test('renders brand', () => {
  render(<App />)
  expect(screen.getByText(/story digger/i)).toBeInTheDocument()
})
```
跑 `npm test`，PASS。

- [ ] **Step 8: 提交**

```bash
cd web && git add -A && git commit -q -m "feat(web): Vite+React+TS 脚手架与类型定义"
```

---

### Task 9: API 客户端 + SSE 解析 + reducer

**Files:**
- Create: `web/src/api.ts`
- Create: `web/src/sse.ts`
- Create: `web/src/api.test.ts`、`web/src/sse.test.ts`

**Interfaces:**
- Produces:
  ```ts
  export async function fetchConversations(): Promise<Conversation[]>
  export async function createConversation(title?: string): Promise<Conversation>
  export async function fetchConversation(id: number): Promise<{ id: number; messages: Message[] }>
  export async function fetchProjects(): Promise<ProjectItem[]>
  export function abortConversation(id: number): Promise<void>
  export async function streamChat(id: number, content: string,
      onEvent: (e: SSEEvent) => void, signal?: AbortSignal): Promise<void>
  ```
- Produces: `reduceSSE(buf: string, onEvent)` 纯函数（从 SSE 文本块提取 `event:`/`data:` 并回调）；`parseSSEBlock(block: string): SSEEvent`

- [ ] **Step 1: 编写 sse 解析测试（先红）**

创建 `web/src/sse.ts`：
```ts
import type { SSEEvent } from './types'

/** 把一段 SSE 响应文本解析为事件并回调（容错：被网络切成多块的缓冲）。 */
export function parseSSEBlock(block: string): SSEEvent[] {
  const events: SSEEvent[] = []
  const lines = block.split(/\r?\n/)
  let eventName = 'message'
  const dataLines: string[] = []
  const flush = () => {
    if (dataLines.length) {
      let data: unknown = dataLines.join('\n')
      try { data = JSON.parse(String(data)) } catch { /* 保持原字符串 */ }
      events.push({ event: eventName as SSEEvent['event'], data })
      dataLines.length = 0
    }
  }
  for (const line of lines) {
    if (!line) { flush(); continue }
    const [key, ...rest] = line.split(':')
    const value = rest.join(':').trim()
    if (key === 'event') eventName = value
    else if (key === 'data') dataLines.push(value)
  }
  flush()
  return events
}

/** SSE 增量 reducer：accumulated 负责跨块缓冲未结束的 data 行。 */
export function reduceSSE(accumulated: { pending: string }, chunk: string,
                          onEvent: (e: SSEEvent) => void): void {
  accumulated.pending += chunk
  const idx = accumulated.pending.lastIndexOf('\n\n')
  if (idx === -1) return
  const complete = accumulated.pending.slice(0, idx)
  accumulated.pending = accumulated.pending.slice(idx + 2)
  for (const ev of parseSSEBlock(complete)) onEvent(ev)
}
```

创建 `web/src/sse.test.ts`：
```ts
import { describe, it, expect } from 'vitest'
import { parseSSEBlock, reduceSSE } from './sse'

describe('parseSSEBlock', () => {
  it('parses typed event with json data', () => {
    const es = parseSSEBlock('event: text_delta\ndata: {"text":"你好"}\n\nevent: done\ndata: {"session_id":null}\n\n')
    expect(es).toHaveLength(2)
    expect(es[0].event).toBe('text_delta')
    expect((es[0].data as { text: string }).text).toBe('你好')
  })
  it('falls back to raw string when data not json', () => {
    const es = parseSSEBlock('event: x\ndata: plain text\n\n')
    expect(es[0].data).toBe('plain text')
  })
})

describe('reduceSSE', () => {
  it('buffers partial chunks and flushes on blank line', () => {
    const buf = { pending: '' }
    const seen: string[] = []
    reduceSSE(buf, 'event: text_delta\ndata: {', (e) => seen.push(e.event))
    expect(seen).toHaveLength(0)
    reduceSSE(buf, '"hi"}\n\n', (e) => seen.push(e.event))
    expect(seen).toEqual(['message'])
  })
})
```

- [ ] **Step 2: 编写 api 客户端测试（先红）**

创建 `web/src/api.test.ts`（mock `globalThis.fetch`）：
```ts
import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest'
import { fetchConversations, streamChat, abortConversation } from './api'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchConversations', () => {
  it('GETs conversations', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify([])))
    const out = await fetchConversations()
    expect(out).toEqual([])
    expect(fetch).toHaveBeenCalledWith('/api/conversations')
  })
})

describe('abortConversation', () => {
  it('POSTs abort', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('{}'))
    await abortConversation(2)
    expect(fetch).toHaveBeenCalled()
  })
})

describe('streamChat', () => {
  it('yields text_delta events over a read stream', async () => {
    const body = 'event: text_delta\ndata: {"text":"hi"}\n\nevent: done\ndata: {"session_id":"s"}\n\n'
    const stream = new ReadableStream({
      start(c) { c.enqueue(new TextEncoder().encode(body)); c.close() },
    })
    vi.mocked(fetch).mockResolvedValue(new Response(stream, {
      headers: { 'content-type': 'text/event-stream' },
    }))
    const seen: string[] = []
    await streamChat(1, 'hi', (e) => seen.push(e.event))
    expect(seen).toContain('text_delta')
    expect(seen).toContain('done')
  })
})
```

- [ ] **Step 3: 实现 `web/src/api.ts`**

```ts
import type { Conversation, Message, ProjectItem, SSEEvent } from './types'
import { reduceSSE } from './sse'

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json() as Promise<T>
}

export async function fetchConversations(): Promise<Conversation[]> {
  return json(await fetch('/api/conversations'))
}

export async function createConversation(title?: string): Promise<Conversation> {
  return json(await fetch('/api/conversations', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(title ? { title } : {}),
  }))
}

export async function fetchConversation(id: number): Promise<{ id: number; messages: Message[] }> {
  return json(await fetch(`/api/conversations/${id}`))
}

export async function fetchProjects(): Promise<ProjectItem[]> {
  return json(await fetch('/api/projects'))
}

export async function abortConversation(id: number): Promise<void> {
  await fetch(`/api/conversations/${id}/abort`, { method: 'POST' })
}

export async function streamChat(
  id: number, content: string,
  onEvent: (e: SSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`/api/conversations/${id}/messages`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ content }),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  const buf = { pending: '' }
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    reduceSSE(buf, decoder.decode(value, { stream: true }), onEvent)
  }
  reduceSSE(buf, decoder.decode(), onEvent)
}
```

- [ ] **Step 4: 跑前端测试**

```bash
cd web && npm test
```
预期：PASS（sse + api）。

- [ ] **Step 5: 提交**

```bash
cd web && git add -A && git commit -q -m "feat(web): API 客户端与 SSE 解析"
```

---

### Task 10: 前端组件（Sidebar/ChatView/Message/ToolCall/DocCard/ProjectsView）

**Files:**
- Create: `web/src/components/ToolCall.tsx`
- Create: `web/src/components/DocCard.tsx`
- Create: `web/src/components/Message.tsx`
- Create: `web/src/components/ChatView.tsx`
- Create: `web/src/components/Sidebar.tsx`
- Create: `web/src/components/ProjectsView.tsx`
- Create: `web/src/components/ToolCall.test.tsx`、`DocCard.test.tsx`、`Message.test.tsx`

**Interfaces:**
- Consumes: `types.ts`、`api.ts`
- Produces（每个组件 props）：
  - `ToolCall({ call }: { call: ToolUseData })`
  - `DocCard({ doc }: { doc: { filename: string } })`
  - `Message({ msg }: { msg: MessageT })`（组件名 `Message` 与类型名 `Message` 冲突，模块内用 `MessageT` 别名引入类型）
  - `ChatView({ conversationId }: { conversationId: number })`
  - `Sidebar({ items, activeId, onSelect, onNew, onDelete })`
  - `ProjectsView()`
  - `Sidebar({ items, activeId, onSelect, onNew, onDelete })`
  - `ProjectsView()`

- [ ] **Step 1: 编写 ToolCall 测试（先红）**

创建 `web/src/components/ToolCall.tsx`：
```tsx
import type { ToolUseData } from '../types'

const TOOL_LABEL: Record<string, string> = {
  'mcp__mongo__search_texts': '🔍 检索原文',
  'mcp__mongo__get_text': '📖 读取正文',
  'mcp__mongo__get_meta': '🏷️ 查询元数据',
  'mcp__mongo__stats': '📊 查看统计',
  Task: '👥 派发章节',
  Write: '📄 写入文档',
}

function fmtInput(name: string, input: Record<string, unknown>): string {
  if (name === 'mcp__mongo__search_texts') {
    const kw = (input.keywords as string[] | undefined) ?? []
    return `关键词：${kw.join('、')}`
  }
  if (name === 'Task') {
    return (input.prompt as string | undefined)?.slice(0, 40) ?? ''
  }
  if (name === 'Write') {
    return String(input.file_path ?? '')
  }
  return ''
}

export default function ToolCall({ call }: { call: ToolUseData }) {
  const label = TOOL_LABEL[call.name] ?? call.name
  const detail = fmtInput(call.name, call.input)
  return (
    <details className="tool-call">
      <summary>{label}{detail ? ` · ${detail}` : ''}</summary>
      <pre>{JSON.stringify(call.input, null, 2)}</pre>
    </details>
  )
}
```

创建 `web/src/components/ToolCall.test.tsx`：
```tsx
import { render, screen } from '@testing-library/react'
import ToolCall from './ToolCall'

test('shows label and keyword detail for search_texts', () => {
  render(<ToolCall call={{ id: 't1', name: 'mcp__mongo__search_texts', input: { keywords: ['渊下'] } }} />)
  expect(screen.getByText(/检索原文/)).toBeInTheDocument()
  expect(screen.getByText(/关键词：渊下/)).toBeInTheDocument()
})
```

- [ ] **Step 2: 编写 DocCard 测试（先红）**

创建 `web/src/components/DocCard.tsx`：
```tsx
export default function DocCard({ filename }: { filename: string }) {
  return (
    <div className="doc-card">
      📄 已生成文档：{filename}
      <a href={`/api/projects/${encodeURIComponent(filename)}`} target="_blank" rel="noreferrer">查看</a>
      <a href={`/api/projects/${encodeURIComponent(filename)}?download=1`}>下载</a>
    </div>
  )
}
```

创建 `web/src/components/DocCard.test.tsx`：
```tsx
import { render, screen } from '@testing-library/react'
import DocCard from './DocCard'

test('renders filename and links', () => {
  render(<DocCard filename="渊下宫.md" />)
  expect(screen.getByText(/已生成文档：渊下宫\.md/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '查看' }).getAttribute('href')).toContain('渊下宫.md')
})
```

- [ ] **Step 3: 编写 Message 测试（先红）**

创建 `web/src/components/Message.tsx`（markdown 渲染 + 按 kind 分发）：
```tsx
import ReactMarkdown from 'react-markdown'
import type { Message as MessageT } from '../types'
import DocCard from './DocCard'

export default function Message({ msg }: { msg: MessageT }) {
  if (msg.kind === 'document') {
    return <div className="msg document"><DocCard filename={String(msg.meta.filename ?? '')} /></div>
  }
  if (msg.role === 'user') {
    return <div className="msg user"><div className="bubble">{msg.content}</div></div>
  }
  return (
    <div className="msg assistant">
      <div className="bubble markdown">
        <ReactMarkdown>{msg.content}</ReactMarkdown>
      </div>
    </div>
  )
}
```

创建 `web/src/components/Message.test.tsx`：
```tsx
import { render, screen } from '@testing-library/react'
import Message from './Message'

test('renders user bubble', () => {
  render(<Message msg={{ id: 1, conversation_id: 1, role: 'user', content: 'hello', kind: 'user', meta: {}, created_at: '' }} />)
  expect(screen.getByText('hello')).toBeInTheDocument()
})

test('renders assistant markdown', () => {
  render(<Message msg={{ id: 2, conversation_id: 1, role: 'assistant', content: '**bold**', kind: 'assistant', meta: {}, created_at: '' }} />)
  expect(screen.getByText('bold').tagName).toBe('STRONG')
})

test('renders document card', () => {
  render(<Message msg={{ id: 3, conversation_id: 1, role: 'assistant', content: '', kind: 'document', meta: { filename: 'a.md' }, created_at: '' }} />)
  expect(screen.getByText(/已生成文档/)).toBeInTheDocument()
})
```

- [ ] **Step 4: 跑三个组件测试**

```bash
cd web && npm test
```
预期：PASS。

- [ ] **Step 5: 实现 ChatView（流式积累 + 发送/停止）**

创建 `web/src/components/ChatView.tsx`：
```tsx
import { useCallback, useEffect, useRef, useState } from 'react'
import { abortConversation, fetchConversation, streamChat } from '../api'
import type { Message, SSEEvent, ToolUseData } from '../types'
import MessageView from './Message'
import ToolCallView from './ToolCall'
import DocCardView from './DocCard'

export default function ChatView({ conversationId }: { conversationId: number }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [toolCalls, setToolCalls] = useState<ToolUseData[]>([])
  const [docs, setDocs] = useState<string[]>([])
  const abortRef = useRef<AbortController | null>(null)
  const bottomRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    let alive = true
    setMessages([])
    setToolCalls([])
    setDocs([])
    fetchConversation(conversationId).then(({ messages }) => {
      if (!alive) return
      setMessages(messages)
    })
    return () => { alive = false }
  }, [conversationId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, toolCalls, docs])

  const handleEvent = useCallback((e: SSEEvent) => {
    if (e.event === 'text_delta') {
      const text = String((e.data as { text: string }).text)
      setMessages((prev) => {
        const last = prev[prev.length - 1]
        if (last && last.kind === 'assistant') {
          const updated = [...prev]
          updated[updated.length - 1] = { ...last, content: last.content + text }
          return updated
        }
        return [...prev, { id: -1, conversation_id: conversationId, role: 'assistant',
          kind: 'assistant', content: text, meta: {}, created_at: '' }]
      })
    } else if (e.event === 'tool_use') {
      setToolCalls((prev) => [...prev, e.data as ToolUseData])
    } else if (e.event === 'document_saved') {
      setDocs((prev) => [...prev, (e.data as { filename: string }).filename])
    } else if (e.event === 'done' || e.event === 'error') {
      setBusy(false)
    }
  }, [conversationId])

  const send = async () => {
    const content = input.trim()
    if (!content || busy) return
    setMessages((prev) => [...prev, { id: -1, conversation_id: conversationId, role: 'user',
      kind: 'user', content, meta: {}, created_at: '' } as Message])
    setToolCalls([])
    setDocs([])
    setInput('')
    setBusy(true)
    const ac = new AbortController()
    abortRef.current = ac
    try {
      await streamChat(conversationId, content, handleEvent, ac.signal)
    } catch { setBusy(false) }
    setBusy(false)
  }

  const stop = () => {
    abortConversation(conversationId)
    abortRef.current?.abort()
    setBusy(false)
  }

  return (
    <div className="chat">
      <div className="messages">
        {messages.map((m, i) =>
          m.kind === 'document'
            ? null
            : <MessageView key={m.kind === 'assistant' ? `a-${i}` : `u-${i}`} msg={m} />,
        )}
        {toolCalls.length > 0 && (
          <div className="toolcalls">
            {toolCalls.map((c) => <ToolCallView key={c.id} call={c} />)}
          </div>
        )}
        {docs.map((d) => <DocCardView key={d} filename={d} />)}
        <div ref={bottomRef} />
      </div>
      <div className="composer">
        <textarea value={input} onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          placeholder="输入故事线关键词…" />
        {busy
          ? <button onClick={stop}>停止</button>
          : <button onClick={send} disabled={!input.trim()}>发送</button>}
      </div>
    </div>
  )
}
```
> ChatView 已在 import 里引入 `ToolCallView` / `DocCardView`；`streamChat`/`abortConversation`
> 来自 Task 9 的 `api.ts`。

- [ ] **Step 6: 实现 Sidebar 与 ProjectsView**

创建 `web/src/components/Sidebar.tsx`：
```tsx
import type { Conversation } from '../types'

export default function Sidebar({ items, activeId, onSelect, onNew, onDelete }:
  { items: Conversation[]; activeId: number | null; onSelect: (id: number) => void;
    onNew: () => void; onDelete: (id: number) => void }) {
  return (
    <aside className="sidebar">
      <button className="new" onClick={onNew}>＋ 新对话</button>
      <ul>
        {items.map((c) => (
          <li key={c.id} className={c.id === activeId ? 'active' : ''} onClick={() => onSelect(c.id)}>
            <span className="title">{c.title || `对话 ${c.id}`}</span>
            <button className="del" onClick={(e) => { e.stopPropagation(); onDelete(c.id) }}>✕</button>
          </li>
        ))}
      </ul>
    </aside>
  )
}
```

创建 `web/src/components/ProjectsView.tsx`：
```tsx
import { useEffect, useState } from 'react'
import { fetchProjects } from '../api'
import type { ProjectItem } from '../types'

export default function ProjectsView() {
  const [items, setItems] = useState<ProjectItem[]>([])
  useEffect(() => {
    fetchProjects().then(setItems).catch(() => {})
  }, [])
  return (
    <div className="projects">
      <h2>已生成文档</h2>
      <ul>
        {items.map((p) => (
          <li key={p.filename}>
            <a href={`/api/projects/${encodeURIComponent(p.filename)}`} target="_blank" rel="noreferrer">
              {p.filename}
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}
```

- [ ] **Step 7: 跑前端测试**

```bash
cd web && npm test && npm run build
```
预期：PASS 且 build 成功。

- [ ] **Step 8: 提交**

```bash
cd web && git add -A && git commit -q -m "feat(web): 对话/侧栏/项目组件"
```

---

### Task 11: App 集成 + 样式 + dev 代理

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/main.tsx`（若有调整）
- Create: `web/src/styles.css`（完善）
- Modify: `web/vite.config.ts`（dev 代理，若 Task 8 未含）
- Create: `web/src/App.test.tsx`（更新为集成断言）

**Interfaces:**
- Produces: 完整 `App`：边栏会话 + 中央 ChatView + 项目切换

- [ ] **Step 1: 实现 `App.tsx` 完整集成**

```tsx
import { useCallback, useEffect, useState } from 'react'
import { createConversation, deleteConversation, fetchConversations } from './api'
import type { Conversation } from './types'
import Sidebar from './components/Sidebar'
import ChatView from './components/ChatView'
import ProjectsView from './components/ProjectsView'

type View = { kind: 'chat'; id: number } | { kind: 'projects' }

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [view, setView] = useState<View | null>(null)

  const load = useCallback(() => {
    fetchConversations().then((cs) => {
      setConversations(cs)
      if (!view && cs.length > 0) setView({ kind: 'chat', id: cs[0].id })
    }).catch(() => {})
  }, [view])

  useEffect(load, [load])

  const onNew = async () => {
    const c = await createConversation()
    setConversations((prev) => [c, ...prev])
    setView({ kind: 'chat', id: c.id })
  }

  const onDelete = async (id: number) => {
    await deleteConversation(id)
    const rest = conversations.filter((c) => c.id !== id)
    setConversations(rest)
    setView(rest.length ? { kind: 'chat', id: rest[0].id } : null)
  }

  return (
    <div className="layout">
      <Sidebar
        items={conversations}
        activeId={view?.kind === 'chat' ? view.id : null}
        onSelect={(id) => setView({ kind: 'chat', id })}
        onNew={onNew}
        onDelete={onDelete}
      />
      <main className="main">
        <div className="tabs">
          <button onClick={() => setView({ kind: 'projects' })}>项目</button>
        </div>
        {view?.kind === 'projects' && <ProjectsView />}
        {view?.kind === 'chat' && <ChatView key={view.id} conversationId={view.id} />}
        {!view && <div className="empty">选择或新建一个对话开始</div>}
      </main>
    </div>
  )
}
```
> 依赖：`api.ts` 需补一个 `deleteConversation`（见下方 Step 2 前后端补充）。

- [ ] **Step 2: 后端补 DELETE 端点 + 前端 deleteConversation**

后端在 `src/app.py` 的 `create_app` 内新增：
```python
    @app.delete("/api/conversations/{cid}")
    def delete_conversation(cid: int):
        if mgr.get(cid) is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        mgr.delete(cid)
        return {"ok": True}
```
在 `tests/test_web_app.py` 增加：
```python
def test_delete_conversation(client):
    cid = client.post("/api/conversations", json={"title": "x"}).json()["id"]
    assert client.delete(f"/api/conversations/{cid}").status_code == 200
    assert client.get(f"/api/conversations/{cid}").status_code == 404
```
后端 `api.ts` 增加：
```ts
export async function deleteConversation(id: number): Promise<void> {
  await fetch(`/api/conversations/${id}`, { method: 'DELETE' })
}
```
跑：`uv run pytest tests/test_web_app.py -v`，PASS。

- [ ] **Step 3: 完善 `styles.css`**

`web/src/styles.css`：
```css
:root { --bg: #f6f7f9; --panel: #fff; --accent: #4f6ef7; --border: #e3e6eb; }
* { box-sizing: border-box; }
html, body, #root { height: 100%; margin: 0; }
body { font-family: system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; }
.layout { display: flex; height: 100%; }
.sidebar { width: 260px; background: var(--panel); border-right: 1px solid var(--border);
  display: flex; flex-direction: column; }
.sidebar .new { margin: 12px; padding: 10px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--accent); color: #fff; cursor: pointer; }
.sidebar ul { list-style: none; margin: 0; padding: 0; overflow-y: auto; flex: 1; }
.sidebar li { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px;
  cursor: pointer; border-bottom: 1px solid var(--border); }
.sidebar li.active { background: #eef1ff; }
.sidebar li .del { border: none; background: none; cursor: pointer; color: #999; }
.main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.tabs { padding: 8px 14px; border-bottom: 1px solid var(--border); background: var(--panel); }
.chat { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.messages { flex: 1; overflow-y: auto; padding: 16px; }
.msg { margin-bottom: 14px; }
.msg.user { display: flex; justify-content: flex-end; }
.msg.user .bubble { background: var(--accent); color: #fff; padding: 10px 14px; border-radius: 12px; max-width: 70%; }
.msg.assistant .bubble { background: var(--panel); border: 1px solid var(--border);
  border-radius: 12px; padding: 12px 14px; max-width: 100%; }
.markdown pre { background: #1e1e1e; color: #ddd; padding: 10px; border-radius: 8px; overflow-x: auto; }
.toolcall, .tool-call { font-size: 13px; color: #555; margin: 4px 0; }
.tool-call summary { cursor: pointer; color: var(--accent); }
.tool-call pre { background: #f0f1f3; padding: 8px; border-radius: 6px; font-size: 12px; }
.doc-card { border: 1px dashed var(--accent); border-radius: 8px; padding: 10px 14px;
  margin: 8px 0; background: #eef1ff; }
.doc-card a { margin-left: 12px; color: var(--accent); }
.composer { display: flex; gap: 8px; padding: 12px 16px; border-top: 1px solid var(--border);
  background: var(--panel); }
.composer textarea { flex: 1; resize: none; min-height: 60px; border: 1px solid var(--border);
  border-radius: 10px; padding: 10px; font-family: inherit; }
.composer button { padding: 0 20px; border-radius: 10px; border: none; background: var(--accent); color: #fff; cursor: pointer; }
.projects { padding: 20px; }
.projects li { margin: 6px 0; }
```

- [ ] **Step 4: 更新 `App.test.tsx` 为 smoke**

将 Task 8 的 `App.test.tsx` 改为渲染冒烟（mock fetch 返回空列表）：
```tsx
import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'
import App from './App'

test('renders new conversation button', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify([]))))
  render(<App />)
  expect(await screen.findByText(/新对话/)).toBeInTheDocument()
  vi.unstubAllGlobals()
})
```

- [ ] **Step 5: 前端全部测试 + build**

```bash
cd web && npm test && npm run build
```
预期：PASS 且 build 产出 `web/dist`。

- [ ] **Step 6: 提交**

```bash
cd web && git add -A
cd .. && git add src/app.py tests/test_web_app.py
git commit -q -m "feat(web): App 集成/样式与 DELETE 端点"
```

---

## Self-Review 自查结果

对照 spec 逐项核对：

- **§4.1 后端组件** → Task 1(config/web)、Task 3(ConversationManager+SQLite)、Task 4(AgentRuntime)、Task 5(app 路由+SSE)、Task 6(mongo_mcp+__main__)。✅
- **§4.1 端点表** → Task 5 + Task 11 补 `DELETE`。✅
- **§4.2 文档保存改造**（捕获 Write→document_saved→DocCard，GET /api/projects 兜底）→ Task 4（捕获）+ Task 5（projects 端点 + 历史写入）+ Task 10（DocCard）。✅
- **§4.3 前端组件** → Task 8-11。✅
- **§5 数据流** → Task 5 `send_message` 的 ge n 顺序（存 user→流式→回合末写 assistant/document/session）。✅
- **§6 错误处理** → Task 4（error 事件、abort、单锁）、Task 5（404/400）。✅
- **§7 测试策略** → 各任务内嵌 pytest / Vitest。✅
- **Global Constraints（移除 REPL、非包结构、__main__入口）** → Task 4/7。✅

## 潜在风险与说明

- `AgentRuntime.stream_turn` 是纯事件生成器，历史写入在 `app.py` send_message 内完成（与 spec 措辞"AgentRuntime 写 SQLite"略有出入，但职责更清晰且不影响 spec 的 SSE 事件表与数据流）。见 Task 5 说明。
- `document_saved` 判定要求 Write 目标为**绝对路径**且在 `output_dir` 内。若某环境下 agent 以相对路径写文件，此判定不触发，前端仅显示 tool_use 详情（不产生文档卡片）。这是有意为之的保守行为。
- 前端 SSE 停止：前端 `AbortController` 中断读取 + 调 `POST abort` 取消后端流，双保险。spec §6 已覆盖。
- MCP 常驻对真实 Mongo 的完整性（拉起后能实际 search_texts）依赖本机 MongoDB；本地无库时以"失败即干净退出"为 smoke 判据。
