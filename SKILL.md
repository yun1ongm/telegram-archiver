---
name: telegram-archiver
description: 下载 Telegram 频道历史消息、实时监听新消息，并输出为 SQLite / CSV / Parquet。当用户想要归档、备份、分析 Telegram 频道内容，或管理 tg-archiver 的频道白名单时使用。
metadata:
  version: "0.1.1"
---

# telegram-archiver

通过 `tg-archiver` CLI 操作（基于 Telethon，使用用户自己的 Telegram API 凭据）。
所有用户数据在 `~/.telegram-archiver/`（凭据、session、白名单、默认输出）。

## 前置检查

1. 运行 `tg-archiver doctor` 确认凭据、session 就绪，且无敏感文件被 git 跟踪。
2. **首次登录必须由用户本人交互完成**（需要手机验证码或扫码 + 可能的二步验证密码）。
   如果 doctor 提示未配置凭据或无 session，提示用户在终端输入：
   `! tg-archiver init --qr`（或 `! tg-archiver init` 用验证码登录）。
   不要替用户索要或处理验证码/密码。

## 常用操作

```bash
tg-archiver channels list                     # 查看白名单与进度
tg-archiver channels add @username            # 添加频道（也支持 t.me 链接、频道 ID）
tg-archiver channels sync                     # 导入账号订阅的全部频道（默认不启用监听）
tg-archiver channels enable <channel_id>      # 启用实时监听

tg-archiver fetch --channel @username --limit 1000   # 下载历史（限量）
tg-archiver fetch --all --incremental                # 全量频道增量更新
tg-archiver fetch -c @username --storage csv -o ./out  # 直接输出 CSV

tg-archiver watch                             # 实时监听（常驻前台，长时间运行请放后台）
tg-archiver watch --verbose                   # 排查更新补取、限流和重连
tg-archiver export --format parquet -o ./lake # SQLite 导出为 parquet/csv
```

## 实时监听与延迟

- 从 0.1.1 起，`watch` 在连接前将 Telethon 的无更新补取超时从 900 秒缩短到 60 秒，
  注册处理器后加载一次 dialogs，初始化频道更新位置和访问信息。
- 60 秒是补取等待设置，不保证所有消息在 60 秒内到达。此设置会增加当前进程内所有
  已知频道的补取请求，包含非白名单订阅频道；大量频道运行时应查看限流日志。
- 使用包声明的 Telethon 1.45.0；此优化依赖内部接口，升级依赖时需重新验证。
  升级安装后需重启监听进程才能生效。
- 若用户反馈延迟，按 [延迟调查与验证说明](docs/telethon-update-latency.md) 区分事件到达、
  处理和写盘延迟。`get_dialogs()` 不负责补齐离线历史，历史补下载仍使用 `fetch --incremental`。
- 版本更新记录见 [CHANGELOG.md](CHANGELOG.md)。

## 存储说明

- 默认输出 SQLite：`~/.telegram-archiver/data/messages.db`，表 `messages`，
  主键 `(channel_id, message_id)`，字段：`channel_id, message_id, time, channel_username, channel_title, body, source, views, forwards`。
- CSV：每频道一个文件 `<dir>/<channel_id>.csv`。
- Parquet：目录数据集 `<dir>/<channel_id>/part-*.parquet`（需 `pip install 'telegram-archiver[parquet]'`）。
- 三种格式都自动去重，可安全重复运行。

## 安全红线（必须遵守）

- **绝不**读取、打印、上传或提交 `~/.telegram-archiver/` 下的
  `*.session`、`credentials.json`、`channels.json`；session 文件等于账号钥匙。
- 不要把消息数据发送到任何外部服务，除非用户明确要求。
- 长时间监听用后台方式运行 `tg-archiver watch`，并告知用户日志位置。
- 提醒用户遵守 Telegram API 服务条款，仅下载自己有权访问的内容。
