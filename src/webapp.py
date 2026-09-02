"""可 reload 的 Web 应用入口（uvicorn --reload / production 共用）。

与 __main__.py 的区别：这里在模块级暴露 `app`，uvicorn 可按导入字符串
"webapp:app" 热加载（改 src/** 后自动重启 worker，MCP 随 lifespan 重启）。
生产也可直接 `uvicorn webapp:app` 或经 __main__.py 复用同一套构建。

配置来源：STORY_DIGGER_CONFIG 环境变量优先，否则默认 ~/.story-digger-agent/config.toml。
"""

from __future__ import annotations

import os

from agent_runtime import AgentRuntime, sanitize_agent_env
from app import create_app
from config import DEFAULT_CONFIG_PATH, load_config
from conversations import ConversationManager
from mongo_mcp import MongoMcp


def load_app_config():
    path = os.environ.get("STORY_DIGGER_CONFIG") or str(DEFAULT_CONFIG_PATH)
    return load_config(path)


def build_app():
    """构建应用：配置加载 + conversation/agent/mcp 组装，MCP 生命周期交给 lifespan。"""
    cfg = load_app_config()
    cfg.agent.output_dir = cfg.agent.output_dir.resolve()
    cfg.agent.output_dir.mkdir(parents=True, exist_ok=True)

    sanitize_agent_env()
    for k, v in cfg.sdk_env().items():
        os.environ[k] = v

    mgr = ConversationManager(cfg.web.db_path)
    rt = AgentRuntime(cfg)
    mcp = MongoMcp(cfg)
    return create_app(cfg, mgr, rt, mcp=mcp)


# uvicorn reload 目标：模块级单例，reload 时整模块被重新 import 而重建。
app = build_app()
