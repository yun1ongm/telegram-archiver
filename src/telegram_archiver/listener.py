"""实时监听器：接收注册表中启用频道的新消息并写入存储。"""

from __future__ import annotations

import logging

from telethon import TelegramClient, events

from .channels import ChannelRegistry
from .processors import extract_message, should_process
from .storage import StorageBackend

logger = logging.getLogger("telegram_archiver.listener")


class LiveListener:
    def __init__(
        self,
        client: TelegramClient,
        storage: StorageBackend,
        registry: ChannelRegistry,
    ):
        self.client = client
        self.storage = storage
        self.registry = registry

    async def start(self) -> None:
        entries = self.registry.list(enabled_only=True)
        if not entries:
            raise RuntimeError(
                "没有启用监听的频道。先运行 `tg-archiver channels sync` "
                "或 `tg-archiver channels add <频道>`。"
            )

        entities = []
        for entry in entries:
            try:
                ref = entry.username or entry.channel_id
                entities.append(await self.client.get_entity(ref))
            except Exception as e:  # noqa: BLE001
                logger.error("无法解析频道 %s: %s", entry.title or entry.channel_id, e)

        if not entities:
            raise RuntimeError("所有频道都解析失败，请检查网络与频道配置。")

        logger.info("开始实时监听 %s 个频道", len(entities))

        @self.client.on(events.NewMessage(chats=entities))
        async def _handler(event):
            try:
                msg = event.message
                if not should_process(msg):
                    return
                entity = await event.get_chat()
                data = extract_message(msg, entity)
                inserted = self.storage.insert_messages([data])
                if inserted:
                    preview = (data["body"] or "")[:50]
                    logger.info("[%s] %s", data["channel_title"], preview)
            except Exception:  # noqa: BLE001
                logger.exception("处理新消息失败")

        await self.client.run_until_disconnected()
