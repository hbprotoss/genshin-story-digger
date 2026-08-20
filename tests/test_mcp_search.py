import json

import pytest

import mcp_server


@pytest.fixture(scope="module")
def server(mongo_cfg):
    mcp_server.init_client(mongo_cfg.uri(), mongo_cfg.database)
    return mcp_server


def test_search_finds_known_docs(server):
    r = json.loads(server.search_texts(["坎瑞亚"]))
    assert r["query"]["keywords"] == ["坎瑞亚"]
    assert r["total_matched"] >= 30  # 实测 mission_filtered 命中 37
    assert len(r["results"]) <= 20
    for item in r["results"]:
        assert item["collection"] in mcp_server.COLLECTIONS
        assert item["matched_keywords"] == ["坎瑞亚"]
        assert item["text_len"] > 0


def test_search_multi_keywords_or(server):
    # 两个关键词：命中数应不少于单关键词（OR 语义）
    single = json.loads(server.search_texts(["坎瑞亚"]))["total_matched"]
    both = json.loads(server.search_texts(["坎瑞亚", "黄金王国"]))["total_matched"]
    assert both >= single


def test_search_respects_collections_filter(server):
    r = json.loads(server.search_texts(["坎瑞亚"], collections=["book_filtered"]))
    assert {item["collection"] for item in r["results"]} <= {"book_filtered"}


def test_search_snippets_contain_keyword(server):
    r = json.loads(server.search_texts(["坎瑞亚"], limit=5))
    assert r["results"]
    for item in r["results"]:
        if item["snippets"]:
            assert any("坎瑞亚" in s for s in item["snippets"])


def test_search_no_match_returns_empty(server):
    r = json.loads(server.search_texts(["绝不存在的关键词xyzzy123"]))
    assert r["results"] == []
    assert r["total_matched"] == 0
