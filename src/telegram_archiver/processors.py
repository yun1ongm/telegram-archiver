"""消息过滤与字段提取。"""

from __future__ import annotations

from telethon.tl.types import Message, MessageMediaDocument, MessageMediaPhoto


def should_process(msg) -> bool:
    """只保留有文本或媒体的真实消息，跳过服务消息（加群通知等）。"""
    return isinstance(msg, Message) and bool(msg.message or msg.media)


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _media_placeholder(msg: Message) -> str:
    if isinstance(msg.media, MessageMediaPhoto):
        return "[photo]"
    if isinstance(msg.media, MessageMediaDocument):
        return "[document]"
    return "[media]"


def build_source_url(channel_id: int, username: str | None, message_id: int) -> str:
    if username:
        return f"https://t.me/{username}/{message_id}"
    # 私有频道链接格式：https://t.me/c/<channel_id>/<message_id>
    return f"https://t.me/c/{channel_id}/{message_id}"


def extract_message(msg: Message, entity) -> dict:
    """把 Telethon Message 转成统一字段字典（供各存储后端写入）。"""
    username = getattr(entity, "username", None)
    title = getattr(entity, "title", None) or getattr(entity, "first_name", "Unknown")
    body = clean_text(msg.message)
    if not body and msg.media:
        body = _media_placeholder(msg)

    return {
        "message_id": msg.id,
        "channel_id": entity.id,
        "channel_username": username,
        "channel_title": title,
        "time": msg.date,  # timezone-aware UTC datetime
        "body": body,
        "source": build_source_url(entity.id, username, msg.id),
        "views": getattr(msg, "views", None),
        "forwards": getattr(msg, "forwards", None),
    }
