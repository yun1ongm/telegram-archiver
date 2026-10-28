"""数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CrawlResult:
    """单次频道历史下载的结果。"""

    channel_id: int
    channel_title: str = ""
    total_fetched: int = 0
    total_inserted: int = 0
    last_msg_id: int = 0
    errors: list[str] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None

    @property
    def duration(self) -> float:
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()

    @property
    def success_rate(self) -> float:
        return self.total_inserted / self.total_fetched if self.total_fetched else 0.0
