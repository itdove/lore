from __future__ import annotations

from nicegui import ui

from lore.dashboard.pages import format_level_label, render_sync_badge
from lore.dashboard.state import get_dashboard_store, get_sync_status


def render_overview() -> None:
    ui.label("Knowledge Base Overview").classes("text-h6 q-mb-md")

    store = get_dashboard_store()
    health = store.health()
    sync_status = get_sync_status()

    from lore.store.sqlite import _VEC_LOADED

    with ui.row().classes("q-gutter-md"):
        _stat_card("Total Entries", str(health["total_entries"]), "storage")
        _stat_card(
            "Conflicts",
            str(health["conflict_count"]),
            "warning",
            color="negative" if health["conflict_count"] > 0 else "grey",
        )
        _stat_card(
            "Stale Entries",
            str(health["stale_count"]),
            "schedule",
            color="warning" if health["stale_count"] > 0 else "grey",
        )
        negated = health["negated_count"]
        _stat_card(
            "Negated",
            str(negated),
            "block",
            color="deep-purple" if negated > 0 else "grey",
        )
        _stat_card(
            "sqlite-vec",
            "Active" if _VEC_LOADED else "Fallback",
            "memory" if _VEC_LOADED else "speed",
            color="positive" if _VEC_LOADED else "warning",
        )

    ui.label("Entries by Level").classes("text-subtitle1 q-mt-lg q-mb-sm")
    with ui.row().classes("q-gutter-md"):
        for level, count in sorted(health["entries_by_level"].items()):
            label = format_level_label(level)
            _stat_card(label, str(count), "layers")

    ui.label("Sync Status").classes("text-subtitle1 q-mt-lg q-mb-sm")
    with ui.card().classes("q-pa-md"):
        render_sync_badge(sync_status)

        ui.label(
            f"Auto-sync: {'enabled' if sync_status['auto_sync'] else 'disabled'}"
        ).classes("text-caption")
        if sync_status["locked"]:
            ui.label("Sync in progress...").classes("text-caption text-warning")


def _stat_card(title: str, value: str, icon: str, color: str = "primary") -> None:
    with ui.card().classes("q-pa-md items-center").style("min-width: 150px"):
        ui.icon(icon, size="md", color=color)
        ui.label(value).classes("text-h4 text-weight-bold")
        ui.label(title).classes("text-caption")
