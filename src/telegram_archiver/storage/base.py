"""存储后端抽象接口。

消息字典统一字段（见 processors.extract_message）：
message_id, channel_id, channel_username, channel_title, time(datetime, UTC),
body, source, views, forwards
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class StorageBackend(ABC):
    @abstractmethod
    def insert_messages(self, messages: list[dict]) -> int:
        """批量写入，自动按 (channel_id, message_id) 去重，返回实际插入条数。"""

    @abstractmethod
    def get_latest_message_id(self, channel_id: int) -> int:
        """该频道已存的最大消息 ID（用于断点续传），无数据返回 0。"""

    @abstractmethod
    def count_messages(self, channel_id: int | None = None) -> int:
        """消息总数（可按频道过滤）。"""

    def close(self) -> None:
        """释放资源（可选实现）。"""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
