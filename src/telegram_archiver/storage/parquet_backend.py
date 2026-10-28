"""Parquet 存储后端（需要 pyarrow：pip install 'telegram-archiver[parquet]'）。

目录布局：<output>/<channel_id>/part-000001.parquet、part-000002.parquet ...
每积累 _FLUSH_EVERY 条消息写出一个 part 文件；读取时用 pandas/pyarrow
直接读整个 <channel_id> 目录即可（pyarrow 支持目录数据集）。
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .base import StorageBackend

SCHEMA = pa.schema(
    [
        ("channel_id", pa.int64()),
        ("message_id", pa.int64()),
        ("time", pa.timestamp("us", tz="UTC")),
        ("channel_username", pa.string()),
        ("channel_title", pa.string()),
        ("body", pa.string()),
        ("source", pa.string()),
        ("views", pa.int64()),
        ("forwards", pa.int64()),
    ]
)

_FLUSH_EVERY = 2000


class ParquetBackend(StorageBackend):
    def __init__(self, output_dir: str):
        self.dir = Path(output_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._known_ids: dict[int, set[int]] = {}
        self._buffers: dict[int, list[dict]] = {}
        self._part_counters: dict[int, int] = {}

    def _dir_for(self, channel_id: int) -> Path:
        d = self.dir / str(channel_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _ids_for(self, channel_id: int) -> set[int]:
        if channel_id not in self._known_ids:
            ids: set[int] = set()
            for f in sorted(self._dir_for(channel_id).glob("part-*.parquet")):
                table = pq.read_table(f, columns=["message_id"])
                ids.update(table.column("message_id").to_pylist())
            self._known_ids[channel_id] = ids
        return self._known_ids[channel_id]

    def insert_messages(self, messages: list[dict]) -> int:
        inserted = 0
        for m in messages:
            known = self._ids_for(m["channel_id"])
            if m["message_id"] in known:
                continue
            known.add(m["message_id"])
            self._buffers.setdefault(m["channel_id"], []).append(m)
            inserted += 1
            if len(self._buffers[m["channel_id"]]) >= _FLUSH_EVERY:
                self._flush(m["channel_id"])
        return inserted

    def _next_part_path(self, channel_id: int) -> Path:
        d = self._dir_for(channel_id)
        if channel_id not in self._part_counters:
            existing = sorted(d.glob("part-*.parquet"))
            self._part_counters[channel_id] = len(existing)
        self._part_counters[channel_id] += 1
        return d / f"part-{self._part_counters[channel_id]:06d}.parquet"

    def _flush(self, channel_id: int) -> None:
        buf = self._buffers.get(channel_id)
        if not buf:
            return
        table = pa.Table.from_pylist(
            [{k: m.get(k) for k in SCHEMA.names} for m in buf], schema=SCHEMA
        )
        pq.write_table(table, self._next_part_path(channel_id), compression="zstd")
        self._buffers[channel_id] = []

    def flush_all(self) -> None:
        for channel_id in list(self._buffers):
            self._flush(channel_id)

    def get_latest_message_id(self, channel_id: int) -> int:
        ids = self._ids_for(channel_id)
        buffered = [m["message_id"] for m in self._buffers.get(channel_id, [])]
        all_ids = ids | set(buffered)
        return max(all_ids) if all_ids else 0

    def count_messages(self, channel_id: int | None = None) -> int:
        if channel_id is not None:
            return len(self._ids_for(channel_id))
        total = 0
        for d in self.dir.iterdir():
            if d.is_dir() and d.name.isdigit():
                total += len(self._ids_for(int(d.name)))
        return total

    def close(self) -> None:
        self.flush_all()
