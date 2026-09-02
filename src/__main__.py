"""Web 入口：拉起常驻 MCP + 启动 uvicorn（生产 / 开发热加载）。"""

from __future__ import annotations

import argparse
import os

import uvicorn

from config import DEFAULT_CONFIG_PATH, load_config
from webapp import build_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Story Digger Agent Web 服务")
    parser.add_argument(
        "--config", default=str(DEFAULT_CONFIG_PATH),
        help="配置文件路径（默认 ~/.story-digger-agent/config.toml）",
    )
    parser.add_argument(
        "--dev", action="store_true",
        help="开发模式：uvicorn 开启 --reload，改 src/** 后自动热重启",
    )
    args = parser.parse_args()

    # 统一走 webapp.build_app()（同一套 lifespan 单入口），MCP 生命周期由
    # lifespan 管理。reload 依赖"可导入"的 app，dev 用 "webapp:app" 字符串。
    if args.dev:
        os.environ.setdefault("STORY_DIGGER_CONFIG", args.config)
        uvicorn.run(
            "webapp:app",
            app_dir=os.path.dirname(os.path.abspath(__file__)),
            reload=True,
            reload_dirs=[os.path.dirname(os.path.abspath(__file__))],
            host="127.0.0.1",
            port=8080,
            log_level="info",
        )
        return

    # 生产模式：直接启动（无 reload）。
    cfg = load_config(args.config)
    os.environ.setdefault("STORY_DIGGER_CONFIG", args.config)
    app = build_app()
    uvicorn.run(app, host=cfg.web.host, port=cfg.web.port)


if __name__ == "__main__":
    main()
