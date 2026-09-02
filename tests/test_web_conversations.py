"""ConversationManager + SQLite 持久化测试。"""

import json
from pathlib import Path

import pytest

from conversations import ConversationManager


@pytest.fixture()
def mgr(tmp_path: Path) -> ConversationManager:
    return ConversationManager(tmp_path / "test.db")


def test_create_and_get(mgr):
    conv = mgr.create("渊下宫")
    assert conv.id > 0
    assert conv.title == "渊下宫"
    got = mgr.get(conv.id)
    assert got is not None and got.id == conv.id


def test_list_sorted_by_updated(mgr):
    a = mgr.create("甲")
    b = mgr.create("乙")
    assert len(mgr.list()) == 2
    assert {c.id for c in mgr.list()} == {a.id, b.id}


def test_append_and_messages(mgr):
    conv = mgr.create()
    user = mgr.append_message(conv.id, "user", "渊下", kind="user")
    ai = mgr.append_message(conv.id, "assistant", "你好，", meta={"stop": "plan"})
    msgs = mgr.messages(conv.id)
    assert [m.kind for m in msgs] == ["user", "assistant"]
    assert msgs[1].meta == {"stop": "plan"}


def test_append_document_message(mgr):
    conv = mgr.create()
    doc = mgr.append_message(conv.id, "assistant", "", kind="document",
                             meta={"filename": "渊下.md"})
    assert doc.kind == "document"
    assert json.loads(doc.meta)["filename"] == "渊下.md" if isinstance(doc.meta, str) else doc.meta["filename"] == "渊下.md"


def test_persists_across_reopen(mgr, tmp_path):
    conv = mgr.create("纳西妲")
    mgr.append_message(conv.id, "user", "纳西妲")
    mgr2 = ConversationManager(tmp_path / "test.db")
    assert mgr2.get(conv.id) is not None
    assert len(mgr2.messages(conv.id)) == 1


def test_set_session_id(mgr):
    conv = mgr.create()
    mgr.set_session(conv.id, "sess-abc")
    assert mgr.get(conv.id).agent_session_id == "sess-abc"
    mgr.set_session(conv.id, None)
    assert mgr.get(conv.id).agent_session_id is None


def test_delete(mgr):
    conv = mgr.create()
    mgr.delete(conv.id)
    assert mgr.get(conv.id) is None
    assert mgr.messages(conv.id) == []
