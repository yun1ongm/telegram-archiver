"""CSV 存储后端：每个频道一个文件 <output>/<channel_id>.csv。

启动时把已有 message_id 读入内存做去重；适合中小规模归档与人工查看。
"""

from __future__ import annotations

import csv
from pathlib import Path

from .base import StorageBackend

FIELDS = [
    "channel_id",
    "message_id",
    "time",
    "channel_username",
    "channel_title",
    "body",
    "source",
    "views",
    "forwards",
]


class CSVBackend(StorageBackend):
    def __init__(self, output_dir: str):
        self.dir = Path(output_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._known_ids: dict[int, set[int]] = {}  # channel_id -> message_ids

    def _file_for(self, channel_id: int) -> Path:
        return self.dir / f"{channel_id}.csv"

    def _ids_for(self, channel_id: int) -> set[int]:
        if channel_id not in self._known_ids:
            ids: set[int] = set()
            f = self._file_for(channel_id)
            if f.exists():
                with f.open("r", encoding="utf-8", newline="") as fh:
                    for row in csv.DictReader(fh):
                        try:
                            ids.add(int(row["message_id"]))
                        except (KeyError, ValueError):
                            continue
            self._known_ids[channel_id] = ids
        return self._known_ids[channel_id]

    @staticmethod
    def _row(m: dict) -> dict:
        row = dict(m)
        row["time"] = m["time"].isoformat()
        return {k: row.get(k) for k in FIELDS}

    def insert_messages(self, messages: list[dict]) -> int:
        if not messages:
            return 0
        inserted = 0
        by_channel: dict[int, list[dict]] = {}
        for m in messages:
            by_channel.setdefault(m["channel_id"], []).append(m)

        for channel_id, msgs in by_channel.items():
            known = self._ids_for(channel_id)
            fresh = [m for m in msgs if m["message_id"] not in known]
            if not fresh:
                continue
            f = self._file_for(channel_id)
            write_header = not f.exists() or f.stat().st_size == 0
            with f.open("a", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=FIELDS)
                if write_header:
                    writer.writeheader()
                for m in fresh:
                    writer.writerow(self._row(m))
                    known.add(m["message_id"])
            inserted += len(fresh)
        return inserted

    def get_latest_message_id(self, channel_id: int) -> int:
        ids = self._ids_for(channel_id)
        return max(ids) if ids else 0

    def count_messages(self, channel_id: int | None = None) -> int:
        if channel_id is not None:
            return len(self._ids_for(channel_id))
        total = 0
        for f in self.dir.glob("*.csv"):
            try:
                total += len(self._ids_for(int(f.stem)))
            except ValueError:
                continue
        return total
