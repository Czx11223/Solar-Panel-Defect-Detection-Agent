"""SQLite连接与会话管理。

关键设计（D30：原生sqlite3，不引入ORM）：
- 每请求独立连接（FastAPI依赖注入），请求结束自动关闭，避免线程间连接共享；
- 每个连接开启外键约束 PRAGMA foreign_keys=ON（SQLite默认关闭，db_design.md约定）；
- 行以sqlite3.Row返回，支持按列名访问。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..core.config import DATA_DIR


def _ensure_db_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / "pv_defect.db"


DB_PATH = _ensure_db_dir()


def get_conn():
    """FastAPI依赖：提供独立数据库连接，请求结束后关闭。

    用法：def route(conn: sqlite3.Connection = Depends(get_conn)):
    """
    # async路由在线程池线程创建连接、事件循环线程使用，须关闭SQLite线程检查；
    # 每请求独立连接+用完即关，不存在跨请求共享，check_same_thread=False安全
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
    finally:
        conn.close()
