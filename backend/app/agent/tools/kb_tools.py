"""知识库检索工具：search_knowledge（BM25，零外部服务依赖）。

索引管理：进程内缓存，首次调用时从 kb_chunk 表构建；
表内容变化（重新运行 scripts/build_kb.py）后通过 row count 校验自动重建。
语料为空时返回明确提示，模型会引导用户先构建知识库。
"""

from __future__ import annotations

import sqlite3
import threading
from typing import Any

from ...core.config import settings
from . import tool

_lock = threading.Lock()
_cache: dict = {"count": -1, "bm25": None, "chunks": []}


def _ensure_index(conn: sqlite3.Connection) -> bool:
    """构建/复用 BM25 索引。返回知识库是否非空。"""
    rows = conn.execute(
        "SELECT id, heading, source, content, keywords FROM kb_chunk ORDER BY id"
    ).fetchall()
    with _lock:
        if len(rows) == _cache["count"] and _cache["bm25"] is not None:
            return bool(rows)
        from rank_bm25 import BM25Okapi

        corpus = [r["keywords"].split() for r in rows]
        _cache["bm25"] = BM25Okapi(corpus) if rows else None
        _cache["chunks"] = [dict(r) for r in rows]
        _cache["count"] = len(rows)
    return bool(rows)


def _query_tokens(query: str) -> list[str]:
    import jieba

    return [w for w in jieba.lcut(query) if len(w.strip()) >= 2]


@tool(
    "search_knowledge",
    "检索光伏项目知识库（系统架构、算法指标、接口、部署运维等文档语料），"
    "回答项目相关专业问题时优先使用。",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索问题或关键词"},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
)
def search_knowledge(conn: sqlite3.Connection, user: dict, query: str
                     ) -> dict[str, Any]:
    if not query.strip():
        return {"error": "检索词不能为空"}
    if not _ensure_index(conn):
        return {"empty": True,
                "note": "知识库为空，请先在 backend 目录运行 scripts/build_kb.py 构建"}
    tokens = _query_tokens(query)
    if not tokens:
        return {"empty": True, "note": "检索词分词后为空"}
    with _lock:
        scores = _cache["bm25"].get_scores(tokens)
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        top_k = max(1, min(settings.kb_top_k, len(order)))
        hits = []
        for i in order[:top_k]:
            if scores[i] <= 0:
                continue
            c = _cache["chunks"][i]
            hits.append({
                "heading": c["heading"],
                "source": c["source"],
                "score": round(float(scores[i]), 3),
                "content": c["content"][:1200],
            })
    if not hits:
        return {"empty": True, "note": "知识库中未检索到相关内容"}
    return {"results": hits, "note": "引用时注明 heading 来源"}
