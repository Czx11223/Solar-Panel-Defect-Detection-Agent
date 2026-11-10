"""建库建表初始化（幂等）。

DDL与 docs/db_design.md 完全一致：
- user表：username唯一、email部分唯一索引（IS NOT NULL，选填邮箱不冲突）；
- detect_record表：user_id外键级联删除，(user_id, created_at DESC)复合索引；
- 时间字段由数据库生成东八区本地时间。
"""

from __future__ import annotations

import sqlite3

from .database import DB_PATH

DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS user (
        id            INTEGER       PRIMARY KEY AUTOINCREMENT,
        username      VARCHAR(50)   NOT NULL,
        password_hash VARCHAR(255)  NOT NULL,
        email         VARCHAR(100),
        nickname      VARCHAR(50),
        created_at    DATETIME      NOT NULL DEFAULT (datetime('now', 'localtime')),
        updated_at    DATETIME      NOT NULL DEFAULT (datetime('now', 'localtime')),
        token_version INTEGER       NOT NULL DEFAULT 0
    );
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_user_username ON user (username);
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_user_email ON user (email) WHERE email IS NOT NULL;
    """,
    """
    CREATE TABLE IF NOT EXISTS detect_record (
        id                INTEGER        PRIMARY KEY AUTOINCREMENT,
        user_id           INTEGER        NOT NULL,
        image_name        VARCHAR(255)   NOT NULL,
        image_path        VARCHAR(500)   NOT NULL,
        result_image_path VARCHAR(500),
        detect_result     TEXT           NOT NULL,
        defect_summary    TEXT,
        inference_time_ms REAL,
        model_version     VARCHAR(50)    NOT NULL,
        created_at        DATETIME       NOT NULL DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (user_id) REFERENCES user (id) ON DELETE CASCADE
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_detect_record_user_time
        ON detect_record (user_id, created_at DESC);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_detect_record_created ON detect_record (created_at);
    """,
    # ---- Agent 会话（LLM 智能体）----
    """
    CREATE TABLE IF NOT EXISTS agent_session (
        id         INTEGER      PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER      NOT NULL,
        title      VARCHAR(100) NOT NULL DEFAULT '新会话',
        created_at DATETIME     NOT NULL DEFAULT (datetime('now', 'localtime')),
        updated_at DATETIME     NOT NULL DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (user_id) REFERENCES user (id) ON DELETE CASCADE
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_agent_session_user
        ON agent_session (user_id, updated_at DESC);
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_message (
        id              INTEGER      PRIMARY KEY AUTOINCREMENT,
        session_id      INTEGER      NOT NULL,
        role            VARCHAR(20)  NOT NULL,  -- user / assistant / tool
        content         TEXT         NOT NULL DEFAULT '',
        reasoning       TEXT,                   -- 思维链（K3.1 Pro 始终思考）
        tool_calls_json TEXT,                   -- assistant 发起的工具调用（原样回传）
        tool_call_id    VARCHAR(64),            -- role=tool 时对应的调用ID
        tool_name       VARCHAR(64),            -- role=tool 时工具名
        tokens_in       INTEGER      NOT NULL DEFAULT 0,
        tokens_out      INTEGER      NOT NULL DEFAULT 0,
        created_at      DATETIME     NOT NULL DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (session_id) REFERENCES agent_session (id) ON DELETE CASCADE
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_agent_message_session
        ON agent_message (session_id, id);
    """,
    # ---- 光伏知识库分块（RAG 检索）----
    """
    CREATE TABLE IF NOT EXISTS kb_chunk (
        id         INTEGER      PRIMARY KEY AUTOINCREMENT,
        source     VARCHAR(100) NOT NULL,  -- 来源文件名
        heading    VARCHAR(255) NOT NULL,  -- 所属标题（溯源用）
        content    TEXT         NOT NULL,  -- 分块正文
        keywords   TEXT         NOT NULL DEFAULT '',  -- jieba 分词结果（空格分隔）
        created_at DATETIME     NOT NULL DEFAULT (datetime('now', 'localtime'))
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_kb_chunk_source ON kb_chunk (source);
    """,
]


def init_db() -> None:
    """应用启动时执行：创建数据库文件与全部表/索引（幂等）。"""
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    try:
        # WAL 让读写并发不互相阻塞；该设置持久化在数据库文件中，只需设置一次
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        for stmt in DDL_STATEMENTS:
            conn.execute(stmt)
        # 轻量迁移：兼容本版本之前已存在的数据库文件
        cols = {r[1] for r in conn.execute("PRAGMA table_info(user)")}
        if "token_version" not in cols:
            conn.execute("ALTER TABLE user ADD COLUMN token_version "
                         "INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    finally:
        conn.close()
