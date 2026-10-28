"""Telethon 客户端构造。"""

from __future__ import annotations

from telethon import TelegramClient

from .config import get_sessions_dir, load_credentials


def build_client(session_name: str = "default") -> TelegramClient:
    """根据已保存的凭据构造客户端（尚未连接）。

    session 文件保存在 ~/.telegram-archiver/sessions/<session_name>.session，
    它等同于账号钥匙，切勿提交到任何仓库。
    """
    creds = load_credentials()
    if creds is None:
        raise RuntimeError(
            "未找到 Telegram API 凭据。请先运行 `tg-archiver init`，"
            "或设置环境变量 TELEGRAM_API_ID / TELEGRAM_API_HASH。"
        )
    api_id, api_hash = creds
    session_path = get_sessions_dir() / session_name
    return TelegramClient(
        str(session_path),
        api_id,
        api_hash,
        connection_retries=None,
        retry_delay=1,
        timeout=15,
        flood_sleep_threshold=60,  # 小于 60 秒的限流由 Telethon 自动等待
        request_retries=5,
    )
