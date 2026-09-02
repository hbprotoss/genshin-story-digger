"""MongoMcp.start() 就绪探测与错误上报行为测试。

不依赖真实 MongoDB：构造一个必然起不来（会立刻崩溃）的子进程命令，
断言 start() 抛出的 RuntimeError 携带了子进程的真实 stderr，而不是
泛化的"未能就绪"超时信息。
"""

import os
import subprocess
import sys

import pytest

from config import AppConfig, ChatConfig, MongoConfig
from mongo_mcp import MongoMcp


def _make_cfg() -> AppConfig:
    return AppConfig(
        mongo=MongoConfig(
            host="127.0.0.1", port=27017, database="x",
            username="u", password="p",
        ),
        chat=ChatConfig(base_url="http://x", api_key="k", model="m"),
    )


def test_start_reports_child_crash_stderr(monkeypatch):
    """子进程立刻崩溃（退出非零）时，start() 抛出带真实 stderr 的 RuntimeError。"""
    cfg = _make_cfg()
    mcp = MongoMcp(cfg)

    # 让子进程打印一行错误后立刻非零退出 —— 模拟 fastmcp 缺失等启动失败。
    script = (
        "import sys, os\n"
        "print('BOOM: pretend fastmcp/init failure', file=sys.stderr)\n"
        "sys.exit(3)\n"
    )
    fake_cmd = [sys.executable, "-c", script]

    monkeypatch.setattr("mongo_mcp.mcp_cmd", lambda cfg: fake_cmd)
    monkeypatch.setattr("mongo_mcp.wait_http_ready", lambda *a, **k: False)

    with pytest.raises(RuntimeError) as ei:
        mcp.start()

    msg = str(ei.value)
    assert "未能就绪" in msg
    assert "BOOM" in msg, f"期望异常携带子进程 stderr，实得: {msg!r}"
