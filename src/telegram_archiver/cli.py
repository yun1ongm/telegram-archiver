"""tg-archiver 命令行入口。"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .auth import ensure_authorized
from .channels import ChannelRegistry
from .client import build_client
from .config import get_config_dir, get_data_dir, get_sessions_dir, load_credentials, save_credentials
from .crawler import HistoryCrawler
from .listener import LiveListener
from .storage import open_storage

app = typer.Typer(
    name="tg-archiver",
    help="Telegram 频道归档工具：历史下载、实时监听，输出 SQLite / CSV / Parquet。",
    no_args_is_help=True,
)
channels_app = typer.Typer(help="管理监听频道（白名单）", no_args_is_help=True)
app.add_typer(channels_app, name="channels")

console = Console()
err_console = Console(stderr=True)


def _setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )


# ---------------------------------------------------------------- init


@app.command()
def init(
    qr: bool = typer.Option(False, "--qr", help="使用二维码登录（免输验证码）"),
    session: str = typer.Option("default", help="session 名称（多账号时用不同名字区分）"),
):
    """首次注册：配置 API 凭据并登录 Telegram 账号。"""
    asyncio.run(_init(qr=qr, session=session))


async def _init(qr: bool, session: str) -> None:
    creds = load_credentials()
    if creds is None:
        console.print("请先到 [link]https://my.telegram.org/apps[/link] 申请 API 凭据（免费）")
        api_id = typer.prompt("API ID", type=int)
        api_hash = typer.prompt("API Hash", hide_input=True)
        path = save_credentials(api_id, api_hash)
        console.print(f"✔ 凭据已保存到 {path}（权限 600）")
    else:
        console.print("✔ 已存在 API 凭据，跳过填写")

    client = build_client(session)
    await ensure_authorized(client, qr=qr)
    me = await client.get_me()
    name = " ".join(filter(None, [me.first_name, me.last_name]))
    console.print(f"[green]✔ 登录成功：{name} (@{me.username})[/green]")
    console.print(f"  session 保存在 {get_sessions_dir() / (session + '.session')}，请妥善保管")
    console.print("\n下一步：")
    console.print("  tg-archiver channels sync     # 导入你订阅的频道")
    console.print("  tg-archiver channels add @xxx # 或手动添加频道")
    console.print("  tg-archiver fetch --all       # 下载历史消息")
    console.print("  tg-archiver watch             # 实时监听")
    await client.disconnect()


# ---------------------------------------------------------------- channels


@channels_app.command("list")
def channels_list() -> None:
    """列出注册表中的频道。"""
    registry = ChannelRegistry()
    entries = registry.list()
    if not entries:
        console.print("（空）先运行 channels sync 或 channels add")
        return
    table = Table(title="监听频道")
    for col in ("ID", "Username", "标题", "实时监听", "历史下载", "进度", "状态"):
        table.add_column(col)
    for e in entries:
        table.add_row(
            str(e.channel_id),
            f"@{e.username}" if e.username else "-",
            e.title,
            "✔" if e.enabled else "✘",
            "✔" if e.crawl_history else "✘",
            str(e.last_crawled_msg_id),
            e.crawl_status,
        )
    console.print(table)


@channels_app.command("add")
def channels_add(
    refs: list[str] = typer.Argument(..., help="频道用户名/链接/ID，可多个"),
    session: str = typer.Option("default"),
) -> None:
    """添加频道到白名单（会联网解析频道信息）。"""
    asyncio.run(_channels_add(refs, session))


async def _channels_add(refs: list[str], session: str) -> None:
    from .crawler import _parse_ref

    registry = ChannelRegistry()
    client = build_client(session)
    await ensure_authorized(client)
    for ref in refs:
        try:
            entity = await client.get_entity(_parse_ref(ref))
            entry = registry.add(
                channel_id=entity.id,
                title=getattr(entity, "title", str(ref)),
                username=getattr(entity, "username", None),
            )
            console.print(f"✔ 已添加 {entry.title} (ID: {entry.channel_id})")
        except Exception as e:  # noqa: BLE001
            err_console.print(f"[red]✘ 添加 {ref} 失败: {e}[/red]")
    await client.disconnect()


@channels_app.command("remove")
def channels_remove(channel_id: int = typer.Argument(...)) -> None:
    """从白名单移除频道（不删除已下载数据）。"""
    registry = ChannelRegistry()
    if registry.remove(channel_id):
        console.print(f"✔ 已移除 {channel_id}")
    else:
        err_console.print(f"[red]未找到频道 {channel_id}[/red]")
        raise typer.Exit(1)


@channels_app.command("enable")
def channels_enable(channel_id: int = typer.Argument(...)) -> None:
    """启用频道的实时监听。"""
    _set_enabled(channel_id, True)


@channels_app.command("disable")
def channels_disable(channel_id: int = typer.Argument(...)) -> None:
    """停用频道的实时监听。"""
    _set_enabled(channel_id, False)


def _set_enabled(channel_id: int, enabled: bool) -> None:
    registry = ChannelRegistry()
    if registry.set_enabled(channel_id, enabled):
        console.print(f"✔ 频道 {channel_id} 已{'启用' if enabled else '停用'}")
    else:
        err_console.print(f"[red]未找到频道 {channel_id}[/red]")
        raise typer.Exit(1)


@channels_app.command("sync")
def channels_sync(session: str = typer.Option("default")) -> None:
    """导入你 Telegram 账号订阅的所有频道/群组（默认不启用监听）。"""
    asyncio.run(_channels_sync(session))


async def _channels_sync(session: str) -> None:
    from telethon.tl.types import Channel

    registry = ChannelRegistry()
    client = build_client(session)
    await ensure_authorized(client)
    added = 0
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, Channel):
            if registry.get(entity.id) is None:
                registry.add(
                    channel_id=entity.id,
                    title=getattr(entity, "title", ""),
                    username=getattr(entity, "username", None),
                    enabled=False,
                )
                added += 1
    console.print(f"✔ 新导入 {added} 个频道（默认未启用监听，用 channels enable/list 管理）")
    await client.disconnect()


# ---------------------------------------------------------------- fetch


@app.command()
def fetch(
    channels: list[str] = typer.Option(
        None, "--channel", "-c", help="频道用户名/链接/ID，可多次指定"
    ),
    all_channels: bool = typer.Option(
        False, "--all", help="下载注册表中所有允许历史下载的频道"
    ),
    limit: int = typer.Option(None, help="每个频道最多下载条数（默认全部）"),
    incremental: bool = typer.Option(
        False, "--incremental", "-i", help="增量模式：从上次下载进度继续"
    ),
    storage: str = typer.Option("sqlite", help="存储格式: sqlite / csv / parquet"),
    output: Path = typer.Option(None, "-o", help="输出路径（默认 ~/.telegram-archiver/data/）"),
    batch_size: int = typer.Option(100, help="每批消息数（最大 100）"),
    rate_limit: float = typer.Option(1.0, help="批次间隔秒数（防限流，建议 ≥1）"),
    session: str = typer.Option("default"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """下载频道历史消息（自动去重、断点续传）。"""
    _setup_logging(verbose)
    asyncio.run(
        _fetch(channels, all_channels, limit, incremental, storage, output, batch_size, rate_limit, session)
    )


async def _fetch(channels, all_channels, limit, incremental, storage, output, batch_size, rate_limit, session) -> None:
    registry = ChannelRegistry()
    targets: list[str | int] = list(channels or [])
    if all_channels:
        for e in registry.to_crawl():
            targets.append(e.username or e.channel_id)
    if not targets:
        err_console.print("[red]请用 --channel 指定频道，或用 --all 下载注册表中的频道[/red]")
        raise typer.Exit(1)

    client = build_client(session)
    await ensure_authorized(client)
    with open_storage(storage, str(output) if output else None) as store:
        crawler = HistoryCrawler(
            client, store, registry,
            batch_size=batch_size, rate_limit_delay=rate_limit,
        )
        results = []
        for ref in targets:
            try:
                results.append(
                    await crawler.crawl_channel(ref, limit=limit, incremental=incremental)
                )
            except Exception as e:  # noqa: BLE001
                err_console.print(f"[red]✘ 下载 {ref} 失败: {e}[/red]")

    table = Table(title="下载结果")
    for col in ("频道", "拉取", "写入", "错误"):
        table.add_column(col)
    for r in results:
        table.add_row(r.channel_title, str(r.total_fetched), str(r.total_inserted),
                      "; ".join(r.errors) or "-")
    console.print(table)
    await client.disconnect()


# ---------------------------------------------------------------- watch


@app.command()
def watch(
    storage: str = typer.Option("sqlite", help="存储格式: sqlite / csv / parquet"),
    output: Path = typer.Option(None, "-o", help="输出路径（默认 ~/.telegram-archiver/data/）"),
    session: str = typer.Option("default"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """实时监听启用频道的新消息（Ctrl+C 停止）。"""
    _setup_logging(verbose)
    asyncio.run(_watch(storage, output, session))


async def _watch(storage, output, session) -> None:
    registry = ChannelRegistry()
    client = build_client(session)
    await ensure_authorized(client)
    with open_storage(storage, str(output) if output else None) as store:
        listener = LiveListener(client, store, registry)
        console.print("[green]监听中… Ctrl+C 停止[/green]")
        try:
            await listener.start()
        except KeyboardInterrupt:
            pass
    await client.disconnect()
    console.print("已停止。")


# ---------------------------------------------------------------- export


@app.command()
def export(
    format: str = typer.Option(..., "--format", "-f", help="导出格式: csv 或 parquet"),
    source: Path = typer.Option(None, "--source", "-s", help="源 SQLite 数据库（默认 ~/.telegram-archiver/data/messages.db）"),
    output: Path = typer.Option(..., "-o", help="导出目录"),
) -> None:
    """把 SQLite 库中的消息导出为 CSV 或 Parquet。"""
    from .storage.sqlite_backend import SQLiteBackend

    src = source or get_data_dir() / "messages.db"
    if not src.exists():
        err_console.print(f"[red]源数据库不存在: {src}[/red]")
        raise typer.Exit(1)

    reader = SQLiteBackend(str(src))
    try:
        with open_storage(format, str(output)) as writer:
            total = 0
            for batch in reader.iter_messages():
                for m in batch:
                    from datetime import datetime

                    m["time"] = datetime.fromisoformat(m["time"])
                total += writer.insert_messages(batch)
            console.print(f"✔ 已导出 {total} 条消息到 {output}")
    finally:
        reader.close()


# ---------------------------------------------------------------- doctor


_SENSITIVE_PATTERNS = (
    ".env",
    ".session",
    ".session-journal",
    "credentials.json",
    "channels.json",
    ".db",
    ".sqlite",
)


@app.command()
def doctor() -> None:
    """环境自检：凭据、session、以及敏感文件泄漏风险检查。"""
    ok = True

    # 1. 凭据
    if load_credentials():
        console.print("[green]✔[/green] API 凭据已配置")
    else:
        console.print("[yellow]![/yellow] 未配置 API 凭据，请运行 tg-archiver init")
        ok = False

    # 2. 凭据文件权限
    cred_file = get_config_dir() / "credentials.json"
    if cred_file.exists():
        mode = cred_file.stat().st_mode & 0o777
        if mode == 0o600:
            console.print("[green]✔[/green] credentials.json 权限 600")
        else:
            console.print(f"[yellow]![/yellow] credentials.json 权限为 {oct(mode)}，建议 chmod 600")

    # 3. session
    sessions = list(get_sessions_dir().glob("*.session"))
    if sessions:
        console.print(f"[green]✔[/green] 找到 {len(sessions)} 个 session（{get_sessions_dir()}）")
    else:
        console.print("[yellow]![/yellow] 尚未登录任何账号（无 session 文件）")

    # 4. 当前 git 仓库中是否跟踪了敏感文件
    try:
        tracked = subprocess.run(
            ["git", "ls-files"], capture_output=True, text=True, check=True,
        ).stdout.splitlines()
        leaked = [f for f in tracked if any(p in f for p in _SENSITIVE_PATTERNS)]
        if leaked:
            ok = False
            console.print("[red]✘ 以下敏感文件正被 git 跟踪，请立即移除：[/red]")
            for f in leaked:
                console.print(f"    git rm --cached {f}")
        else:
            console.print("[green]✔[/green] 当前 git 仓库未跟踪敏感文件")
    except (subprocess.CalledProcessError, FileNotFoundError):
        console.print("· 当前目录不是 git 仓库，跳过敏感文件检查")

    raise typer.Exit(0 if ok else 1)


if __name__ == "__main__":
    app()
