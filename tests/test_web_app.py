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
                            duration_ms=0, duration_api_ms=0,
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


def test_delete_conversation(client):
    cid = client.post("/api/conversations", json={"title": "x"}).json()["id"]
    assert client.delete(f"/api/conversations/{cid}").status_code == 200
    assert client.get(f"/api/conversations/{cid}").status_code == 404


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
