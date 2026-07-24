from __future__ import annotations

from nicegui import ui

from lore.dashboard.pages import format_level_label
from lore.dashboard.state import (
    build_repo_file_url,
    promote_entry,
)


def show_entry_detail(store, entry_id: str) -> None:
    entry = store.get_by_id(entry_id)
    if not entry:
        ui.notify("Entry not found", type="negative")
        return

    with ui.dialog() as dialog, ui.card().classes("w-full max-w-3xl"):
        with ui.row().classes("items-center justify-between w-full q-mb-md"):
            ui.label(entry.key).classes("text-h6")
            color = "green" if entry.level == 0 else "blue"
            ui.badge(format_level_label(entry), color=color)

        if entry.conflict_with:
            ui.badge("CONFLICT", color="negative").classes("q-mb-sm")

        if entry.locked:
            ui.badge("LOCKED", color="warning").classes("q-mb-sm")

        if entry.tags:
            with ui.row().classes("q-gutter-xs q-mb-md"):
                for tag in entry.tags.split(","):
                    tag = tag.strip()
                    if tag:
                        ui.badge(tag, color="grey").props("outline")

        ui.separator()
        ui.markdown(entry.value).classes("q-my-md").props("no-html")
        ui.separator()

        if entry.level > 0:
            repo_url = build_repo_file_url(entry)
            if repo_url:
                ui.link("View Source in Repository", repo_url, new_tab=True).classes(
                    "q-mt-sm"
                )

        with ui.row().classes("q-gutter-sm q-mt-md"):
            if entry.level == 0:
                ui.button(
                    "Edit",
                    icon="edit",
                    on_click=lambda: _open_child_dialog(
                        entry, dialog, "show_edit_dialog"
                    ),
                ).props("flat")
                ui.button(
                    "Delete",
                    icon="delete",
                    on_click=lambda: _open_child_dialog(
                        entry, dialog, "show_delete_dialog"
                    ),
                    color="negative",
                ).props("flat")
                ui.button(
                    "Promote",
                    icon="publish",
                    on_click=lambda: _do_promote(entry),
                ).props("flat color=positive")

            ui.button("Close", on_click=dialog.close).props("flat")

        _render_history(store, entry.id)

    dialog.open()


def _render_history(store, entry_id: str) -> None:
    history = store.get_history(entry_id)
    if not history:
        return

    ui.label("History").classes("text-subtitle2 q-mt-lg q-mb-sm")
    columns = [
        {"name": "action", "label": "Action", "field": "action", "align": "left"},
        {"name": "actor", "label": "Actor", "field": "actor", "align": "left"},
        {"name": "reason", "label": "Reason", "field": "reason", "align": "left"},
        {"name": "timestamp", "label": "Time", "field": "timestamp", "align": "left"},
    ]
    rows = [
        {
            "action": h.action,
            "actor": h.actor or "",
            "reason": h.reason or "",
            "timestamp": h.timestamp or "",
        }
        for h in history
    ]
    ui.table(columns=columns, rows=rows, row_key="timestamp").props(
        "dense flat bordered"
    ).classes("w-full")


def _open_child_dialog(entry, parent_dialog, fn_name: str) -> None:
    from lore.dashboard.pages import individual

    parent_dialog.close()
    getattr(individual, fn_name)(entry)


def _do_promote(entry) -> None:
    result = promote_entry(entry)
    if "error" in result:
        ui.notify(f"Promote failed: {result['error']}", type="negative")
    else:
        ui.notify(f"PR created: {result['pr_url']}", type="positive")
