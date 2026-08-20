import json

import pytest

import mcp_server


@pytest.fixture(scope="module")
def server(mongo_cfg):
    mcp_server.init_client(mongo_cfg.uri(), mongo_cfg.database)
    return mcp_server


def _first_id(db_obj, coll):
    return db_obj[coll].find_one({}, {"id": 1})["id"]


def test_get_text_returns_full_small_doc(server, db):
    id_ = _first_id(db, "mission_filtered")
    r = json.loads(server.get_text("mission_filtered", id_))
    assert r["id"] == id_
    assert r["collection"] == "mission_filtered"
    assert r["text"]
    assert r["total_len"] == len(r["text"])
    assert r["has_more"] is False
    assert r["offset"] == 0


def test_get_text_pagination(server, db):
    id_ = _first_id(db, "mission_filtered")
    full = json.loads(server.get_text("mission_filtered", id_))
    page1 = json.loads(server.get_text("mission_filtered", id_, offset=0, length=100))
    page2 = json.loads(server.get_text("mission_filtered", id_, offset=100, length=100))
    assert page1["returned_len"] == 100
    assert page1["has_more"] is True
    assert page1["text"] == full["text"][:100]
    assert page2["text"] == full["text"][100:200]
    assert page2["offset"] == 100


def test_get_text_missing_doc_returns_error(server):
    r = json.loads(server.get_text("mission_filtered", "nonexistent-99999"))
    assert "error" in r
