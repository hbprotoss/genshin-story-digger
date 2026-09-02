import asyncio
from pathlib import Path

import pytest

import agent_runtime as ar_module
from agent_runtime import AgentRuntime, format_message, sanitize_agent_env
from config import load_config


@pytest.fixture()
def engine_cfg(fixtures_cfg, tmp_path):
    cfg = load_config(fixtures_cfg)
    cfg.web.db_path = tmp_path / "test.db"
    cfg.agent.output_dir = tmp_path / "output"
    return cfg


def test_sanitize_agent_env_clears_claude_code_leaks():
    # 残留的 Claude Code 代理变量会覆盖 config.toml：ANTHROPIC_MODEL /
    # CLAUDE_CODE_SUBAGENT_MODEL 会让（尤其 sub agent 的）模型指向不存在的
    # 代理模型名，ANTHROPIC_API_KEY 会与 AUTH_TOKEN 冲突。启动 agent 前必须清掉。
    env = {
        "ANTHROPIC_MODEL": "ark-code-latest[1m]",
        "CLAUDE_CODE_SUBAGENT_MODEL": "ark-code-latest[1m]",
        "ANTHROPIC_API_KEY": "bad",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "x",
        "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME": "x",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "x",
        "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME": "x",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "x",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME": "x",
        "PATH": "/usr/bin",
    }
    sanitize_agent_env(env)
    for key in (
        "ANTHROPIC_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL", "ANTHROPIC_API_KEY",
        "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME",
        "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME",
    ):
        assert key not in env
    assert env["PATH"] == "/usr/bin"


def test_sanitize_agent_env_keeps_endpoint_vars():
    # BASE_URL / AUTH_TOKEN 由 config.toml 经 sdk_env() 注入，不在清除之列
    env = {"ANTHROPIC_BASE_URL": "u", "ANTHROPIC_AUTH_TOKEN": "t"}
    sanitize_agent_env(env)
    assert env == {"ANTHROPIC_BASE_URL": "u", "ANTHROPIC_AUTH_TOKEN": "t"}


def test_format_message_text_and_tool_use():
    from claude_agent_sdk.types import AssistantMessage, TextBlock, ToolUseBlock

    msg = AssistantMessage(
        content=[
            TextBlock(text="你好"),
            ToolUseBlock(
                id="t1", name="search_texts",
                input={"keywords": ["坎瑞亚"], "limit": 5},
            ),
        ],
        model="mimo-v2.5-pro",
    )
    out = format_message(msg)
    assert "你好" in out
    assert "search_texts" in out
    assert "坎瑞亚" in out


def test_format_message_ignores_others():
    assert format_message(object()) is None


def test_build_options_disables_claude_code_settings(engine_cfg):
    # 必须显式清空 setting_sources，否则 SDK 不传 --setting-sources，
    # 子进程 CLI 会回落到默认（user/project/local），读取 ~/.claude/settings.json
    # 里的 env（如 ANTHROPIC_BASE_URL 代理）、MCP server、权限等，覆盖本程序的配置。
    opts = AgentRuntime(engine_cfg).build_options()
    assert opts.setting_sources == []


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
                            duration_ms=0, duration_api_ms=0,
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
                            duration_ms=0, duration_api_ms=0,
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
                            duration_ms=0, duration_api_ms=0,
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
