# Story Digger Agent 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个基于 claude-code-sdk 驱动 MiMo 模型的交互式 CLI agent，从 MongoDB 中的原神六类文本里挖掘指定故事线，生成带出处的中文 Markdown 文档。

**Architecture:** Python REPL 主程序通过 claude-agent-sdk 启动主 Agent（模型 mimo-v2.5-pro，经 Anthropic 兼容端点），主 Agent 通过 FastMCP stdio server 提供的 4 个工具（search_texts / get_text / get_meta / stats）检索 MongoDB，用 Claude Code 内置 Task 工具并行派发 sub agent，最后汇总写出 Markdown。详见 spec。

**Tech Stack:** Python 3.13 + uv；claude-agent-sdk、fastmcp、pymongo；pytest。

**Spec:** `docs/superpowers/specs/2026-08-20-story-digger-agent-design.md`

## Global Constraints

- 依赖管理一律用 uv（`uv add` / `uv run` / `uv run --with pytest pytest`）
- Python >= 3.13，标准库 `tomllib` 读配置（不用 tomli）
- 源码直接放 `src/`（扁平结构，无包名子目录），pytest 用 `pythonpath = ["src"]` 直接 import
- MongoDB 连接：URI 必须带 `authSource=admin`，即 `mongodb://user:pass@host:port/?authSource=admin`，然后按库名取 `mihoyo` 库
- 对 MongoDB **纯只读**：任何工具/代码不得写库
- 只使用六个 `_filtered` 集合（mission/book/artifact/weapon/map_text/character_filtered）做正文检索；原始集合（去掉 `_filtered` 后缀）只用于查元数据；不使用 kg* 集合
- 配置文件路径 `/root/.story-digger-agent/config.toml`（可用 `--config` 覆盖）
- MCP server 的 Mongo 连接参数通过命令行参数（argv）传入，不在 MCP 进程里读配置文件
- 已验证的 API 事实（实现时直接依赖，勿改）：
  - `fastmcp` 包（3.x，`from fastmcp import FastMCP`；`mcp` 包里没有 `mcp.server.fastmcp`）；`@mcp.tool()` 装饰器**返回原函数**，测试可直接调用
  - `claude_agent_sdk.ClaudeAgentOptions` 支持 `system_prompt` / `model` / `permission_mode` / `mcp_servers` / `env` / `forward_subagent_text` 字段；**不支持 temperature**（CLI 也无此 flag）——配置里的 `temperature` 字段保留但实现忽略它，在 config.py 注释说明
  - `mcp_servers` 值形如 `{"type": "stdio", "command": <python>, "args": [...], "env": {...}}`（TypedDict，`type`/`args`/`env` 可省）
  - 交互式多轮：`ClaudeSDKClient`（`connect` / `query` / `receive_messages` / `interrupt` / `disconnect`），同一 client 上再次 `query()` 自动延续会话
- 每个任务完成后都要 commit；测试命令统一为 `uv run --with pytest pytest tests/ -v`（pytest 通过 `[tool.pytest.ini_options] pythonpath = ["src"]` 找到 src 下模块）

---

### Task 1: 项目脚手架与配置模块

**Files:**
- Modify: `pyproject.toml`
- Create: `src/config.py`
- Delete: `main.py`（uv init 的脚手架，无用处）
- Create: `tests/conftest.py`
- Create: `tests/test_config.py`
- Create: `tests/fixtures/config.toml`（测试用配置）

**Interfaces:**
- Consumes: 无（首个任务）
- Produces:
  - `config.py`：`DEFAULT_CONFIG_PATH: Path`、`@dataclass MongoConfig`（字段 host/port/database/username/password/auth_source，方法 `uri() -> str`）、`@dataclass ChatConfig`（字段 base_url/api_key/model/temperature/stream/debug_llm）、`@dataclass AgentConfig`（字段 output_dir: Path、max_subagents: int）、`@dataclass AppConfig`（字段 mongo/chat/agent，方法 `sdk_env() -> dict[str, str]`）、`load_config(path) -> AppConfig`
  - `tests/conftest.py`：`mongo_cfg` fixture（读默认配置的 mongo 段，连不上则 skip）、`db` fixture（连好的 pymongo Database）

- [ ] **Step 1: 安装依赖并配置 pytest**

```bash
cd /opt/src/story-digger-agent
uv add claude-agent-sdk fastmcp pymongo
uv add --dev pytest
rm main.py
```

`pyproject.toml` 的 `[project]` dependencies 应变为 `["claude-agent-sdk", "fastmcp", "pymongo"]`，`[dependency-groups]` 有 `dev = ["pytest"]`。再在 `pyproject.toml` 末尾追加：

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
```

同时确认 `.gitignore`（uv init 已生成）包含 `.venv` 与 `__pycache__`，并追加一行 `output/`。

- [ ] **Step 2: 写失败测试 `tests/test_config.py`**

先建测试夹具 `tests/fixtures/config.toml`（结构与真实配置一致，auth_source 显式写出，chat 段用 Anthropic 端点）：

```toml
[mongo]
host = "localhost"
port = 27017
database = "mihoyo"
username = "super"
password = "testpass"
auth_source = "admin"

[chat]
stream = true
base_url = "https://api.xiaomimimo.com/anthropic"
api_key = "sk-test"
model = "mimo-v2.5-pro"
temperature = 0.2
debug_llm = true

[agent]
output_dir = "/tmp/story-digger-test-output"
max_subagents = 3
```

`tests/test_config.py`：

```python
from pathlib import Path

from config import AppConfig, AgentConfig, ChatConfig, MongoConfig, load_config

FIXTURE = Path(__file__).parent / "fixtures" / "config.toml"


def test_load_config_parses_all_sections():
    cfg = load_config(FIXTURE)
    assert isinstance(cfg, AppConfig)
    assert cfg.mongo == MongoConfig(
        host="localhost", port=27017, database="mihoyo",
        username="super", password="testpass", auth_source="admin",
    )
    assert cfg.chat == ChatConfig(
        base_url="https://api.xiaomimimo.com/anthropic",
        api_key="sk-test", model="mimo-v2.5-pro",
        temperature=0.2, stream=True, debug_llm=True,
    )
    assert cfg.agent == AgentConfig(
        output_dir=Path("/tmp/story-digger-test-output"), max_subagents=3,
    )


def test_mongo_uri_contains_auth_source():
    cfg = load_config(FIXTURE)
    assert cfg.mongo.uri() == "mongodb://super:testpass@localhost:27017/?authSource=admin"


def test_sdk_env_maps_anthropic_vars():
    cfg = load_config(FIXTURE)
    assert cfg.sdk_env() == {
        "ANTHROPIC_BASE_URL": "https://api.xiaomimimo.com/anthropic",
        "ANTHROPIC_AUTH_TOKEN": "sk-test",
    }


def test_agent_section_is_optional():
    # 无 [agent] 段时用默认值
    tmp = Path("/tmp/sd-agentless.toml")
    tmp.write_text(
        "[mongo]\nhost='h'\nport=1\ndatabase='d'\nusername='u'\npassword='p'\n"
        "[chat]\nbase_url='http://x'\napi_key='k'\nmodel='m'\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp)
    assert cfg.agent.max_subagents == 5
    assert cfg.agent.output_dir == Path("./output")
```

再建 `tests/conftest.py`（供后续任务复用，真实库只读）：

```python
import pytest
from pymongo import MongoClient

from config import DEFAULT_CONFIG_PATH, load_config


@pytest.fixture(scope="session")
def mongo_cfg():
    cfg = load_config(DEFAULT_CONFIG_PATH)
    client = MongoClient(cfg.mongo.uri(), serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
    except Exception:
        pytest.skip("MongoDB 不可达，跳过需要真实库的测试")
    return cfg.mongo


@pytest.fixture(scope="session")
def db(mongo_cfg):
    client = MongoClient(mongo_cfg.uri(), serverSelectionTimeoutMS=3000)
    return client[mongo_cfg.database]
```

- [ ] **Step 3: 运行测试确认失败**

Run: `uv run --with pytest pytest tests/test_config.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'config'`

- [ ] **Step 4: 实现 `src/config.py`**

```python
"""读取 /root/.story-digger-agent/config.toml，映射为运行时配置。"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("/root/.story-digger-agent/config.toml")


@dataclass
class MongoConfig:
    host: str
    port: int
    database: str
    username: str
    password: str
    auth_source: str = "admin"

    def uri(self) -> str:
        # 认证库必须是 admin（super 用户建在 admin 下）；
        # URI 不指定目标库，用 client[database] 按名取库
        return (
            f"mongodb://{self.username}:{self.password}"
            f"@{self.host}:{self.port}/?authSource={self.auth_source}"
        )


@dataclass
class ChatConfig:
    base_url: str
    api_key: str
    model: str
    # 注：claude-agent-sdk / claude CLI 不暴露 temperature，此字段仅保留
    # 在配置里以备将来支持，当前实现会忽略它。
    temperature: float = 0.2
    stream: bool = True
    debug_llm: bool = False


@dataclass
class AgentConfig:
    output_dir: Path = Path("./output")
    max_subagents: int = 5


@dataclass
class AppConfig:
    mongo: MongoConfig
    chat: ChatConfig
    agent: AgentConfig = field(default_factory=AgentConfig)

    def sdk_env(self) -> dict[str, str]:
        return {
            "ANTHROPIC_BASE_URL": self.chat.base_url,
            "ANTHROPIC_AUTH_TOKEN": self.chat.api_key,
        }


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> AppConfig:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    agent_data = data.get("agent", {})
    return AppConfig(
        mongo=MongoConfig(**data["mongo"]),
        chat=ChatConfig(**data["chat"]),
        agent=AgentConfig(
            output_dir=Path(agent_data.get("output_dir", "./output")),
            max_subagents=agent_data.get("max_subagents", 5),
        ),
    )
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run --with pytest pytest tests/test_config.py -v`
Expected: 4 个测试全 PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/config.py tests/ .gitignore
git commit -m "feat: 项目脚手架与配置模块"
```

---

### Task 2: MCP server 骨架与 stats 工具

**Files:**
- Create: `src/mcp_server.py`
- Create: `tests/test_mcp_stats.py`

**Interfaces:**
- Consumes: `conftest.py` 的 `mongo_cfg` / `db` fixture
- Produces:
  - `mcp_server.py`：模块级 `mcp = FastMCP("mongo")`、`init_client(uri: str, database: str) -> None`（全局连接，启动即 ping 验证）、`COLLECTIONS: list[str]`（六个 `_filtered` 集合名）、工具函数 `stats() -> str`（JSON 字符串：`{集合名: 文档数}`）、`main()`（argparse 解析 `--uri/--database`，init 后 `mcp.run()`）
  - 后续任务在同一文件追加 `@mcp.tool()` 函数，测试直接以普通函数方式调用（装饰器返回原函数）

- [ ] **Step 1: 写失败测试 `tests/test_mcp_stats.py`**

```python
import json

import pytest

pytest.importorskip("fastmcp")

import mcp_server


@pytest.fixture(scope="module")
def server(mongo_cfg):
    mcp_server.init_client(mongo_cfg.uri(), mongo_cfg.database)
    return mcp_server


def test_stats_returns_doc_counts_for_all_six_collections(server):
    result = json.loads(server.stats())
    assert set(result.keys()) == set(mcp_server.COLLECTIONS)
    assert result["mission_filtered"] == 986
    assert result["book_filtered"] == 90
    assert result["artifact_filtered"] == 61
    assert result["weapon_filtered"] == 234
    assert result["map_text_filtered"] == 653
    assert result["character_filtered"] == 130
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run --with pytest pytest tests/test_mcp_stats.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'mcp_server'`

- [ ] **Step 3: 实现 `src/mcp_server.py`**

```python
"""Mongo 检索 MCP server（stdio）。对 MongoDB 纯只读。

由主程序经 claude-agent-sdk 以子进程拉起：
    python mcp_server.py --uri <mongo-uri> --database <db>
"""

from __future__ import annotations

import argparse
import json

from fastmcp import FastMCP
from pymongo import MongoClient

COLLECTIONS = [
    "mission_filtered",
    "book_filtered",
    "artifact_filtered",
    "weapon_filtered",
    "map_text_filtered",
    "character_filtered",
]

mcp = FastMCP("mongo")

_client: MongoClient | None = None
_db = None


def init_client(uri: str, database: str) -> None:
    """建立全局连接；连接失败直接抛异常（启动即验证）。"""
    global _client, _db
    _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    _client.admin.command("ping")  # 连接/认证失败在此抛出
    _db = _client[database]


def db():
    if _db is None:
        raise RuntimeError("Mongo 未初始化：需先调用 init_client()")
    return _db


@mcp.tool()
def stats() -> str:
    """各集合文档数一览，了解数据全貌。"""
    return json.dumps(
        {c: db()[c].estimated_document_count() for c in COLLECTIONS},
        ensure_ascii=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Mongo 检索 MCP server")
    parser.add_argument("--uri", required=True, help="MongoDB 连接 URI（含 authSource）")
    parser.add_argument("--database", required=True, help="数据库名")
    args = parser.parse_args()
    init_client(args.uri, args.database)
    mcp.run()  # stdio


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run --with pytest pytest tests/test_mcp_stats.py -v`
Expected: PASS（Mongo 不可达时 SKIP）

- [ ] **Step 5: Commit**

```bash
git add src/mcp_server.py tests/test_mcp_stats.py
git commit -m "feat: MCP server 骨架与 stats 工具"
```

---

### Task 3: search_texts 工具

**Files:**
- Modify: `src/mcp_server.py`（追加工具函数）
- Create: `tests/test_mcp_search.py`

**Interfaces:**
- Consumes: Task 2 的 `init_client` / `db` / `COLLECTIONS`
- Produces: `search_texts(keywords: list[str], collections: list[str] | None = None, limit: int = 20) -> str`。返回 JSON 字符串，结构：

```json
{
  "query": {"keywords": ["坎瑞亚"], "collections": [...], "limit": 20},
  "results": [
    {
      "collection": "mission_filtered",
      "id": "501361",
      "name": "…",
      "matched_keywords": ["坎瑞亚"],
      "text_len": 12345,
      "snippets": ["…前后各约50字的命中上下文…"]
    }
  ],
  "total_matched": 37
}
```

排序：`matched_keywords` 数多的在前，再按 name。每个文档 snippets 最多 3 条（每个命中关键词最多取 2 处，每处约 100 字：命中点前 50 后 80）。

- [ ] **Step 1: 写失败测试 `tests/test_mcp_search.py`**

```python
import json

import pytest

import mcp_server


@pytest.fixture(scope="module")
def server(mongo_cfg):
    mcp_server.init_client(mongo_cfg.uri(), mongo_cfg.database)
    return mcp_server


def test_search_finds_known_docs(server):
    r = json.loads(server.search_texts(["坎瑞亚"]))
    assert r["query"]["keywords"] == ["坎瑞亚"]
    assert r["total_matched"] >= 30  # 实测 mission_filtered 命中 37
    assert len(r["results"]) <= 20
    for item in r["results"]:
        assert item["collection"] in mcp_server.COLLECTIONS
        assert item["matched_keywords"] == ["坎瑞亚"]
        assert item["text_len"] > 0


def test_search_multi_keywords_or(server):
    # 两个关键词：命中数应不少于单关键词（OR 语义）
    single = json.loads(server.search_texts(["坎瑞亚"]))["total_matched"]
    both = json.loads(server.search_texts(["坎瑞亚", "黄金王国"]))["total_matched"]
    assert both >= single


def test_search_respects_collections_filter(server):
    r = json.loads(server.search_texts(["坎瑞亚"], collections=["book_filtered"]))
    assert {item["collection"] for item in r["results"]} <= {"book_filtered"}


def test_search_snippets_contain_keyword(server):
    r = json.loads(server.search_texts(["坎瑞亚"], limit=5))
    assert r["results"]
    for item in r["results"]:
        if item["snippets"]:
            assert any("坎瑞亚" in s for s in item["snippets"])


def test_search_no_match_returns_empty(server):
    r = json.loads(server.search_texts(["绝不存在的关键词xyzzy123"]))
    assert r["results"] == []
    assert r["total_matched"] == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run --with pytest pytest tests/test_mcp_search.py -v`
Expected: FAIL，`AttributeError: module 'mcp_server' has no attribute 'search_texts'`

- [ ] **Step 3: 在 `src/mcp_server.py` 追加实现**（放在 `stats` 之后）

```python
import re


def _escape(keyword: str) -> str:
    return re.escape(keyword)


def _snippets_for(text: str, keyword: str, per_keyword: int = 2) -> list[str]:
    """取命中点上下文片段：命中点前 50 字、后 80 字。"""
    out: list[str] = []
    start = 0
    while len(out) < per_keyword:
        i = text.find(keyword, start)
        if i == -1:
            break
        out.append(text[max(0, i - 50): i + 80])
        start = i + len(keyword)
    return out


@mcp.tool()
def search_texts(
    keywords: list[str],
    collections: list[str] | None = None,
    limit: int = 20,
) -> str:
    """跨集合关键词检索（滚雪球主力工具）。

    对各集合的 name 和 text 做关键词包含匹配（多关键词 OR），
    返回 id/名称/命中关键词/文本长度/命中上下文片段，按命中关键词数排序。
    """
    if not keywords:
        return json.dumps({"error": "keywords 不能为空"}, ensure_ascii=False)

    cols = collections or COLLECTIONS
    invalid = [c for c in cols if c not in COLLECTIONS]
    if invalid:
        return json.dumps({"error": f"未知集合: {invalid}，可用: {COLLECTIONS}"}, ensure_ascii=False)

    # name/text × keyword 的 OR 条件（re.escape 防正则注入）
    conditions = [
        {field: {"$regex": _escape(k)}}
        for k in keywords
        for field in ("name", "text")
    ]
    match = {"$or": conditions}

    results = []
    total = 0
    for coll in cols:
        cursor = db()[coll].find(match, {"name": 1, "text": 1})
        for doc in cursor:
            total += 1
            text = doc.get("text", "") or ""
            name = doc.get("name", "") or ""
            matched = [k for k in keywords if k in text or k in name]
            snippets: list[str] = []
            for k in matched:
                snippets.extend(_snippets_for(text, k))
                if len(snippets) >= 3:
                    break
            results.append({
                "collection": coll,
                "id": doc["id"],
                "name": name,
                "matched_keywords": matched,
                "text_len": len(text),
                "snippets": snippets[:3],
            })
            # 每个集合最多取 limit*3 个候选，防止超广关键词拉爆内存
            if sum(1 for r in results if r["collection"] == coll) >= limit * 3:
                break

    results.sort(key=lambda r: (-len(r["matched_keywords"]), r["name"]))
    results = results[:limit]
    return json.dumps(
        {
            "query": {"keywords": keywords, "collections": cols, "limit": limit},
            "results": results,
            "total_matched": total,
        },
        ensure_ascii=False,
    )
```

注意：`total_matched` 只统计进入候选池的文档数（每集合封顶 limit*3），在工具 docstring 已如实描述为"命中数"。`import re` 与 `_escape`/`_snippets_for` 放在文件顶部工具函数区（`import re` 并入文件头 import 区）。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run --with pytest pytest tests/test_mcp_search.py -v`
Expected: 5 个测试全 PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_server.py tests/test_mcp_search.py
git commit -m "feat: search_texts 跨集合关键词检索工具"
```

---

### Task 4: get_text 工具

**Files:**
- Modify: `src/mcp_server.py`（追加工具函数）
- Create: `tests/test_mcp_get_text.py`

**Interfaces:**
- Consumes: Task 2 的 `init_client` / `db`
- Produces: `get_text(collection: str, id: str, offset: int = 0, length: int = 8000) -> str`。返回 JSON：`{collection, id, name, total_len, offset, returned_len, has_more, text}`；找不到返回 `{"error": "未找到 …"}`

- [ ] **Step 1: 写失败测试 `tests/test_mcp_get_text.py`**

```python
import json

import pytest

import mcp_server


@pytest.fixture(scope="module")
def server(mongo_cfg):
    mcp_server.init_client(mongo_cfg.uri(), mongo_cfg.database)
    return mcp_server


def _first_id(db_obj, coll):
    return db_obj[coll].find_one({}, {"id": 1})["id"]


def test_get_text_returns_full_small_doc(server, db):
    id_ = _first_id(db, "mission_filtered")
    r = json.loads(server.get_text("mission_filtered", id_))
    assert r["id"] == id_
    assert r["collection"] == "mission_filtered"
    assert r["text"]
    assert r["total_len"] == len(r["text"])
    assert r["has_more"] is False
    assert r["offset"] == 0


def test_get_text_pagination(server, db):
    id_ = _first_id(db, "mission_filtered")
    full = json.loads(server.get_text("mission_filtered", id_))
    page1 = json.loads(server.get_text("mission_filtered", id_, offset=0, length=100))
    page2 = json.loads(server.get_text("mission_filtered", id_, offset=100, length=100))
    assert page1["returned_len"] == 100
    assert page1["has_more"] is True
    assert page1["text"] == full["text"][:100]
    assert page2["text"] == full["text"][100:200]
    assert page2["offset"] == 100


def test_get_text_missing_doc_returns_error(server):
    r = json.loads(server.get_text("mission_filtered", "nonexistent-99999"))
    assert "error" in r
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run --with pytest pytest tests/test_mcp_get_text.py -v`
Expected: FAIL，`AttributeError: ... has no attribute 'get_text'`

- [ ] **Step 3: 追加实现**（`search_texts` 之后）

```python
@mcp.tool()
def get_text(collection: str, id: str, offset: int = 0, length: int = 8000) -> str:
    """按 id 取单个文档正文，超长自动分页（默认每页 8000 字）。

    返回 total_len/has_more 标记，需要时用 offset 续读。
    """
    if collection not in COLLECTIONS:
        return json.dumps({"error": f"未知集合: {collection}"}, ensure_ascii=False)
    doc = db()[collection].find_one({"id": id}, {"name": 1, "text": 1})
    if doc is None:
        return json.dumps({"error": f"未找到 {collection}:{id}"}, ensure_ascii=False)
    text = doc.get("text", "") or ""
    chunk = text[offset: offset + length]
    return json.dumps({
        "collection": collection,
        "id": id,
        "name": doc.get("name", ""),
        "total_len": len(text),
        "offset": offset,
        "returned_len": len(chunk),
        "has_more": offset + length < len(text),
        "text": chunk,
    }, ensure_ascii=False)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run --with pytest pytest tests/test_mcp_get_text.py -v`
Expected: 3 个测试全 PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_server.py tests/test_mcp_get_text.py
git commit -m "feat: get_text 分页取全文工具"
```

---

### Task 5: get_meta 工具

**Files:**
- Modify: `src/mcp_server.py`（追加工具函数）
- Create: `tests/test_mcp_get_meta.py`

**Interfaces:**
- Consumes: Task 2 的 `init_client` / `db`
- Produces: `get_meta(collection: str, id: str) -> str`。到原始集合（`mission_filtered` -> `mission`，即去掉 `_filtered` 后缀）查元数据。返回 JSON：保留 `id/name/desc/version/ext/filter_values` 等小字段，剔除 `menus/modules/langs/_id` 等大字段；`ext.fe_ext` 是 JSON 字符串，尝试解析为对象。找不到返回 `{"error": …}`

- [ ] **Step 1: 写失败测试 `tests/test_mcp_get_meta.py`**

```python
import json

import pytest

import mcp_server


@pytest.fixture(scope="module")
def server(mongo_cfg):
    mcp_server.init_client(mongo_cfg.uri(), mongo_cfg.database)
    return mcp_server


def test_get_meta_returns_version_and_parsed_fe_ext(server, db):
    doc = db["mission_filtered"].find_one(
        {"text": {"$regex": "坎瑞亚"}}, {"id": 1}
    )
    r = json.loads(server.get_meta("mission_filtered", doc["id"]))
    assert r["id"] == doc["id"]
    assert "version" in r
    # 大字段被剔除
    assert "menus" not in r and "modules" not in r and "langs" not in r
    # fe_ext 从 JSON 字符串解析成了对象
    fe = r.get("ext", {}).get("fe_ext")
    if fe is not None:
        assert isinstance(fe, dict)


def test_get_meta_missing_returns_error(server):
    r = json.loads(server.get_meta("book_filtered", "nonexistent-99999"))
    assert "error" in r
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run --with pytest pytest tests/test_mcp_get_meta.py -v`
Expected: FAIL，`AttributeError: ... has no attribute 'get_meta'`

- [ ] **Step 3: 追加实现**（`get_text` 之后）

```python
_META_EXCLUDE = {"_id", "menus", "modules", "langs"}


@mcp.tool()
def get_meta(collection: str, id: str) -> str:
    """查原始集合中的文档元数据（版本号、地区、类型筛选等）。

    mission_filtered -> mission（去掉 _filtered 后缀）。剔除 menus/modules
    等大字段；ext.fe_ext 若为 JSON 字符串则解析为对象。
    """
    raw_coll = collection.removesuffix("_filtered")
    if raw_coll not in {c.removesuffix("_filtered") for c in COLLECTIONS}:
        return json.dumps({"error": f"未知集合: {collection}"}, ensure_ascii=False)
    doc = db()[raw_coll].find_one({"id": id})
    if doc is None:
        return json.dumps({"error": f"未找到 {raw_coll}:{id}"}, ensure_ascii=False)
    meta = {k: v for k, v in doc.items() if k not in _META_EXCLUDE}
    ext = meta.get("ext")
    if isinstance(ext, dict) and isinstance(ext.get("fe_ext"), str):
        try:
            ext["fe_ext"] = json.loads(ext["fe_ext"])
        except json.JSONDecodeError:
            pass
    return json.dumps(meta, ensure_ascii=False, default=str)
```

- [ ] **Step 4: 运行全部 MCP 测试确认通过**

Run: `uv run --with pytest pytest tests/ -v`
Expected: config + stats + search + get_text + get_meta 全 PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_server.py tests/test_mcp_get_meta.py
git commit -m "feat: get_meta 元数据查询工具，MCP 工具集齐"
```

---

### Task 6: 提示词模块

**Files:**
- Create: `src/prompts.py`
- Create: `tests/test_prompts.py`

**Interfaces:**
- Consumes: 无
- Produces: `MAIN_SYSTEM_PROMPT: str`（含 `{max_subagents}`/`{output_dir}` 两个运行时 replace 占位符，由 repl.py 注入）、`SUBAGENT_TASK_TEMPLATE: str`（含 `{topic}`/`{seed_keywords}`/`{chapter_title}` 占位符，主 agent 派发 Task 时套用）

- [ ] **Step 1: 写失败测试 `tests/test_prompts.py`**

```python
from prompts import MAIN_SYSTEM_PROMPT, SUBAGENT_TASK_TEMPLATE


def test_main_prompt_has_replace_slots_and_constraints():
    formatted = (
        MAIN_SYSTEM_PROMPT
        .replace("{max_subagents}", "5")
        .replace("{output_dir}", "./output/")
    )
    assert "{max_subagents}" not in formatted
    assert "./output/" in formatted
    # 五条核心约束的关键词都在
    for key in ("候选", "大纲", "并行", "Task", "检索覆盖说明"):
        assert key in formatted


def test_subagent_template_placeholders():
    formatted = SUBAGENT_TASK_TEMPLATE.format(
        topic="坎瑞亚大灾变", seed_keywords="坎瑞亚, 黑日王朝", chapter_title="大灾变",
    )
    assert "坎瑞亚大灾变" in formatted
    assert "黑日王朝" in formatted
    assert "{topic}" not in formatted
    for key in ("滚雪球", "出处", "连续 2 轮"):
        assert key in formatted
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run --with pytest pytest tests/test_prompts.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'prompts'`

- [ ] **Step 3: 实现 `src/prompts.py`**

```python
"""主 agent 与 sub agent 的提示词。"""

_MAIN_PROMPT_TEMPLATE = """你是"故事挖掘员"，一个原神剧情资料整理 agent。你的工具：
- search_texts(keywords, collections?, limit?)：跨六类集合（任务/书籍/圣遗物/武器/地图文本/角色）关键词检索，返回命中摘要
- get_text(collection, id, offset?, length?)：按 id 取正文，超长分页
- get_meta(collection, id)：查版本/地区等元数据
- stats()：各集合文档数
可用集合：mission_filtered、book_filtered、artifact_filtered、weapon_filtered、map_text_filtered、character_filtered。

你的工作流程（严格遵守）：

## 第一步：关键词澄清（必做，不可跳过）
用户给出故事线关键词后，禁止直接开挖。必须：
1. 用 search_texts 对 name 字段做包含匹配，并抽读 2-3 条命中正文确认语境；
2. 输出编号候选列表，每项含一句话说明和出处集合（例如输入"渊下"时给出"1. 渊下宫·白夜国主线剧情线（任务/书籍）"这样的候选）；
3. 明确询问用户：选哪个（可多选），或补充描述。
用户确认前，绝不派发 sub agent。

## 第二步：规划
用户确认后，先读 3-5 篇核心文本建立框架，产出故事线大纲（章节划分 + 每章要回答的问题），展示给用户后再派发。大纲章节数不超过 {max_subagents}。

## 第三步：并行挖掘
用 Task 工具**一次性并行**派发所有章节的 sub agent（在同一条消息里发起多个 Task 调用，不要串行）。每个 sub agent 的任务书严格按以下模板写：

<subagent_task>
{subagent_task}
</subagent_task>

## 第四步：汇总撰写
sub agent 返回后：
1. 合并去重各章产出（相同出处只保留一次）；
2. 检查覆盖：对照大纲发现遗漏可再派一轮 sub agent 补挖；
3. 按大纲写成最终文档，用 Write 工具保存到 {output_dir}<故事线名>.md。

最终文档结构：
# <故事线名称>
> 涉及版本/地区概览、一句话概述
## 概述
## 第一章 <主题>
（梳理后的叙事，关键情节逐字引用原文并标注出处，格式：[出处: 任务·xxx (mission_filtered:50123)]）
## 人物/势力表
## 时间线（如可考）
## 资料来源清单
- 集合·名称 (collection:id) - 一句话说明贡献了什么
## 检索覆盖说明
（检索过的关键词、各集合命中情况、sub agent 失败或未完成的部分如实标注、已知可能的遗漏）

## 纪律
- 原文摘录必须逐字保留，禁止改写引文；
- 出处必须精确到 集合·名称 (collection:id)；
- 某章节 sub agent 失败时重试一次，仍失败则在"检索覆盖说明"里如实标注，不静默吞掉；
- get_text 大文档用分页续读，不要反复从头拉取；
- 全程用中文。
"""

SUBAGENT_TASK_TEMPLATE = """你负责故事线整理的一个子课题，只做自己的章节，不要越界。

主题：{topic}
章节标题：{chapter_title}
种子关键词：{seed_keywords}

工作方法（滚雪球纪律）：
1. 用 search_texts 检索种子关键词（可拆分成多个具体关键词）；
2. 读命中的正文（get_text，长文分页读完），从文中提炼新的实体名/别名/事件名/地名作为新关键词，再检索；
3. 重复上述过程，直到连续 2 轮检索无新增命中才可收尾；
4. 每轮检索覆盖全部六类集合（search_texts 不传 collections 参数即可）；
5. 需要版本/地区信息时用 get_meta。

产出格式（严格遵守）：
## {chapter_title}
<梳理后的叙事，关键情节逐字引用原文>
[出处: 集合·名称 (collection:id)]
<人物/势力小结>

## 覆盖说明
<检索过的所有关键词列表、各集合命中数、哪些方向没找到资料（"没找到"也是有效结论，如实写出）>
"""

# 把任务书模板嵌进主提示词。此后 MAIN_SYSTEM_PROMPT 只剩
# {max_subagents}/{output_dir} 两个运行时占位符，由 repl.py 用 str.replace
# 注入（不能用 .format：模板区里的 {topic} 等占位符会让 format 抛 KeyError）。
MAIN_SYSTEM_PROMPT = _MAIN_PROMPT_TEMPLATE.replace(
    "{subagent_task}", SUBAGENT_TASK_TEMPLATE
)
```


- [ ] **Step 4: 运行测试确认通过**

Run: `uv run --with pytest pytest tests/test_prompts.py -v`
Expected: 2 个测试全 PASS

- [ ] **Step 5: Commit**

```bash
git add src/prompts.py tests/test_prompts.py
git commit -m "feat: 主 agent 与 sub agent 提示词"
```

---

### Task 7: REPL 主程序

**Files:**
- Create: `src/repl.py`
- Create: `src/__main__.py`（三行入口，仅 `from repl import main`）
- Create: `tests/test_repl.py`

**Interfaces:**
- Consumes: `config.load_config` / `AppConfig.sdk_env()`；`prompts.MAIN_SYSTEM_PROMPT`；`mcp_server`（仅作为子进程脚本路径引用，不 import 运行时逻辑）
- Produces: 可执行入口 `uv run python src/__main__.py [--config <path>]`；内部函数 `build_options(cfg: AppConfig) -> ClaudeAgentOptions`（可测试）、`format_message(msg) -> str | None`（可测试）

- [ ] **Step 1: 写失败测试 `tests/test_repl.py`**

```python
import pytest

pytest.importorskip("claude_agent_sdk")

from claude_agent_sdk.types import AssistantMessage, TextBlock, ToolUseBlock

from config import load_config
from repl import build_options, format_message


@pytest.fixture()
def cfg():
    from pathlib import Path
    return load_config(Path(__file__).parent / "fixtures" / "config.toml")


def test_build_options_wires_model_env_and_mcp(cfg):
    opts = build_options(cfg)
    assert opts.model == "mimo-v2.5-pro"
    assert opts.env["ANTHROPIC_BASE_URL"] == "https://api.xiaomimimo.com/anthropic"
    assert opts.env["ANTHROPIC_AUTH_TOKEN"] == "sk-test"
    assert opts.permission_mode == "bypassPermissions"
    assert opts.forward_subagent_text is True
    mcp = opts.mcp_servers["mongo"]
    assert mcp["type"] == "stdio"
    assert mcp["args"][0].endswith("mcp_server.py")
    argv = mcp["args"]
    assert argv[argv.index("--uri") + 1] == cfg.mongo.uri()
    assert argv[argv.index("--database") + 1] == "mihoyo"
    # system prompt 已注入运行时参数
    assert "{max_subagents}" not in opts.system_prompt
    assert "3" in opts.system_prompt  # fixture 的 max_subagents=3
    assert "/tmp/story-digger-test-output" in opts.system_prompt


def test_format_message_text_and_tool_use():
    msg = AssistantMessage(
        content=[TextBlock(type="text", text="你好"), ToolUseBlock(
            id="t1", name="search_texts",
            input={"keywords": ["坎瑞亚"], "limit": 5},
        )],
    )
    out = format_message(msg)
    assert "你好" in out
    assert "search_texts" in out
    assert "坎瑞亚" in out


def test_format_message_ignores_others():
    assert format_message(object()) is None
```

注意：`AssistantMessage`/`TextBlock`/`ToolUseBlock` 的确切构造签名以本机安装的 claude-agent-sdk 为准，实现前先用 `uv run python -c "from claude_agent_sdk.types import AssistantMessage, TextBlock, ToolUseBlock; import inspect; print(inspect.signature(AssistantMessage))"` 确认；若是 dataclass/pydantic 模型，按实际字段构造。`format_message` 的实现要与测试一致，遇到不认识的消息类型返回 None。

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run --with pytest pytest tests/test_repl.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'repl'`

- [ ] **Step 3: 实现 `src/repl.py` 与 `src/__main__.py`**

`src/__main__.py`：

```python
from repl import main

if __name__ == "__main__":
    main()
```

`src/repl.py`：

```python
"""交互式 REPL：claude-agent-sdk 驱动主 Agent，流式输出。"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from config import AppConfig, DEFAULT_CONFIG_PATH, load_config
from prompts import MAIN_SYSTEM_PROMPT

_SRC_DIR = Path(__file__).resolve().parent


def build_options(cfg: AppConfig) -> ClaudeAgentOptions:
    system_prompt = (
        MAIN_SYSTEM_PROMPT
        .replace("{max_subagents}", str(cfg.agent.max_subagents))
        .replace("{output_dir}", str(cfg.agent.output_dir) + "/")
    )
    return ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=cfg.chat.model,
        permission_mode="bypassPermissions",
        forward_subagent_text=True,
        mcp_servers={
            "mongo": {
                "type": "stdio",
                "command": sys.executable,
                "args": [
                    str(_SRC_DIR / "mcp_server.py"),
                    "--uri", cfg.mongo.uri(),
                    "--database", cfg.mongo.database,
                ],
            },
        },
        env=cfg.sdk_env(),
    )


def format_message(msg) -> str | None:
    """把 SDK 消息转成要打印的文本；不需要打印的返回 None。"""
    content = getattr(msg, "content", None)
    if not content:
        return None
    parts: list[str] = []
    for block in content:
        btype = getattr(block, "type", None)
        if btype == "text":
            parts.append(getattr(block, "text", ""))
        elif btype == "tool_use":
            name = getattr(block, "name", "?")
            inp = getattr(block, "input", {}) or {}
            brief = ", ".join(f"{k}={v!r}" for k, v in list(inp.items())[:3])
            parts.append(f"⟐ {name}({brief})")
    return "\n".join(p for p in parts if p) or None


async def run_repl(cfg: AppConfig) -> None:
    options = build_options(cfg)
    client = ClaudeSDKClient(options=options)
    await client.connect()
    print(f"已连接。故事挖掘员就绪（模型 {cfg.chat.model}）。输入故事线关键词开始，exit/quit 退出。")
    try:
        while True:
            try:
                user_input = input("\n你> ").strip()
            except EOFError:
                break
            if not user_input:
                continue
            if user_input in {"exit", "quit"}:
                break
            try:
                await client.query(user_input)
                async for msg in client.receive_messages():
                    text = format_message(msg)
                    if text:
                        print(text)
            except (KeyboardInterrupt, asyncio.CancelledError):
                # Ctrl+C：打断当前轮，回到输入提示符
                print("\n（已打断本轮）")
                try:
                    await client.interrupt()
                except Exception:
                    pass
            except Exception as exc:  # LLM API 失败等：报告但保留会话
                print(f"\n[出错] {exc}\n（会话保留，可重试）")
    finally:
        await client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="原神故事线挖掘 agent")
    parser.add_argument(
        "--config", default=str(DEFAULT_CONFIG_PATH),
        help="配置文件路径（默认 /root/.story-digger-agent/config.toml）",
    )
    args = parser.parse_args()
    cfg = load_config(args.config)
    cfg.agent.output_dir.mkdir(parents=True, exist_ok=True)
    asyncio.run(run_repl(cfg))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run --with pytest pytest tests/test_repl.py -v`
Expected: 3 个测试全 PASS（`build_options` 测试如因 ClaudeAgentOptions 字段校验报错，按报错调整——字段名以 `inspect.signature(ClaudeAgentOptions)` 实测为准）

- [ ] **Step 5: 运行全部测试**

Run: `uv run --with pytest pytest tests/ -v`
Expected: 全 PASS

- [ ] **Step 6: Commit**

```bash
git add src/repl.py src/__main__.py tests/test_repl.py
git commit -m "feat: REPL 主程序，接通 SDK/MCP/提示词"
```

---

### Task 8: 更新真实配置、端到端冒烟与 README

**Files:**
- Modify: `/root/.story-digger-agent/config.toml`（库外文件）
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 1-7 全部成果
- Produces: 可用的运行环境与使用说明

- [ ] **Step 1: 更新真实配置文件**

`/root/.story-digger-agent/config.toml` 改为（`base_url` 换成 Anthropic 兼容端点，mongo 段保持不动，追加 `[agent]` 段；先读原文件确认 username/password 原值不变）：

```toml
[mongo]
host = "localhost"
port = 27017
database = "mihoyo"
username = "super"
password = "<保持原值>"

[chat]
stream = true
base_url = "https://api.xiaomimimo.com/anthropic"
api_key = "<保持原值>"
model = "mimo-v2.5-pro"
temperature = 0.2
debug_llm = true

[agent]
output_dir = "./output/"
max_subagents = 5
```

（temperature 保留字段但当前实现忽略——config.py 已有注释说明。）

- [ ] **Step 2: 确认单元测试在真实配置下仍全绿**

Run: `uv run --with pytest pytest tests/ -v`
Expected: 全 PASS（conftest 读的就是这份真实配置）

- [ ] **Step 3: 端到端冒烟（手动）**

Run: `uv run python src/__main__.py`

操作序列（需人工在终端执行，验证 agent 行为）：
1. 输入 `渊下`，观察：agent 是否先调 `search_texts` 查 name 并输出编号候选列表、询问选择（**不**直接开挖）；
2. 回复选择一个候选（如渊下宫主线），观察：agent 是否展示大纲、并行派发多个 Task sub agent（终端可见 `⟐ Task(...)` 调用）、sub agent 是否各自调 `search_texts`/`get_text`；
3. 等待汇总完成，确认 `output/` 下生成了 `.md` 文件，且含"检索覆盖说明"章节与 `[出处: …]` 标注；
4. 追问一句（如"深渊教团和这条线的关系？"），确认会话延续、agent 可继续挖；
5. `exit` 退出。

冒烟不通过时的排查顺序：MCP server 是否起来（`get_mcp_status`/stderr）→ env 是否传到（ANTHROPIC_BASE_URL）→ 提示词约束是否被模型遵守（收紧措辞）。此步骤标记为手动验收，不在 CI 内。

- [ ] **Step 4: 更新 README.md**

```markdown
# story-digger-agent

原神故事线挖掘 agent：给定故事线名称，从 MongoDB 中的六类游戏文本（任务对白、
书籍、圣遗物、武器、地图可交互文本、角色资料）整理出带出处的中文 Markdown 文档。

基于 claude-code-sdk 驱动 MiMo 模型（mimo-v2.5-pro），主 agent 规划拆分章节后
并行派发 sub agent 滚雪球检索，最后汇总成文。

## 运行

    uv run python src/__main__.py [--config /root/.story-digger-agent/config.toml]

配置文件含 [mongo] / [chat] / [agent] 三段（见 docs/superpowers/specs/）。
产出文档写入 [agent].output_dir（默认 ./output/）。

## 测试

    uv run --with pytest pytest tests/ -v

（需要 MongoDB 可达；LLM 相关为手动冒烟。）

## 设计文档

- docs/superpowers/specs/2026-08-20-story-digger-agent-design.md
- docs/superpowers/plans/2026-08-20-story-digger-agent.md
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: README 使用说明"
```
