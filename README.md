# telegram-archiver

> **English summary**: A small CLI tool (built on [Telethon](https://github.com/LonamiWebs/Telethon)) to download Telegram channel history and listen to live messages, writing to **SQLite, CSV, or Parquet**. First-time setup is an interactive wizard (`tg-archiver init`) that registers your session via phone code or QR login. Your credentials stay on your machine (`~/.telegram-archiver/`) — nothing is sent anywhere except Telegram's official servers. You must use your own API credentials from https://my.telegram.org and comply with Telegram's Terms of Service. License: MIT.

一个 Telegram 频道归档工具：**历史消息下载 + 实时监听**，输出 **SQLite / CSV / Parquet**。基于 Telethon，使用你自己的 Telegram API 凭据，所有数据只存在你本机。

## 功能特性

- 📥 **历史下载**：批量拉取频道全部历史，自动去重，断点续传，遇限流自动等待重试
- 📡 **实时监听**：常驻进程接收白名单频道的新消息
- 🔐 **交互式首次注册**：手机号验证码或扫码登录，session 只保存在本机
- 💾 **三种输出格式**：SQLite（默认，零配置）、CSV（每频道一个文件）、Parquet（列式分析格式）
- 🛡 **隐私优先**：凭据文件权限 600，`.gitignore` 排除所有敏感文件，`doctor` 命令自检泄漏风险

## 五分钟上手

### 1. 申请 API 凭据（一次性）

打开 https://my.telegram.org/apps ，用你的 Telegram 账号登录，创建一个应用，得到 `api_id` 和 `api_hash`。这是 Telegram 官方的开发者凭据，免费申请。

### 2. 安装

```bash
# 需要 Python 3.10+
pip install git+https://github.com/yun1ongm/telegram-archiver.git

# 如需 Parquet 输出：
pip install "telegram-archiver[parquet] @ git+https://github.com/yun1ongm/telegram-archiver.git"
```

### 3. 首次注册（登录你的账号）

```bash
tg-archiver init          # 手机号 + 验证码登录
tg-archiver init --qr     # 或扫码登录（推荐，终端显示二维码）
```

向导会引导你填入 api_id / api_hash（只填一次，保存在 `~/.telegram-archiver/credentials.json`，权限 600），然后完成 Telegram 登录。session 保存在 `~/.telegram-archiver/sessions/`。

### 4. 添加频道并下载

```bash
# 方式一：一键导入你订阅的所有频道（默认不启用监听）
tg-archiver channels sync

# 方式二：手动添加（支持 @用户名、t.me 链接、频道 ID）
tg-archiver channels add @durov https://t.me/telegram

# 下载历史消息
tg-archiver fetch --channel @durov --limit 1000    # 单个频道，最多 1000 条
tg-archiver fetch --all                            # 白名单中所有频道
tg-archiver fetch --all --incremental              # 增量更新（从上次进度继续）
tg-archiver fetch -c @durov --storage csv -o ./out # 直接输出 CSV

# 实时监听（Ctrl+C 停止）
tg-archiver watch
tg-archiver watch --storage parquet -o ./lake      # 实时写入 Parquet

# 从 SQLite 导出其他格式
tg-archiver export --format parquet -o ./lake
tg-archiver export --format csv -o ./csv_out
```

### 5. 环境自检

```bash
tg-archiver doctor
```

检查凭据配置、文件权限、以及当前 git 仓库是否误跟踪了敏感文件（.env、session、数据库等）。

## 命令速查

| 命令 | 说明 |
|---|---|
| `tg-archiver init [--qr]` | 首次注册：配置凭据 + 登录 |
| `tg-archiver channels list` | 查看白名单与下载进度 |
| `tg-archiver channels add <ref>...` | 添加频道（@名 / 链接 / ID） |
| `tg-archiver channels sync` | 导入账号订阅的全部频道 |
| `tg-archiver channels enable/disable <id>` | 开关实时监听 |
| `tg-archiver channels remove <id>` | 移出白名单 |
| `tg-archiver fetch [--all] [-c 频道] [--incremental]` | 下载历史消息 |
| `tg-archiver watch` | 实时监听 |
| `tg-archiver export -f csv\|parquet -o 目录` | 从 SQLite 导出 |
| `tg-archiver doctor` | 环境与泄漏风险自检 |

通用选项：`--storage sqlite|csv|parquet`、`-o 输出路径`、`--session 名称`（多账号）。

## 数据放在哪

```
~/.telegram-archiver/
├── credentials.json      # API 凭据（权限 600）
├── sessions/             # 登录 session（= 账号钥匙，勿外传！）
├── channels.json         # 频道白名单与下载进度
└── data/
    ├── messages.db       # 默认 SQLite 输出
    ├── csv/              # --storage csv 的输出
    └── parquet/          # --storage parquet 的输出
```

可用环境变量 `TELEGRAM_ARCHIVER_HOME` 改变根目录。也可用环境变量
`TELEGRAM_API_ID` / `TELEGRAM_API_HASH`（或项目目录 `.env`）提供凭据，
CI/服务器场景下不需要 `credentials.json`。

消息字段：`channel_id, message_id, time(UTC), channel_username, channel_title, body, source(消息链接), views, forwards`。
三种格式都按 `(channel_id, message_id)` 去重，重复运行不会产生重复数据。

## 常见问题

**触发 FloodWait / 限流怎么办？**
工具会自动等待 Telegram 要求的秒数并重试。日常可把批次间隔调大：`tg-archiver fetch --all --rate-limit 2`。

**账号开了两步验证？**
`init` 时验证码通过后会提示输入二步验证密码（输入不可见，不会被保存）。

**私有频道可以下载吗？**
只要你的账号已加入该频道就可以。用 `channels sync` 导入或用频道 ID 添加。

**session 文件泄露了？**
立即在 Telegram 客户端：设置 → 设备 → 终止对应会话，然后删除 `~/.telegram-archiver/sessions/` 下的文件并重新 `init`。详见 [SECURITY.md](SECURITY.md)。

**多账号？**
`tg-archiver init --session work`、`tg-archiver fetch --session work ...`，每个 session 独立。

## 免责声明

- 本项目仅供个人数据备份与研究学习使用。请遵守 [Telegram API 服务条款](https://core.telegram.org/api/terms) 与所在地区的法律法规。
- 必须使用**你自己申请**的 API 凭据；本项目不提供、也不应使用任何共享凭据。
- 下载他人频道内容前，请确认你有权这么做；请勿用于监控、骚扰或任何侵犯他人隐私的用途。

## Roadmap

- [ ] 消息转发（频道 → 频道/群/Bot）
- [ ] 媒体文件（图片/文档）下载
- [ ] 增量导出与定时任务模板

## 作为 Claude Code Skill 使用

仓库根目录包含 [SKILL.md](SKILL.md)。把本仓库作为 skill 安装后，Claude Code
可以帮你完成频道管理、历史下载、监听与导出等操作（首次 `init` 登录需要你本人在终端交互完成）。

## License

[MIT](LICENSE) © 2026 yun1ongm
