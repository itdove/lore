from __future__ import annotations

from nicegui import run, ui

from lore.dashboard.pages import render_sync_badge
from lore.dashboard.state import get_sync_status, trigger_sync


def render_sync() -> None:
    ui.label("Sync Management").classes("text-h6 q-mb-md")

    status_container = ui.column().classes("w-full")
    result_container = ui.column().classes("w-full q-mt-md")

    def refresh_status():
        status_container.clear()
        with status_container:
            _render_status_card()

    async def do_sync():
        result_container.clear()
        with result_container:
            ui.spinner(size="lg").classes("q-my-md")

        try:
            result = await run.io_bound(trigger_sync)
        except RuntimeError:
            result_container.clear()
            with result_container:
                ui.label("Sync already in progress").classes("text-negative")
            return

        result_container.clear()
        with result_container:
            _render_sync_result(result)

        refresh_status()

    refresh_status()

    ui.button("Sync Now", icon="sync", on_click=do_sync).props("color=primary")

    _render_hierarchy()


def _render_status_card() -> None:
    sync_status = get_sync_status()

    with ui.card().classes("q-pa-md w-full"):
        with ui.row().classes("items-center q-gutter-sm"):
            ui.icon("sync", size="md")
            ui.label("Sync Status").classes("text-subtitle1")

        with ui.column().classes("q-mt-sm"):
            render_sync_badge(sync_status)

        with ui.row().classes("q-gutter-md q-mt-sm"):
            ui.label(f"Threshold: {sync_status['threshold_minutes']} min").classes(
                "text-caption"
            )
            ui.label(
                f"Auto-sync: {'on' if sync_status['auto_sync'] else 'off'}"
            ).classes("text-caption")

        if sync_status["locked"]:
            with ui.row().classes("items-center q-gutter-xs q-mt-sm"):
                ui.spinner(size="sm")
                ui.label("Sync in progress...").classes("text-warning")


def _render_hierarchy() -> None:
    try:
        from lore.config.manager import get_project_config

        project_cfg = get_project_config()
    except Exception:
        return

    if not project_cfg.hierarchy:
        return

    ui.label("Configured Hierarchy").classes("text-subtitle1 q-mt-lg q-mb-sm")

    columns = [
        {"name": "level", "label": "Level", "field": "level", "align": "left"},
        {"name": "name", "label": "Name", "field": "name", "align": "left"},
        {"name": "repo", "label": "Repository", "field": "repo", "align": "left"},
        {"name": "branch", "label": "Branch", "field": "branch", "align": "left"},
    ]

    rows = []
    for h in project_cfg.hierarchy:
        rows.append(
            {
                "level": h.level,
                "name": h.name or f"level-{h.level}",
                "repo": h.repo,
                "branch": h.branch,
            }
        )

    ui.table(columns=columns, rows=rows, row_key="level").props(
        "dense flat bordered"
    ).classes("w-full")


def _render_sync_result(result) -> None:
    with ui.card().classes("q-pa-md w-full"):
        ui.label("Sync Result").classes("text-subtitle1 q-mb-sm")

        with ui.row().classes("q-gutter-md"):
            _result_chip("Created", result.created, "positive")
            _result_chip("Updated", result.updated, "primary")
            _result_chip("Deleted", result.deleted, "grey")
            _result_chip("Promoted", result.promoted, "info")
            _result_chip("Conflicts", result.conflicts, "warning")
            _result_chip("Blocked", result.blocked, "negative")

        if result.errors:
            ui.label("Errors").classes("text-subtitle2 text-negative q-mt-sm")
            for err in result.errors:
                ui.label(f"  {err}").classes("text-caption text-negative")

        if result.details:
            with ui.expansion("Details", icon="list").classes("q-mt-sm"):
                for detail in result.details:
                    ui.label(detail).classes("text-caption font-mono")


def _result_chip(label: str, count: int, color: str) -> None:
    display_color = color if count > 0 else "grey"
    ui.badge(f"{label}: {count}", color=display_color).props("outline")
