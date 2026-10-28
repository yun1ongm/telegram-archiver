"""首次注册与登录（手机号验证码 / 二维码两种方式）。"""

from __future__ import annotations

import asyncio
from getpass import getpass

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError


async def ensure_authorized(
    client: TelegramClient, qr: bool = False, phone: str | None = None
) -> None:
    """确保客户端已登录；未登录则走交互式登录流程。"""
    await client.connect()
    if await client.is_user_authorized():
        return
    if qr:
        await _qr_login(client)
    else:
        await _phone_login(client, phone)


async def _phone_login(client: TelegramClient, phone: str | None) -> None:
    if not phone:
        phone = input("手机号（带国际区号，如 +8613800138000）: ").strip()
    await client.send_code_request(phone)
    code = input("请输入 Telegram 客户端中收到的验证码: ").strip()
    try:
        await client.sign_in(phone, code)
    except SessionPasswordNeededError:
        password = getpass("账号开启了两步验证，请输入密码（输入不可见）: ")
        await client.sign_in(password=password)


async def _qr_login(client: TelegramClient) -> None:
    import qrcode

    while True:
        qr = await client.qr_login()
        print("\n请用手机 Telegram 扫码：设置 → 设备 → 连接桌面设备\n")
        try:
            img = qrcode.make(qr.url)
            img.print_ascii(invert=True)
        except Exception:
            pass
        print(f"\n若二维码无法显示，请复制链接到手机浏览器打开:\n{qr.url}\n")
        try:
            await asyncio.wait_for(qr.wait(), timeout=60)
            return
        except SessionPasswordNeededError:
            password = getpass("账号开启了两步验证，请输入密码（输入不可见）: ")
            await client.sign_in(password=password)
            return
        except asyncio.TimeoutError:
            print("二维码已过期，正在刷新……")
