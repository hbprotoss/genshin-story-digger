"""[web] 配置段解析测试。"""

from pathlib import Path

from config import AppConfig, load_config


def test_load_web_config_defaults(fixtures_cfg: Path):
    cfg = load_config(fixtures_cfg)
    assert cfg.web.port == 8080
    assert cfg.web.mcp_port == 9100
    assert cfg.web.db_path == Path("/tmp/story-digger-test.db")


def test_sdk_env_unchanged(fixtures_cfg: Path):
    cfg = load_config(fixtures_cfg)
    assert cfg.sdk_env() == {
        "ANTHROPIC_BASE_URL": "https://api.xiaomimimo.com/anthropic",
        "ANTHROPIC_AUTH_TOKEN": "sk-test",
    }
