"""Web 版 agent 后端的运行时层：封装 SDK 的 query/resume、流式转 SSE 事件、
单生成锁、中止单回合、捕获 Write 文档保存。

由 Web 入口（__main__.py / app.py）驱动；这里保留了原 REPL 迁移来的两个纯函数
（sanitize_agent_env / format_message）与 _CLAUDE_CODE_ENV_LEAKS 常量，内容不变。
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import TextBlock, ToolUseBlock

from config import AppConfig
from prompts import MAIN_SYSTEM_PROMPT

_SRC_DIR = Path(__file__).resolve().parent

# 这些环境变量会被 Claude Code（SDK 子进程）读取，从而覆盖 config.toml 的配置：
# 典型残留是上一套 Claude Code 代理留下的 ark-code-latest 模型名。启动 agent
# 前必须清掉，否则主模型/（尤其）sub agent 模型会被指向 OpenRouter 上不存在的模型。
_CLAUDE_CODE_ENV_LEAKS = (
    "ANTHROPIC_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME",
)


def sanitize_agent_env(env: dict[str, str] | None = None) -> None:
    """清掉会覆盖 config.toml 的 Claude Code 环境变量（就地修改）。

    ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN 不在清除之列——它们承载
    config.toml 的值，由 sdk_env() 显式注入。
    """
    target = os.environ if env is None else env
    for key in _CLAUDE_CODE_ENV_LEAKS:
        target.pop(key, None)


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
            new_stop_reason: str | None = None
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
                    if new_stop_reason is None:
                        new_stop_reason = getattr(msg, "stop_reason", None)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                errored = True
                yield {"event": "error", "data": {"message": str(exc)}}
            finally:
                self._tasks.pop(conversation_id, None)
            # 正常收尾（或已发 error）都发 done
            yield {"event": "done", "data": {
                "stop_reason": new_stop_reason, "is_error": errored, "session_id": new_sid,
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
