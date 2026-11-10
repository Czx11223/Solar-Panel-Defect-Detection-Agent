"""agent_session / agent_message 表数据访问层（DAO，原生sqlite3）。

会话属主隔离：全部查询以 user_id 为过滤条件，与 detect_record 一致。
消息按 OpenAI messages 结构存取：
- assistant 消息的 tool_calls 原样存 JSON（多轮工具循环回传必须完整，
  含 reasoning_content，否则后续工具调用上下文断裂）；
- tool 结果消息单独成行（role=tool，带 tool_call_id）。
"""

from __future__ import annotations

import sqlite3


def create_session(conn: sqlite3.Connection, user_id: int, title: str) -> int:
    cur = conn.execute(
        "INSERT INTO agent_session (user_id, title) VALUES (?, ?)",
        (user_id, title[:100] or "新会话"),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_session(conn: sqlite3.Connection, user_id: int, session_id: int
                ) -> sqlite3.Row | None:
    """属主查询：会话不存在或非本人均返回 None。"""
    return conn.execute(
        "SELECT id, user_id, title, created_at, updated_at "
        "FROM agent_session WHERE id = ? AND user_id = ?",
        (session_id, user_id),
    ).fetchone()


def list_sessions(conn: sqlite3.Connection, user_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT s.id, s.title, s.created_at, s.updated_at,
                  (SELECT COUNT(*) FROM agent_message m
                   WHERE m.session_id = s.id) AS message_count
           FROM agent_session s
           WHERE s.user_id = ?
           ORDER BY s.updated_at DESC, s.id DESC""",
        (user_id,),
    ).fetchall()


def touch_session(conn: sqlite3.Connection, session_id: int) -> None:
    conn.execute(
        "UPDATE agent_session SET updated_at = datetime('now', 'localtime') "
        "WHERE id = ?",
        (session_id,),
    )
    conn.commit()


def delete_session(conn: sqlite3.Connection, user_id: int, session_id: int) -> bool:
    """删除会话及其全部消息（外键级联）。返回是否确实删除。"""
    cur = conn.execute(
        "DELETE FROM agent_session WHERE id = ? AND user_id = ?",
        (session_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def add_message(conn: sqlite3.Connection, session_id: int, *, role: str,
                content: str = "", reasoning: str | None = None,
                tool_calls_json: str | None = None, tool_call_id: str | None = None,
                tool_name: str | None = None,
                tokens_in: int = 0, tokens_out: int = 0) -> int:
    cur = conn.execute(
        """INSERT INTO agent_message
           (session_id, role, content, reasoning, tool_calls_json,
            tool_call_id, tool_name, tokens_in, tokens_out)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, role, content, reasoning, tool_calls_json,
         tool_call_id, tool_name, tokens_in, tokens_out),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_messages(conn: sqlite3.Connection, session_id: int, limit: int
                 ) -> list[sqlite3.Row]:
    """最近 limit 条消息，按时间正序返回（重建 LLM 上下文用）。"""
    rows = conn.execute(
        """SELECT * FROM (
               SELECT * FROM agent_message WHERE session_id = ?
               ORDER BY id DESC LIMIT ?
           ) ORDER BY id ASC""",
        (session_id, limit),
    ).fetchall()
    return rows


def count_messages(conn: sqlite3.Connection, session_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS c FROM agent_message WHERE session_id = ?",
        (session_id,),
    ).fetchone()["c"]
