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
