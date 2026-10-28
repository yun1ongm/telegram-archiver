"""SQLite 存储后端（默认，零配置，标准库实现）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .base import StorageBackend

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    channel_id       INTEGER NOT NULL,
    message_id       INTEGER NOT NULL,
    time             TEXT NOT NULL,
    channel_username TEXT,
    channel_title    TEXT,
    body             TEXT,
    source           TEXT,
    views            INTEGER,
    forwards         INTEGER,
    PRIMARY KEY (channel_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_time ON messages(time);
"""

_INSERT = """
INSERT OR IGNORE INTO messages
    (channel_id, message_id, time, channel_username, channel_title,
     body, source, views, forwards)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class SQLiteBackend(StorageBackend):
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.executescript(_SCHEMA)

    @staticmethod
    def _row(m: dict) -> tuple:
        return (
            m["channel_id"],
            m["message_id"],
            m["time"].isoformat(),
            m.get("channel_username"),
            m.get("channel_title"),
            m.get("body"),
            m.get("source"),
            m.get("views"),
            m.get("forwards"),
        )

    def insert_messages(self, messages: list[dict]) -> int:
        if not messages:
            return 0
        before = self.conn.total_changes
        self.conn.executemany(_INSERT, [self._row(m) for m in messages])
        self.conn.commit()
        return self.conn.total_changes - before

    def get_latest_message_id(self, channel_id: int) -> int:
        row = self.conn.execute(
            "SELECT MAX(message_id) FROM messages WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def count_messages(self, channel_id: int | None = None) -> int:
        if channel_id is None:
            row = self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) FROM messages WHERE channel_id = ?", (channel_id,)
            ).fetchone()
        return int(row[0])

    def iter_messages(self, channel_id: int | None = None, batch_size: int = 5000):
        """导出用：按 channel_id, message_id 升序流式读取。"""
        sql = (
            "SELECT channel_id, message_id, time, channel_username, channel_title,"
            " body, source, views, forwards FROM messages"
        )
        params: tuple = ()
        if channel_id is not None:
            sql += " WHERE channel_id = ?"
            params = (channel_id,)
        sql += " ORDER BY channel_id, message_id"
        cur = self.conn.execute(sql, params)
        cols = [d[0] for d in cur.description]
        while True:
            rows = cur.fetchmany(batch_size)
            if not rows:
                break
            yield [dict(zip(cols, r)) for r in rows]

    def close(self) -> None:
        self.conn.close()
