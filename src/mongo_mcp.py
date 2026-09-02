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
    """轮询 streamable-http 端点直到可连（GET 返回非 5xx 即视为就绪）。"""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                return resp.status < 500
        except Exception:
            time.sleep(0.2)
    return False


class MongoMcp:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.proc: subprocess.Popen | None = None

    def start(self) -> None:
        self.proc = subprocess.Popen(
            mcp_cmd(self.cfg),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not wait_http_ready(f"http://127.0.0.1:{self.cfg.web.mcp_port}/mcp"):
            self.stop()
            raise RuntimeError("Mongo MCP server 未能就绪")

    def stop(self) -> None:
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None
