from pathlib import Path

from config import AppConfig, AgentConfig, ChatConfig, MongoConfig, load_config

FIXTURE = Path(__file__).parent / "fixtures" / "config.toml"


def test_load_config_parses_all_sections():
    cfg = load_config(FIXTURE)
    assert isinstance(cfg, AppConfig)
    assert cfg.mongo == MongoConfig(
        host="localhost", port=27017, database="mihoyo",
        username="super", password="testpass", auth_source="admin",
    )
    assert cfg.chat == ChatConfig(
        base_url="https://api.xiaomimimo.com/anthropic",
        api_key="sk-test", model="mimo-v2.5-pro",
        temperature=0.2, stream=True, debug_llm=True,
    )
    assert cfg.agent == AgentConfig(
        output_dir=Path("/tmp/story-digger-test-output"), max_subagents=3,
    )


def test_mongo_uri_contains_auth_source():
    cfg = load_config(FIXTURE)
    assert cfg.mongo.uri() == "mongodb://super:testpass@localhost:27017/?authSource=admin"


def test_sdk_env_maps_anthropic_vars():
    cfg = load_config(FIXTURE)
    assert cfg.sdk_env() == {
        "ANTHROPIC_BASE_URL": "https://api.xiaomimimo.com/anthropic",
        "ANTHROPIC_AUTH_TOKEN": "sk-test",
    }


def test_agent_section_is_optional(tmp_path):
    # 无 [agent] 段时用默认值
    path = tmp_path / "cfg.toml"
    path.write_text(
        "[mongo]\nhost='h'\nport=1\ndatabase='d'\nusername='u'\npassword='p'\n"
        "[chat]\nbase_url='http://x'\napi_key='k'\nmodel='m'\n",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.agent.max_subagents == 5
    assert cfg.agent.output_dir == Path("./output")
