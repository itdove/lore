from __future__ import annotations

from nicegui import ui

from lore.dashboard.state import get_dashboard_store, validate_key
from lore.store.base import KnowledgeEntry


def render_create_form() -> None:
    ui.label("Create Individual Entry").classes("text-h6 q-mb-md")

    store = get_dashboard_store()

    key_input = ui.input(
        label="Key (e.g., bug:api:jwt)",
        validation={"Invalid format": lambda v: validate_key(v) is None},
    ).classes("w-full")

    value_input = ui.textarea(
        label="Value", placeholder="Knowledge content..."
    ).classes("w-full")

    tags_input = ui.input(
        label="Tags (comma-separated)", placeholder="python, auth, jwt"
    ).classes("w-full")

    def create():
        key = key_input.value.strip()
        value = value_input.value.strip()
        tags = tags_input.value.strip()

        error = validate_key(key)
        if error:
            ui.notify(error, type="negative")
            return

        if not value:
            ui.notify("Value is required", type="negative")
            return

        existing = store.get_by_key_and_level(key, 0)
        if existing:
            ui.notify(f"Key '{key}' already exists at level 0", type="warning")
            return

        entry = KnowledgeEntry(
            key=key,
            value=value,
            tags=tags,
            level=0,
            level_name="individual",
        )
        entry_id = store.store(entry)
        ui.notify(f"Created entry: {key} (id: {entry_id[:8]}...)", type="positive")

        key_input.value = ""
        value_input.value = ""
        tags_input.value = ""

    ui.button("Create", icon="add", on_click=create).props("color=primary")


def show_edit_dialog(entry: KnowledgeEntry) -> None:
    if entry.level != 0:
        ui.notify("Only individual entries can be edited", type="negative")
        return

    store = get_dashboard_store()

    with ui.dialog() as dialog, ui.card().classes("w-full max-w-2xl"):
        ui.label(f"Edit: {entry.key}").classes("text-h6 q-mb-md")

        ui.label(f"Key: {entry.key}").classes("text-caption text-grey")

        value_input = ui.textarea(label="Value", value=entry.value).classes("w-full")

        tags_input = ui.input(label="Tags", value=entry.tags or "").classes("w-full")

        reason_input = ui.input(
            label="Reason for change", placeholder="Why are you editing?"
        ).classes("w-full")

        def save():
            value = value_input.value.strip()
            reason = reason_input.value.strip()

            if not value:
                ui.notify("Value is required", type="negative")
                return

            if not reason:
                ui.notify("Reason is required for audit trail", type="negative")
                return

            store.update(
                entry.key,
                value,
                reason=reason,
                actor="dashboard",
                tags=tags_input.value.strip() or None,
                level=0,
            )
            ui.notify(f"Updated: {entry.key}", type="positive")
            dialog.close()
            ui.navigate.to("/?tab=browse")

        with ui.row().classes("q-gutter-sm q-mt-md"):
            ui.button("Save", icon="save", on_click=save).props("color=primary")
            ui.button("Cancel", on_click=dialog.close).props("flat")

    dialog.open()


def show_delete_dialog(entry: KnowledgeEntry) -> None:
    if entry.level != 0:
        ui.notify("Only individual entries can be deleted", type="negative")
        return

    store = get_dashboard_store()

    with ui.dialog() as dialog, ui.card().classes("w-full max-w-md"):
        ui.label(f"Delete: {entry.key}").classes("text-h6 q-mb-md")
        ui.label(f"Value: {entry.value[:100]}...").classes("text-caption q-mb-md")

        reason_input = ui.input(
            label="Reason for deletion", placeholder="Why are you deleting?"
        ).classes("w-full")

        def confirm_delete():
            reason = reason_input.value.strip()
            if not reason:
                ui.notify("Reason is required for audit trail", type="negative")
                return

            store.delete(entry.key, reason=reason, actor="dashboard", level=0)
            ui.notify(f"Deleted: {entry.key}", type="positive")
            dialog.close()
            ui.navigate.to("/?tab=browse")

        with ui.row().classes("q-gutter-sm q-mt-md"):
            ui.button("Delete", icon="delete", on_click=confirm_delete).props(
                "color=negative"
            )
            ui.button("Cancel", on_click=dialog.close).props("flat")

    dialog.open()
