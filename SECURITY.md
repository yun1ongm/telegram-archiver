# 安全政策 / Security Policy

## 报告漏洞

请通过 GitHub 的 **Security Advisories**（仓库 → Security → Report a vulnerability）私下报告安全问题，不要在公开 Issue 中披露。

## 凭据安全须知（重要）

本工具使用**你自己的** Telegram API 凭据和登录 session，请务必注意：

1. **`.session` 文件 = 你的账号钥匙**。任何拿到它的人都能以你的身份操作 Telegram。
   它保存在 `~/.telegram-archiver/sessions/`，本项目的 `.gitignore` 已排除 `*.session`，
   请**不要**手动把它加入任何 git 仓库或上传到云盘。
2. `credentials.json`（保存 api_id/api_hash）权限为 `600`（仅当前用户可读写）。
3. 如果你怀疑 session 泄露：在 Telegram 客户端中 设置 → 设备 → 终止对应会话，
   然后删除本地 session 文件并重新运行 `tg-archiver init`。
4. 提交代码前可运行 `tg-archiver doctor`，它会检查当前 git 仓库中是否有
   被跟踪的敏感文件（.env、session、数据库文件等）。

## 适用范围

本项目只在你本机运行，不向任何第三方服务器发送数据（除 Telegram 官方服务器外）。
