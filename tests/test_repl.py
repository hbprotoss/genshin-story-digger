import pytest

pytest.importorskip("claude_agent_sdk")

from claude_agent_sdk.types import AssistantMessage, TextBlock, ToolUseBlock

from config import load_config
from repl import build_options, format_message, sanitize_agent_env


@pytest.fixture()
def cfg():
    from pathlib import Path
    return load_config(Path(__file__).parent / "fixtures" / "config.toml")


def test_build_options_wires_model_env_and_mcp(cfg):
    opts = build_options(cfg)
    assert opts.model == "mimo-v2.5-pro"
    assert opts.env["ANTHROPIC_BASE_URL"] == "https://api.xiaomimimo.com/anthropic"
    assert opts.env["ANTHROPIC_AUTH_TOKEN"] == "sk-test"
    assert opts.permission_mode == "default"
    assert opts.allowed_tools
    assert "mcp__mongo__*" in opts.allowed_tools
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


def test_build_options_disables_claude_code_settings(cfg):
    # 必须显式清空 setting_sources，否则 SDK 不传 --setting-sources，
    # 子进程 CLI 会回落到默认（user/project/local），读取 ~/.claude/settings.json
    # 里的 env（如 ANTHROPIC_BASE_URL 代理）、MCP server、权限等，覆盖本程序的配置。
    opts = build_options(cfg)
    assert opts.setting_sources == []


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
