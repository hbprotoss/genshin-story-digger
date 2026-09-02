import pytest
from pathlib import Path
from pymongo import MongoClient

from config import DEFAULT_CONFIG_PATH, load_config


@pytest.fixture()
def fixtures_cfg() -> Path:
    return Path(__file__).parent / "fixtures" / "config.toml"



@pytest.fixture(scope="session")
def mongo_cfg():
    cfg = load_config(DEFAULT_CONFIG_PATH)
    client = MongoClient(cfg.mongo.uri(), serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
    except Exception:
        pytest.skip("MongoDB 不可达，跳过需要真实库的测试")
    return cfg.mongo


@pytest.fixture(scope="session")
def db(mongo_cfg):
    client = MongoClient(mongo_cfg.uri(), serverSelectionTimeoutMS=3000)
    return client[mongo_cfg.database]
