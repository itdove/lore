from lore.store.base import HistoryRecord, KnowledgeEntry, StoreBackend
from lore.store.sqlite import SQLiteStore, create_schema


def get_store() -> SQLiteStore:
    from pathlib import Path

    from lore.config.manager import get_global_config
    from lore.config.utils import db_path

    cfg = get_global_config()
    path = cfg.store.path or str(db_path())
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = create_schema(path)
    return SQLiteStore(conn)


__all__ = [
    "HistoryRecord",
    "KnowledgeEntry",
    "StoreBackend",
    "SQLiteStore",
    "create_schema",
    "get_store",
]
