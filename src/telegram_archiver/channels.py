"""监听频道注册表。

保存在 ~/.telegram-archiver/channels.json（权限 600），
记录频道白名单、是否启用实时监听、历史下载进度（断点续传）。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import get_config_dir


@dataclass
class ChannelEntry:
    channel_id: int
    title: str = ""
    username: str | None = None
    enabled: bool = True  # 实时监听开关
    crawl_history: bool = True  # 允许历史下载
    last_crawled_msg_id: int = 0  # 断点续传进度
    crawl_status: str = "pending"  # pending / running / completed / failed


class ChannelRegistry:
    def __init__(self, path: Path | None = None):
        self.path = path or get_config_dir() / "channels.json"
        self._channels: dict[int, ChannelEntry] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._channels = {
                int(k): ChannelEntry(**v) for k, v in data.get("channels", {}).items()
            }

    def _save(self) -> None:
        payload = {"version": 1, "channels": {str(k): asdict(v) for k, v in self._channels.items()}}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(self.path, 0o600)

    def add(
        self,
        channel_id: int,
        title: str = "",
        username: str | None = None,
        enabled: bool = True,
        crawl_history: bool = True,
    ) -> ChannelEntry:
        entry = self._channels.get(channel_id)
        if entry is None:
            entry = ChannelEntry(
                channel_id=channel_id,
                title=title,
                username=username,
                enabled=enabled,
                crawl_history=crawl_history,
            )
        else:
            entry.title = title or entry.title
            entry.username = username or entry.username
            entry.enabled = enabled
            entry.crawl_history = crawl_history
        self._channels[channel_id] = entry
        self._save()
        return entry

    def remove(self, channel_id: int) -> bool:
        if channel_id in self._channels:
            del self._channels[channel_id]
            self._save()
            return True
        return False

    def set_enabled(self, channel_id: int, enabled: bool) -> bool:
        entry = self._channels.get(channel_id)
        if entry is None:
            return False
        entry.enabled = enabled
        self._save()
        return True

    def get(self, channel_id: int) -> ChannelEntry | None:
        return self._channels.get(channel_id)

    def list(self, enabled_only: bool = False) -> list[ChannelEntry]:
        entries = sorted(self._channels.values(), key=lambda e: e.title.lower())
        return [e for e in entries if e.enabled] if enabled_only else entries

    def to_crawl(self) -> list[ChannelEntry]:
        return [e for e in self.list() if e.crawl_history]

    def update_progress(self, channel_id: int, msg_id: int, status: str | None = None) -> None:
        entry = self._channels.get(channel_id)
        if entry is None:
            return
        entry.last_crawled_msg_id = max(entry.last_crawled_msg_id, msg_id)
        if status:
            entry.crawl_status = status
        self._save()
