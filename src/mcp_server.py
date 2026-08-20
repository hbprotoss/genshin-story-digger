"""Mongo 检索 MCP server（stdio）。对 MongoDB 纯只读。

由主程序经 claude-agent-sdk 以子进程拉起：
    python mcp_server.py --uri <mongo-uri> --database <db>
"""

from __future__ import annotations

import argparse
import json
import re

from fastmcp import FastMCP
from pymongo import MongoClient

COLLECTIONS = [
    "mission_filtered",
    "book_filtered",
    "artifact_filtered",
    "weapon_filtered",
    "map_text_filtered",
    "character_filtered",
]

mcp = FastMCP("mongo")

_client: MongoClient | None = None
_db = None


def init_client(uri: str, database: str) -> None:
    """建立全局连接；连接失败直接抛异常（启动即验证）。"""
    global _client, _db
    _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    _client.admin.command("ping")  # 连接/认证失败在此抛出
    _db = _client[database]


def db():
    if _db is None:
        raise RuntimeError("Mongo 未初始化：需先调用 init_client()")
    return _db


@mcp.tool()
def stats() -> str:
    """各集合文档数一览，了解数据全貌。"""
    return json.dumps(
        {c: db()[c].estimated_document_count() for c in COLLECTIONS},
        ensure_ascii=False,
    )


def _escape(keyword: str) -> str:
    return re.escape(keyword)


def _snippets_for(text: str, keyword: str, per_keyword: int = 2) -> list[str]:
    """取命中点上下文片段：命中点前 50 字、后 80 字。"""
    out: list[str] = []
    start = 0
    while len(out) < per_keyword:
        i = text.find(keyword, start)
        if i == -1:
            break
        out.append(text[max(0, i - 50): i + 80])
        start = i + len(keyword)
    return out


@mcp.tool()
def search_texts(
    keywords: list[str],
    collections: list[str] | None = None,
    limit: int = 20,
) -> str:
    """跨集合关键词检索（滚雪球主力工具）。

    对各集合的 name 和 text 做关键词包含匹配（多关键词 OR），
    返回 id/名称/命中关键词/文本长度/命中上下文片段，按命中关键词数排序。
    每个集合最多取 limit*3 个候选，total_matched 即候选池内命中数。
    """
    if not keywords:
        return json.dumps({"error": "keywords 不能为空"}, ensure_ascii=False)

    cols = collections or COLLECTIONS
    invalid = [c for c in cols if c not in COLLECTIONS]
    if invalid:
        return json.dumps(
            {"error": f"未知集合: {invalid}，可用: {COLLECTIONS}"}, ensure_ascii=False
        )

    # name/text × keyword 的 OR 条件（re.escape 防正则注入）
    conditions = [
        {field: {"$regex": _escape(k)}}
        for k in keywords
        for field in ("name", "text")
    ]
    match = {"$or": conditions}

    results = []
    total = 0
    for coll in cols:
        per_coll = 0
        for doc in db()[coll].find(match, {"id": 1, "name": 1, "text": 1}):
            total += 1
            per_coll += 1
            text = doc.get("text", "") or ""
            name = doc.get("name", "") or ""
            matched = [k for k in keywords if k in text or k in name]
            snippets: list[str] = []
            for k in matched:
                snippets.extend(_snippets_for(text, k))
                if len(snippets) >= 3:
                    break
            results.append({
                "collection": coll,
                "id": doc["id"],
                "name": name,
                "matched_keywords": matched,
                "text_len": len(text),
                "snippets": snippets[:3],
            })
            # 每个集合最多取 limit*3 个候选，防止超广关键词拉爆内存
            if per_coll >= limit * 3:
                break

    results.sort(key=lambda r: (-len(r["matched_keywords"]), r["name"]))
    results = results[:limit]
    return json.dumps(
        {
            "query": {"keywords": keywords, "collections": cols, "limit": limit},
            "results": results,
            "total_matched": total,
        },
        ensure_ascii=False,
    )


@mcp.tool()
def get_text(collection: str, id: str, offset: int = 0, length: int = 8000) -> str:
    """按 id 取单个文档正文，超长自动分页（默认每页 8000 字）。

    返回 total_len/has_more 标记，需要时用 offset 续读。
    """
    if collection not in COLLECTIONS:
        return json.dumps({"error": f"未知集合: {collection}"}, ensure_ascii=False)
    doc = db()[collection].find_one({"id": id}, {"name": 1, "text": 1})
    if doc is None:
        return json.dumps({"error": f"未找到 {collection}:{id}"}, ensure_ascii=False)
    text = doc.get("text", "") or ""
    chunk = text[offset: offset + length]
    return json.dumps({
        "collection": collection,
        "id": id,
        "name": doc.get("name", ""),
        "total_len": len(text),
        "offset": offset,
        "returned_len": len(chunk),
        "has_more": offset + length < len(text),
        "text": chunk,
    }, ensure_ascii=False)


_META_EXCLUDE = {"_id", "menus", "modules", "langs"}


@mcp.tool()
def get_meta(collection: str, id: str) -> str:
    """查原始集合中的文档元数据（版本号、地区、类型筛选等）。

    mission_filtered -> mission（去掉 _filtered 后缀）。剔除 menus/modules
    等大字段；ext.fe_ext 若为 JSON 字符串则解析为对象。
    """
    raw_coll = collection.removesuffix("_filtered")
    if raw_coll not in {c.removesuffix("_filtered") for c in COLLECTIONS}:
        return json.dumps({"error": f"未知集合: {collection}"}, ensure_ascii=False)
    doc = db()[raw_coll].find_one({"id": id})
    if doc is None:
        return json.dumps({"error": f"未找到 {raw_coll}:{id}"}, ensure_ascii=False)
    meta = {k: v for k, v in doc.items() if k not in _META_EXCLUDE}
    ext = meta.get("ext")
    if isinstance(ext, dict) and isinstance(ext.get("fe_ext"), str):
        try:
            ext["fe_ext"] = json.loads(ext["fe_ext"])
        except json.JSONDecodeError:
            pass
    return json.dumps(meta, ensure_ascii=False, default=str)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mongo 检索 MCP server")
    parser.add_argument("--uri", required=True, help="MongoDB 连接 URI（含 authSource）")
    parser.add_argument("--database", required=True, help="数据库名")
    args = parser.parse_args()
    init_client(args.uri, args.database)
    mcp.run()  # stdio


if __name__ == "__main__":
    main()
