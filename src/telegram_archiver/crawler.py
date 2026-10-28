"""历史消息下载器：批量拉取频道历史，支持断点续传与限流重试。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from telethon import TelegramClient
from telethon.errors import ChannelPrivateError, FloodWaitError

from .channels import ChannelRegistry
from .models import CrawlResult
from .processors import extract_message, should_process
from .storage import StorageBackend

logger = logging.getLogger("telegram_archiver.crawler")


class HistoryCrawler:
    def __init__(
        self,
        client: TelegramClient,
        storage: StorageBackend,
        registry: ChannelRegistry | None = None,
        batch_size: int = 100,
        rate_limit_delay: float = 1.0,
        max_retries: int = 3,
    ):
        self.client = client
        self.storage = storage
        self.registry = registry
        self.batch_size = min(batch_size, 100)  # Telegram 单次最多 100
        self.rate_limit_delay = rate_limit_delay
        self.max_retries = max_retries

    async def crawl_channel(
        self,
        channel_ref: str | int,
        limit: int | None = None,
        incremental: bool = False,
    ) -> CrawlResult:
        """下载单个频道历史消息。

        Args:
            channel_ref: 频道用户名（@name）、链接或数字 ID
            limit: 最多下载条数（None = 全部）
            incremental: True 时从注册表记录的上次进度继续（增量更新）
        """
        entity = await self.client.get_entity(_parse_ref(channel_ref))
        title = getattr(entity, "title", str(channel_ref))
        result = CrawlResult(channel_id=entity.id, channel_title=title)

        offset_id = 0
        if incremental and self.registry:
            entry = self.registry.get(entity.id)
            saved = entry.last_crawled_msg_id if entry else 0
            offset_id = max(saved, self.storage.get_latest_message_id(entity.id))

        logger.info(
            "开始下载 %s (ID: %s)，模式: %s，起点: %s",
            title, entity.id, "增量" if incremental else "全量", offset_id,
        )
        if self.registry:
            self.registry.update_progress(entity.id, offset_id, status="running")

        retry = 0
        try:
            while True:
                try:
                    if incremental:
                        messages = await self.client.get_messages(
                            entity, limit=self.batch_size, min_id=offset_id, reverse=True
                        )
                    else:
                        messages = await self.client.get_messages(
                            entity, limit=self.batch_size, offset_id=offset_id
                        )

                    if not messages:
                        break

                    batch = [
                        extract_message(m, entity) for m in messages if should_process(m)
                    ]
                    if batch:
                        result.total_inserted += self.storage.insert_messages(batch)
                    result.total_fetched += len(messages)

                    # 全量模式从新到旧：取本批最小 id 作为下一批 offset
                    # 增量模式从旧到新：取本批最大 id 作为下一批 min_id
                    offset_id = (
                        max(m.id for m in messages)
                        if incremental
                        else min(m.id for m in messages)
                    )
                    result.last_msg_id = offset_id

                    logger.info(
                        "%s: 已拉取 %s 条 / 已写入 %s 条，位置 %s",
                        title, result.total_fetched, result.total_inserted, offset_id,
                    )
                    if self.registry:
                        self.registry.update_progress(entity.id, offset_id)

                    if limit and result.total_fetched >= limit:
                        break

                    retry = 0
                    await asyncio.sleep(self.rate_limit_delay)

                except FloodWaitError as e:
                    logger.warning("触发限流，等待 %s 秒", e.seconds)
                    await asyncio.sleep(e.seconds + 5)
                    retry += 1
                    if retry > self.max_retries:
                        result.errors.append("超过最大重试次数（限流）")
                        break
                except ChannelPrivateError:
                    result.errors.append("频道为私有或已被封禁，跳过")
                    break
                except Exception as e:  # noqa: BLE001
                    logger.exception("拉取批次失败")
                    result.errors.append(str(e))
                    retry += 1
                    if retry > self.max_retries:
                        break
                    await asyncio.sleep(5)
        finally:
            result.end_time = datetime.now()
            if self.registry:
                status = "completed" if not result.errors else "failed"
                self.registry.update_progress(entity.id, result.last_msg_id, status=status)

        logger.info(
            "%s 下载完成: 拉取 %s / 写入 %s，耗时 %.1fs",
            title, result.total_fetched, result.total_inserted, result.duration,
        )
        return result


def _parse_ref(ref: str | int) -> str | int:
    """把 '@name'、'https://t.me/name'、纯数字字符串规范化为 username 或 int。"""
    if isinstance(ref, int):
        return ref
    ref = ref.strip()
    if ref.startswith("https://t.me/"):
        ref = ref.removeprefix("https://t.me/").strip("/")
    if ref.startswith("@"):
        ref = ref[1:]
    return int(ref) if ref.lstrip("-").isdigit() else ref
