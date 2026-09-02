"""FastAPI 应用：REST 端点 + SSE 消息流。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from agent_runtime import AgentRuntime
from config import AppConfig
from conversations import ConversationManager


SSE = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _sse_event(event: dict) -> str:
    data = event.get("data", "")
    if isinstance(data, (dict, list)):
        data = json.dumps(data, ensure_ascii=False)
    return f"event: {event['event']}\ndata: {data}\n\n"


def create_app(cfg: AppConfig, mgr: ConversationManager, rt: AgentRuntime) -> FastAPI:
    app = FastAPI(title="story-digger-web")

    @app.post("/api/conversations")
    def create_conversation(body: dict | None = None):
        title = (body or {}).get("title")
        conv = mgr.create(title=title)
        return {"id": conv.id, "title": conv.title,
                "created_at": conv.created_at, "updated_at": conv.updated_at}

    @app.get("/api/conversations")
    def list_conversations():
        return [{"id": c.id, "title": c.title, "created_at": c.created_at,
                 "updated_at": c.updated_at} for c in mgr.list()]

    @app.get("/api/conversations/{cid}")
    def get_conversation(cid: int):
        conv = mgr.get(cid)
        if conv is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        return {"id": conv.id, "title": conv.title, "created_at": conv.created_at,
                "updated_at": conv.updated_at,
                "messages": [{"id": m.id, "role": m.role, "content": m.content,
                              "kind": m.kind, "meta": m.meta, "created_at": m.created_at}
                             for m in mgr.messages(cid)]}

    @app.post("/api/conversations/{cid}/messages")
    async def send_message(cid: int, body: dict):
        content = (body.get("content") or "").strip()
        if not content:
            raise HTTPException(status_code=400, detail="内容不能为空")
        conv = mgr.get(cid)
        if conv is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        mgr.append_message(cid, "user", content, kind="user")

        async def gen() -> AsyncIterator[str]:
            session_id = conv.agent_session_id
            new_sid = session_id
            pending: list[str] = []          # 累积 assistant 正文
            docs: list[dict] = []
            async for ev in rt.stream_turn(content, cid, session_id):
                data = ev.get("data", {})
                if ev["event"] == "text_delta":
                    pending.append(data.get("text", ""))
                elif ev["event"] == "document_saved":
                    docs.append(data)
                elif ev["event"] == "done":
                    new_sid = data.get("session_id") or new_sid
                yield _sse_event(ev)
            # 回合结束：把累积的 assistant 正文与文档消息写入历史
            if pending:
                mgr.append_message(cid, "assistant", "".join(pending), kind="assistant")
            for d in docs:
                mgr.append_message(cid, "assistant", "", kind="document", meta=d)
            # 持久化最新 agent session_id
            mgr.set_session(cid, new_sid)

        return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE)

    @app.delete("/api/conversations/{cid}")
    def delete_conversation(cid: int):
        if mgr.get(cid) is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        mgr.delete(cid)
        return {"ok": True}

    @app.post("/api/conversations/{cid}/abort")
    def abort_conversation(cid: int):
        rt.abort(cid)
        return {"ok": True}

    @app.get("/api/projects")
    def list_projects():
        out = Path(cfg.agent.output_dir)
        items = []
        if out.is_dir():
            for p in sorted(out.glob("*.md")):
                items.append({"filename": p.name,
                              "size": p.stat().st_size,
                              "mtime": p.stat().st_mtime})
        return items

    @app.get("/api/projects/{filename}")
    def get_project(filename: str):
        out = Path(cfg.agent.output_dir).resolve()
        target = (out / filename).resolve()
        if out != target.parent or not target.is_file():
            raise HTTPException(status_code=404, detail="文档不存在")
        return FileResponse(target, media_type="text/markdown", filename=filename)

    return app
