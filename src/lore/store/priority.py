from __future__ import annotations

from lore.store.base import KnowledgeEntry


def _conflict_rank(locked: bool, level: int) -> tuple[bool, int]:
    return (locked, level)


def pick_winner(
    a: KnowledgeEntry, b: KnowledgeEntry
) -> tuple[KnowledgeEntry, KnowledgeEntry]:
    a_rank = _conflict_rank(a.locked, a.level)
    b_rank = _conflict_rank(b.locked, b.level)
    if a_rank >= b_rank:
        return a, b
    return b, a


def resolve_priority(entries: list[KnowledgeEntry]) -> list[KnowledgeEntry]:
    by_key: dict[str, KnowledgeEntry] = {}
    for entry in entries:
        existing = by_key.get(entry.key)
        if existing is None:
            by_key[entry.key] = entry
        else:
            winner, _ = pick_winner(entry, existing)
            by_key[entry.key] = winner
    return list(by_key.values())
