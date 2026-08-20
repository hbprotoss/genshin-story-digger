import json

import pytest

import mcp_server


@pytest.fixture(scope="module")
def server(mongo_cfg):
    mcp_server.init_client(mongo_cfg.uri(), mongo_cfg.database)
    return mcp_server


def test_get_meta_returns_version_and_parsed_fe_ext(server, db):
    doc = db["mission_filtered"].find_one(
        {"text": {"$regex": "坎瑞亚"}}, {"id": 1}
    )
    r = json.loads(server.get_meta("mission_filtered", doc["id"]))
    assert r["id"] == doc["id"]
    assert "version" in r
    # 大字段被剔除
    assert "menus" not in r and "modules" not in r and "langs" not in r
    # fe_ext 从 JSON 字符串解析成了对象
    fe = r.get("ext", {}).get("fe_ext")
    if fe is not None:
        assert isinstance(fe, dict)


def test_get_meta_missing_returns_error(server):
    r = json.loads(server.get_meta("book_filtered", "nonexistent-99999"))
    assert "error" in r
