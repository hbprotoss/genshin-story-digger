"""Web 入口：拉起常驻 MCP + 启动 uvicorn。"""

from __future__ import annotations

import argparse
import os

import uvicorn

from agent_runtime import AgentRuntime, sanitize_agent_env
from config import DEFAULT_CONFIG_PATH, load_config
from conversations import ConversationManager
from mongo_mcp import MongoMcp


def main() -> None:
    parser = argparse.ArgumentParser(description="Story Digger Agent Web 服务")
    parser.add_argument(
        "--config", default=str(DEFAULT_CONFIG_PATH),
        help="配置文件路径（默认 ~/.story-digger-agent/config.toml）",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    cfg.agent.output_dir = cfg.agent.output_dir.resolve()
    cfg.agent.output_dir.mkdir(parents=True, exist_ok=True)

    sanitize_agent_env()
    for k, v in cfg.sdk_env().items():
        os.environ[k] = v

    mcp = MongoMcp(cfg)
    mcp.start()

    # mcp.start() 之后到 uvicorn.run 结束全部纳入 try/finally，
    # 确保任何构造异常都会触发 mcp.stop() 清理，避免悬挂 MCP 子进程
    try:
        mgr = ConversationManager(cfg.web.db_path)
        rt = AgentRuntime(cfg)

        from app import create_app
        app = create_app(cfg, mgr, rt)

        uvicorn.run(app, host=cfg.web.host, port=cfg.web.port)
    finally:
        mcp.stop()


if __name__ == "__main__":
    main()
