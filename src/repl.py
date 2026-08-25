"""交互式 REPL：claude-agent-sdk 驱动主 Agent，流式输出。

使用一次性 query() 每回合调用 + session resume 实现多轮延续。
这一模型在此端点下 ClaudeSDKClient 的 connect/query 多轮交互不稳定，
而 query() 路径经实测可靠。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import replace
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import TextBlock, ToolUseBlock
from prompt_toolkit.shortcuts import PromptSession

from config import AppConfig, DEFAULT_CONFIG_PATH, load_config
from prompts import MAIN_SYSTEM_PROMPT

_SRC_DIR = Path(__file__).resolve().parent


def build_options(cfg: AppConfig) -> ClaudeAgentOptions:
    system_prompt = (
        MAIN_SYSTEM_PROMPT
        .replace("{max_subagents}", str(cfg.agent.max_subagents))
        .replace("{output_dir}", str(cfg.agent.output_dir).rstrip("/") + "/")
    )
    return ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=cfg.chat.model,
        # root 下 claude CLI 硬性拒绝 --dangerously-skip-permissions，故不用
        # bypassPermissions；改用工具白名单让 agent 可写文件、派发 subagent、
        # 用本项目的 MCP 工具，而不触发该 guard。
        permission_mode="default",
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
        # debug_llm 开启时将 SDK 调试日志写入 stderr
        **({} if not cfg.chat.debug_llm else {"debug_stderr": sys.stderr}),
    )


def format_message(msg) -> str | None:
    """把 SDK 消息转成要打印的文本；不需要打印的返回 None。"""
    content = getattr(msg, "content", None)
    if not content:
        return None
    parts: list[str] = []
    for block in content:
        if isinstance(block, TextBlock):
            parts.append(block.text)
        elif isinstance(block, ToolUseBlock):
            brief = ", ".join(f"{k}={v!r}" for k, v in list(block.input.items())[:3])
            parts.append(f"⟐ {block.name}({brief})")
    return "\n".join(p for p in parts if p) or None


async def _run_turn(prompt: str, opts: ClaudeAgentOptions, sid: str | None) -> tuple[str | None, bool]:
    """执行一回合 query，返回 (new_session_id, interrupted)。"""
    turn_opts = replace(opts, resume=sid) if sid else opts
    new_sid = sid
    interrupted = False
    try:
        async for msg in query(prompt=prompt, options=turn_opts):
            text = format_message(msg)
            if text:
                print(text)
            if new_sid is None:
                new_sid = getattr(msg, "session_id", None)
    except (KeyboardInterrupt, asyncio.CancelledError):
        interrupted = True
        print("\n（已打断本轮）")
    except Exception as exc:  # LLM API 失败等：报告但保留会话
        print(f"\n[出错] {exc}\n（会话保留，可重试）")
    return new_sid, interrupted


async def run_repl(cfg: AppConfig) -> None:
    # 注入模型端点环境变量到当前进程，SDK 子进程会继承。
    # opts.env 理论上也能传，但 SDK 的 env 合并逻辑与父进程已有
    # ANTHROPIC_BASE_URL 交互时不可靠；直接设 os.environ 确保生效。
    for k, v in cfg.sdk_env().items():
        os.environ[k] = v

    options = build_options(cfg)
    ps = PromptSession()
    print(
        f"故事挖掘员就绪（模型 {cfg.chat.model}）。"
        "输入故事线关键词开始，exit/quit 退出。"
    )
    session_id: str | None = None
    try:
        while True:
            try:
                user_input = (await ps.prompt_async("你> ")).strip()
            except EOFError:
                print("\n再见！")
                break
            if not user_input:
                continue
            if user_input in {"exit", "quit"}:
                break
            session_id, _ = await _run_turn(user_input, options, session_id)
    except KeyboardInterrupt:
        print("\n再见！")


def main() -> None:
    parser = argparse.ArgumentParser(description="原神故事线挖掘 agent")
    parser.add_argument(
        "--config", default=str(DEFAULT_CONFIG_PATH),
        help="配置文件路径（默认 /root/.story-digger-agent/config.toml）",
    )
    args = parser.parse_args()
    cfg = load_config(args.config)
    # 将相对路径转绝对，避免 agent 的 Write 工具写到意料之外的目录
    cfg.agent.output_dir = cfg.agent.output_dir.resolve()
    cfg.agent.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"输出目录：{cfg.agent.output_dir}")
    asyncio.run(run_repl(cfg))