"""user表数据访问层（DAO，原生sqlite3）。

仅做SQL封装与行→dict转换；业务规则（密码校验、查重语义）由路由层/schemas负责。
"""

from __future__ import annotations

import sqlite3
from typing import Any


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    d.pop("password_hash", None)  # 任何对外返回均不含密码哈希
    return d


def create_user(conn: sqlite3.Connection, username: str, password_hash: str,
                email: str | None, nickname: str | None) -> int:
    cur = conn.execute(
        "INSERT INTO user (username, password_hash, email, nickname) VALUES (?, ?, ?, ?)",
        (username, password_hash, email, nickname),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_by_username(conn: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM user WHERE username = ?", (username,)).fetchone()


def get_by_id(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()


def get_by_email(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM user WHERE email = ?", (email,)).fetchone()


def get_or_create_by_cloud(conn: sqlite3.Connection, uid: str,
                           name: str | None, email: str | None) -> sqlite3.Row:
    """云端身份 → 应用内用户（首次访问自动建档）。

    云端 uid 是稳定主键，因此用 username = "wb_<uid>" 做映射键；密码哈希写成
    不可用值（该账号不能走密码登录），昵称/邮箱仅在为空时回填，避免覆盖用户自填资料。
    """
    username = f"wb_{uid}"[:50]
    row = get_by_username(conn, username)
    if row is not None:
        return row
    try:
        conn.execute(
            "INSERT INTO user (username, password_hash, email, nickname) "
            "VALUES (?, ?, ?, ?)",
            (username, "cloud$no-password-login", email, name),
        )
        conn.commit()
    except sqlite3.IntegrityError:  # 并发首登：另一请求已建档
        conn.rollback()
    row = get_by_username(conn, username)
    if row is None:
        raise RuntimeError("云端账号建档失败")
    return row


def update_profile(conn: sqlite3.Connection, user_id: int,
                   nickname: str | None, email: str | None) -> None:
    conn.execute(
        "UPDATE user SET nickname = ?, email = ?, updated_at = datetime('now', 'localtime') "
        "WHERE id = ?",
        (nickname, email, user_id),
    )
    conn.commit()


def update_password(conn: sqlite3.Connection, user_id: int, new_hash: str) -> None:
    conn.execute(
        "UPDATE user SET password_hash = ?, token_version = token_version + 1, "
        "updated_at = datetime('now', 'localtime') WHERE id = ?",
        (new_hash, user_id),
    )
    conn.commit()
