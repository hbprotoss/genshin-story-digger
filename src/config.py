"""读取 /root/.story-digger-agent/config.toml，映射为运行时配置。"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote_plus

DEFAULT_CONFIG_PATH = Path("~/.story-digger-agent/config.toml").expanduser()


@dataclass
class MongoConfig:
    host: str
    port: int
    database: str
    username: str
    password: str
    auth_source: str = "admin"

    def uri(self) -> str:
        # 认证库必须是 admin（super 用户建在 admin 下）；
        # URI 不指定目标库，用 client[database] 按名取库
        return (
            f"mongodb://{quote_plus(self.username)}:{quote_plus(self.password)}"
            f"@{self.host}:{self.port}/?authSource={self.auth_source}"
        )


@dataclass
class ChatConfig:
    base_url: str
    api_key: str
    model: str
    # 注：claude-agent-sdk / claude CLI 不暴露 temperature，此字段仅保留
    # 在配置里以备将来支持，当前实现会忽略它。
    temperature: float = 0.2
    stream: bool = True
    debug_llm: bool = False


@dataclass
class AgentConfig:
    output_dir: Path = Path("./output")
    max_subagents: int = 5


@dataclass
class AppConfig:
    mongo: MongoConfig
    chat: ChatConfig
    agent: AgentConfig = field(default_factory=AgentConfig)

    def sdk_env(self) -> dict[str, str]:
        return {
            "ANTHROPIC_BASE_URL": self.chat.base_url,
            "ANTHROPIC_AUTH_TOKEN": self.chat.api_key,
        }


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> AppConfig:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    agent_data = data.get("agent", {})
    return AppConfig(
        mongo=MongoConfig(**data["mongo"]),
        chat=ChatConfig(**data["chat"]),
        agent=AgentConfig(
            output_dir=Path(agent_data.get("output_dir", "./output")),
            max_subagents=agent_data.get("max_subagents", 5),
        ),
    )
