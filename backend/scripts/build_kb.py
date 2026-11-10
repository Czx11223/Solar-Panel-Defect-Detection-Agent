"""知识库构建脚本：把 rag/pv_system_corpus.md 分块入库（幂等）。

分块策略：
- 按二级标题（##）分节，一级标题作为来源上下文保留；
- 单节超过约 800 字时按三级标题（###）拆分；仍超则按段落聚合为 ~600 字块；
- jieba 分词结果存入 keywords 列（空格分隔），BM25 检索直接复用。

运行（在 backend 目录）：
    .venv/Scripts/python.exe scripts/build_kb.py
重复执行安全：先删除同 source 旧分块再插入。
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import jieba  # noqa: E402

from app.db.database import DB_PATH  # noqa: E402
from app.db.init_db import init_db  # noqa: E402

CORPUS_PATH = BACKEND_DIR.parent / "rag" / "pv_system_corpus.md"
SOURCE_NAME = CORPUS_PATH.name
TARGET_LEN = 600   # 目标块长（字）
MAX_LEN = 800      # 超过则继续拆分
_STOP = set(
    "的了和与及或在是为对于将把被从向按按照通过使用以及因此所以如果当其该此这"
    "不没也很更最非常较之其中以外关于由于如下下列以上上述其他其它各种每个所有"
    "任何之内之间等等进行可以需要应当必须一个两个"
)


def _tokenize(text: str) -> str:
    words = jieba.lcut(text)
    keep = [w for w in words if len(w) >= 2 and not re.fullmatch(r"\W+", w)
            and w not in _STOP] or [w for w in words if re.match(r"[\w\d]+", w)]
    return " ".join(dict.fromkeys(keep))


def _split_long(text: str) -> list[str]:
    """超长节按 ### 子标题拆，再按段落聚合到目标长度。"""
    parts = re.split(r"\n(?=###\s)", text)
    if len(parts) > 1:
        return [p.strip() for p in parts if p.strip()]
    # 无子标题：按段落聚合
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    blocks, buf = [], ""
    for p in paragraphs:
        if buf and len(buf) + len(p) > TARGET_LEN:
            blocks.append(buf.strip())
            buf = p
        else:
            buf = f"{buf}\n\n{p}" if buf else p
    if buf.strip():
        blocks.append(buf.strip())
    return blocks


def parse_corpus(md_text: str) -> list[dict]:
    """解析 Markdown → [{heading, content}]。"""
    lines = md_text.splitlines()
    doc_title = ""
    chunks: list[dict] = []
    cur_h2: str | None = None
    buf: list[str] = []

    def flush():
        nonlocal cur_h2, buf
        if cur_h2 is None:
            return
        text = "\n".join(buf).strip()
        buf = []
        if not text:
            return
        pieces = [text] if len(text) <= MAX_LEN else _split_long(text)
        for i, piece in enumerate(pieces):
            heading = cur_h2 if len(pieces) == 1 else f"{cur_h2}（{i + 1}/{len(pieces)}）"
            chunks.append({
                "heading": f"{doc_title} > {heading}".strip(" >"),
                "content": f"# {heading}\n\n{piece}",
            })

    for line in lines:
        if line.startswith("# ") and not line.startswith("## "):
            flush()
            doc_title, cur_h2, buf = line[2:].strip(), None, []
        elif line.startswith("## "):
            flush()
            cur_h2, buf = line[3:].strip(), []
        elif cur_h2 is not None:
            buf.append(line)
    flush()
    return chunks


def build() -> int:
    init_db()
    if not CORPUS_PATH.is_file():
        print(f"语料不存在: {CORPUS_PATH}")
        return 1
    md_text = CORPUS_PATH.read_text(encoding="utf-8")
    chunks = parse_corpus(md_text)
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    try:
        conn.execute("DELETE FROM kb_chunk WHERE source = ?", (SOURCE_NAME,))
        for c in chunks:
            conn.execute(
                "INSERT INTO kb_chunk (source, heading, content, keywords) "
                "VALUES (?, ?, ?, ?)",
                (SOURCE_NAME, c["heading"], c["content"], _tokenize(c["content"])),
            )
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM kb_chunk WHERE source = ?",
                         (SOURCE_NAME,)).fetchone()[0]
        print(f"知识库构建完成：{n} 个分块 <- {CORPUS_PATH}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(build())
