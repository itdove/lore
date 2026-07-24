from __future__ import annotations

from dataclasses import dataclass

from nicegui import ui

from lore.dashboard.pages import format_level_label
from lore.dashboard.state import get_dashboard_store
from lore.store.base import KnowledgeEntry


@dataclass
class _ConflictPair:
    a: KnowledgeEntry
    b: KnowledgeEntry | None
    key: str


def render_conflicts() -> None:
    ui.label("Conflict Resolution").classes("text-h6 q-mb-md")

    container = ui.column().classes("w-full")

    def _build_conflict_list():
        store = get_dashboard_store()
        conflicts = store.list_conflicts()

        if not conflicts:
            ui.label("No conflicts.").classes("text-italic text-grey")
            return

        pairs = _group_conflict_pairs(store, conflicts)

        ui.label(f"{len(pairs)} conflict(s)").classes("text-caption q-mb-md")

        for pair in pairs:
            _render_conflict_card(store, pair, refresh)

    def refresh():
        container.clear()
        with container:
            _build_conflict_list()

    refresh()


def _group_conflict_pairs(store, conflicts) -> list[_ConflictPair]:
    seen = set()
    pairs = []

    for entry in conflicts:
        if entry.id in seen:
            continue
        seen.add(entry.id)

        other = None
        if entry.conflict_with:
            other = store.get_by_id(entry.conflict_with)
            if other:
                seen.add(other.id)

        pairs.append(_ConflictPair(a=entry, b=other, key=entry.key))

    return pairs


def _render_conflict_card(store, pair: _ConflictPair, refresh_callback) -> None:
    with ui.card().classes("w-full q-mb-md"):
        ui.label(pair.key).classes("text-subtitle1 text-weight-bold")

        with ui.row().classes("q-gutter-md w-full"):
            with ui.card().classes("col q-pa-sm bg-blue-1"):
                _entry_label(pair.a, "A")
                ui.markdown(pair.a.value[:300]).classes("text-body2").props("no-html")

            if pair.b:
                with ui.card().classes("col q-pa-sm bg-orange-1"):
                    _entry_label(pair.b, "B")
                    ui.markdown(pair.b.value[:300]).classes("text-body2").props(
                        "no-html"
                    )

        with ui.row().classes("q-gutter-sm q-mt-sm"):
            if pair.b:
                ui.button(
                    "Keep A",
                    icon="check",
                    on_click=lambda a=pair.a, b=pair.b: _resolve_keep(
                        store, a.id, b.id, refresh_callback
                    ),
                ).props("flat color=primary")

                ui.button(
                    "Keep B",
                    icon="check",
                    on_click=lambda a=pair.a, b=pair.b: _resolve_keep(
                        store, b.id, a.id, refresh_callback
                    ),
                ).props("flat color=primary")

                ui.button(
                    "Merge",
                    icon="merge_type",
                    on_click=lambda a=pair.a, b=pair.b: _open_merge_dialog(
                        store, a, b, refresh_callback
                    ),
                ).props("flat color=secondary")

            ui.button(
                "Dismiss",
                icon="close",
                on_click=lambda a=pair.a, b=pair.b: _resolve_dismiss(
                    store, a, b, refresh_callback
                ),
            ).props("flat color=grey")


def _entry_label(entry, side: str) -> None:
    status = entry.conflict_status or "unresolved"
    with ui.row().classes("items-center q-gutter-xs"):
        ui.badge(f"Side {side}", color="grey")
        ui.badge(
            format_level_label(entry),
            color="blue" if entry.level > 0 else "green",
        )
        ui.badge(status, color="orange" if status == "active" else "grey")


def _resolve_keep(store, winner_id: str, loser_id: str, refresh_callback) -> None:
    store.clear_conflict(winner_id)
    store.clear_conflict(loser_id)
    store.commit()
    ui.notify("Conflict resolved", type="positive")
    refresh_callback()


def _resolve_dismiss(store, entry_a, entry_b, refresh_callback) -> None:
    store.clear_conflict(entry_a.id)
    if entry_b:
        store.clear_conflict(entry_b.id)
    store.commit()
    ui.notify("Conflict dismissed", type="info")
    refresh_callback()


def _open_merge_dialog(store, entry_a, entry_b, refresh_callback) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-4xl"):
        ui.label(f"Merge: {entry_a.key}").classes("text-h6 q-mb-md")

        with ui.row().classes("q-gutter-md w-full"):
            with ui.column().classes("col"):
                ui.label("Side A").classes("text-subtitle2")
                ui.markdown(entry_a.value).classes("bg-blue-1 q-pa-sm rounded").props(
                    "no-html"
                )

            with ui.column().classes("col"):
                ui.label("Side B").classes("text-subtitle2")
                ui.markdown(entry_b.value).classes("bg-orange-1 q-pa-sm rounded").props(
                    "no-html"
                )

        ui.label("Merged Value").classes("text-subtitle2 q-mt-md")
        merged_input = ui.textarea(value=entry_a.value).classes("w-full")

        def apply_merge():
            merged_value = merged_input.value.strip()
            if not merged_value:
                ui.notify("Merged value cannot be empty", type="negative")
                return

            store.update(
                entry_a.key,
                merged_value,
                reason="merged via dashboard",
                actor="dashboard",
                level=entry_a.level,
            )
            store.apply_conflict(entry_a.id, entry_b.id)
            store.commit()
            ui.notify("Merged and resolved", type="positive")
            dialog.close()
            refresh_callback()

        with ui.row().classes("q-gutter-sm q-mt-md"):
            ui.button("Apply Merge", icon="merge_type", on_click=apply_merge).props(
                "color=primary"
            )
            ui.button("Cancel", on_click=dialog.close).props("flat")

    dialog.open()
