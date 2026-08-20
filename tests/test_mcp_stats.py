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
    assert result["mission_filtered"] == 986
    assert result["book_filtered"] == 90
    assert result["artifact_filtered"] == 61
    assert result["weapon_filtered"] == 234
    assert result["map_text_filtered"] == 653
    assert result["character_filtered"] == 130
