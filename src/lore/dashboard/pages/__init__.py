from __future__ import annotations

from nicegui import ui

from lore.store.base import KnowledgeEntry


def format_level_label(entry_or_level, level_name: str | None = None) -> str:
    if isinstance(entry_or_level, KnowledgeEntry):
        level = entry_or_level.level
        level_name = entry_or_level.level_name
    else:
        level = int(entry_or_level)
    if level_name:
        return level_name
    return "Individual" if level == 0 else f"Level {level}"


def render_sync_badge(sync_status: dict) -> None:
    last = sync_status["last_sync"] or "Never"
    badge_color = "negative" if sync_status["stale"] else "positive"
    badge_text = "STALE" if sync_status["stale"] else "FRESH"

    with ui.row().classes("items-center q-gutter-sm"):
        ui.label(f"Last sync: {last}")
        ui.badge(badge_text, color=badge_color)
