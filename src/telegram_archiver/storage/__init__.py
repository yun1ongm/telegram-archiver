"""存储后端：sqlite（默认）/ csv / parquet。"""

from __future__ import annotations

from ..config import get_data_dir
from .base import StorageBackend

__all__ = ["StorageBackend", "open_storage"]


def open_storage(kind: str, output: str | None = None) -> StorageBackend:
    if kind == "sqlite":
        from .sqlite_backend import SQLiteBackend

        return SQLiteBackend(output or str(get_data_dir() / "messages.db"))
    if kind == "csv":
        from .csv_backend import CSVBackend

        return CSVBackend(output or str(get_data_dir() / "csv"))
    if kind == "parquet":
        try:
            from .parquet_backend import ParquetBackend
        except ImportError as e:
            raise RuntimeError(
                "Parquet 输出需要 pyarrow：pip install 'telegram-archiver[parquet]'"
            ) from e
        return ParquetBackend(output or str(get_data_dir() / "parquet"))
    raise ValueError(f"未知存储格式: {kind}（支持 sqlite / csv / parquet）")
