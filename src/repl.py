"""交互式 REPL：claude-agent-sdk 驱动主 Agent，流式输出。"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from claude_agent_sdk.types import TextBlock, ToolUseBlock

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
        if isinstance(block, TextBlock):
            parts.append(block.text)
        elif isinstance(block, ToolUseBlock):
            brief = ", ".join(f"{k}={v!r}" for k, v in list(block.input.items())[:3])
            parts.append(f"⟐ {block.name}({brief})")
    return "\n".join(p for p in parts if p) or None


async def run_repl(cfg: AppConfig) -> None:
    options = build_options(cfg)
    client = ClaudeSDKClient(options=options)
    await client.connect()
    print(
        f"已连接。故事挖掘员就绪（模型 {cfg.chat.model}）。"
        "输入故事线关键词开始，exit/quit 退出。"
    )
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
