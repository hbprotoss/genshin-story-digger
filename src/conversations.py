"""会话与消息的 SQLite 持久化。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Message:
    id: int
    conversation_id: int
    role: str
    content: str
    kind: str
    meta: dict = field(default_factory=dict)
    created_at: str = ""


@dataclass
class Conversation:
    id: int
    title: str
    created_at: str = ""
    updated_at: str = ""
    agent_session_id: str | None = None


_ROW_CONV = '"id", title, created_at, updated_at, agent_session_id'
_ROW_MSG = '"id", conversation_id, role, content, kind, meta, created_at'


class ConversationManager:
    def __init__(self, db_path: Path | str):
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False：连接可能被 FastAPI 线程池中的不同线程复用
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '',
                owner TEXT NOT NULL DEFAULT 'local',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                agent_session_id TEXT
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'assistant',
                meta TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """
        )
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.commit()

    def create(self, title: str | None = None) -> Conversation:
        now = _now()
        cur = self._conn.execute(
            "INSERT INTO conversations (title, created_at, updated_at) VALUES (?, ?, ?)",
            (title or "", now, now),
        )
        self._conn.commit()
        return self.get(cur.lastrowid)  # type: ignore[return-value]

    def list(self) -> list[Conversation]:
        rows = self._conn.execute(
            f"SELECT {_ROW_CONV} FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
        return [self._conv(r) for r in rows]

    def get(self, conversation_id: int) -> Conversation | None:
        row = self._conn.execute(
            f"SELECT {_ROW_CONV} FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        return self._conv(row) if row else None

    def set_session(self, conversation_id: int, agent_session_id: str | None) -> None:
        self._conn.execute(
            "UPDATE conversations SET agent_session_id = ? WHERE id = ?",
            (agent_session_id, conversation_id),
        )
        self.touch(conversation_id)
        self._conn.commit()

    def touch(self, conversation_id: int) -> None:
        self._conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (_now(), conversation_id),
        )
        self._conn.commit()

    def append_message(
        self, conversation_id: int, role: str, content: str,
        kind: str = "assistant", meta: dict | None = None,
    ) -> Message:
        now = _now()
        cur = self._conn.execute(
            "INSERT INTO messages (conversation_id, role, content, kind, meta, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (conversation_id, role, content, kind, json.dumps(meta or {}, ensure_ascii=False), now),
        )
        self.touch(conversation_id)
        self._conn.commit()
        row = self._conn.execute(
            f"SELECT {_ROW_MSG} FROM messages WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return self._msg(row)

    def messages(self, conversation_id: int) -> list[Message]:
        rows = self._conn.execute(
            f"SELECT {_ROW_MSG} FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
        return [self._msg(r) for r in rows]

    def delete(self, conversation_id: int) -> None:
        self._conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        self._conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        self._conn.commit()

    @staticmethod
    def _conv(row: sqlite3.Row) -> Conversation:
        return Conversation(
            id=row["id"], title=row["title"], created_at=row["created_at"],
            updated_at=row["updated_at"], agent_session_id=row["agent_session_id"],
        )

    @staticmethod
    def _msg(row: sqlite3.Row) -> Message:
        return Message(
            id=row["id"], conversation_id=row["conversation_id"], role=row["role"],
            content=row["content"], kind=row["kind"],
            meta=json.loads(row["meta"]) if row["meta"] else {},
            created_at=row["created_at"],
        )
