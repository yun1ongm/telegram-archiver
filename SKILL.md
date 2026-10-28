---
name: telegram-archiver
description: 下载 Telegram 频道历史消息、实时监听新消息，并输出为 SQLite / CSV / Parquet。当用户想要归档、备份、分析 Telegram 频道内容，或管理 tg-archiver 的频道白名单时使用。
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
tg-archiver export --format parquet -o ./lake # SQLite 导出为 parquet/csv
```

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
