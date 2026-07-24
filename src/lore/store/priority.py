from __future__ import annotations

from lore.store.base import KnowledgeEntry


def resolve_priority(entries: list[KnowledgeEntry]) -> list[KnowledgeEntry]:
    by_key: dict[str, KnowledgeEntry] = {}
    for entry in entries:
        existing = by_key.get(entry.key)
        if existing is None:
            by_key[entry.key] = entry
        elif entry.locked and not existing.locked:
            by_key[entry.key] = entry
        elif not entry.locked and existing.locked:
            pass
        elif entry.level > existing.level:
            by_key[entry.key] = entry
    return list(by_key.values())
