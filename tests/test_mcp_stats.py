import json

import pytest

pytest.importorskip("fastmcp")

import mcp_server


@pytest.fixture(scope="module")
def server(mongo_cfg):
    mcp_server.init_client(mongo_cfg.uri(), mongo_cfg.database)
    return mcp_server


def test_stats_returns_doc_counts_for_all_six_collections(server):
    result = json.loads(server.stats())
    assert set(result.keys()) == set(mcp_server.COLLECTIONS)
    for c in mcp_server.COLLECTIONS:
        assert isinstance(result[c], int) and result[c] > 0, f"{c} 文档数应为正整数"
