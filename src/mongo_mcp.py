"""常驻 Mongo MCP 子进程生命周期（streamable-http）。"""

from __future__ import annotations

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
    """轮询 streamable-http 端点直到可连。

    用 TCP 连接探测：FastMCP 的 streamable-http 端点 /mcp 对非 MCP 手法的
    普通请求会返回 4xx（如 406），直接依赖 HTTP 状态码会误判"未就绪"。
    只要能建立 TCP 连接即视为进程已在监听、服务就绪。
    """
    from urllib.parse import urlparse
    host, port = urlparse(url).hostname, urlparse(url).port
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            import socket
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.2)
    return False


class MongoMcp:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.proc: subprocess.Popen | None = None

    def start(self, ready_timeout: float = 10.0) -> None:
        """拉起 MCP 子进程并等待就绪；失败时抛出携带真实原因的 RuntimeError。

        子进程的 stderr 被捕获（而非丢弃）并写回控制台，一旦子进程提前
        退出（如缺依赖 / 初始化失败），立刻用其退出码与 stderr 报错，
        而不是干等超时后只给一句泛化的"未能就绪"。
        """
        url = f"http://127.0.0.1:{self.cfg.web.mcp_port}/mcp"
        self.proc = subprocess.Popen(
            mcp_cmd(self.cfg),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        deadline = time.time() + ready_timeout
        while time.time() < deadline:
            # 子进程已崩溃/提前退出：立即携带真实 stderr 抛出，省去干等。
            if self.proc.poll() is not None:
                self._raise_start_failure("子进程提前退出")

            if wait_http_ready(url, timeout=0.5):
                return

        self._raise_start_failure(f"{ready_timeout:.0f} 秒内未就绪")

    def _raise_start_failure(self, why: str) -> None:
        assert self.proc is not None
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        stderr = (self.proc.stderr.read().decode(errors="replace") if self.proc.stderr else "").strip()
        self.proc = None
        reason = stderr or why
        raise RuntimeError(
            f"Mongo MCP server 未能就绪（{why}）"
            + (f"；子进程 stderr：\n{reason}" if reason else "")
        )

    def stop(self) -> None:
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None
