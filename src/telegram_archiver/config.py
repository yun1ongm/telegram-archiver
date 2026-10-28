"""配置目录与凭据管理。

所有用户数据统一放在 ~/.telegram-archiver/（可用环境变量
TELEGRAM_ARCHIVER_HOME 覆盖），不污染项目目录。

凭据优先级：环境变量 > 配置文件 credentials.json。
同时支持在项目目录放置 .env（python-dotenv 自动加载，.gitignore 已排除）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

APP_NAME = "telegram-archiver"
ENV_HOME = "TELEGRAM_ARCHIVER_HOME"
ENV_API_ID = "TELEGRAM_API_ID"
ENV_API_HASH = "TELEGRAM_API_HASH"

load_dotenv()  # 加载当前目录 .env（如果存在）

_CRED_FILE = "credentials.json"


def get_config_dir() -> Path:
    override = os.environ.get(ENV_HOME)
    base = Path(override).expanduser() if override else Path.home() / f".{APP_NAME}"
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_sessions_dir() -> Path:
    d = get_config_dir() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_data_dir() -> Path:
    d = get_config_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_credentials() -> tuple[int, str] | None:
    """返回 (api_id, api_hash)，未配置时返回 None。"""
    api_id = os.environ.get(ENV_API_ID)
    api_hash = os.environ.get(ENV_API_HASH)
    if api_id and api_hash:
        return int(api_id), api_hash

    cred_file = get_config_dir() / _CRED_FILE
    if cred_file.exists():
        data = json.loads(cred_file.read_text(encoding="utf-8"))
        return int(data["api_id"]), data["api_hash"]
    return None


def save_credentials(api_id: int, api_hash: str) -> Path:
    """保存凭据到配置文件，权限 600（仅当前用户可读写）。"""
    cred_file = get_config_dir() / _CRED_FILE
    cred_file.write_text(
        json.dumps({"api_id": api_id, "api_hash": api_hash}, indent=2),
        encoding="utf-8",
    )
    os.chmod(cred_file, 0o600)
    return cred_file
