from __future__ import annotations

from dataclasses import dataclass

from nicegui import ui

from lore.dashboard.pages import format_level_label
from lore.dashboard.state import get_dashboard_store


@dataclass
class _BrowserFilters:
    level: int | None = None
    tag: str = ""
    search: str = ""


def render_browser() -> None:
    ui.label("Knowledge Browser").classes("text-h6 q-mb-md")

    store = get_dashboard_store()
    filters = _BrowserFilters()
    table_container = ui.column().classes("w-full")

    def refresh_table():
        table_container.clear()
        with table_container:
            _build_table(store, filters.level, filters.tag, filters.search)

    def _set_filter(attr: str):
        def handler(e):
            setattr(filters, attr, e.value)
            refresh_table()

        return handler

    with ui.row().classes("q-gutter-md items-end q-mb-md"):
        ui.select(
            options=_get_level_options(store),
            label="Level",
            value=None,
            on_change=_set_filter("level"),
        ).classes("min-w-[150px]")

        ui.input(
            label="Filter by tag",
            on_change=_set_filter("tag"),
        ).props("clearable dense")

        ui.input(
            label="Search",
            on_change=_set_filter("search"),
        ).props("clearable dense")

        ui.button("Refresh", icon="refresh", on_click=refresh_table).props("flat")

    refresh_table()


def _get_level_options(store) -> dict:
    options = {None: "All Levels"}
    health = store.health()
    for level in sorted(health["entries_by_level"].keys()):
        lvl = int(level)
        label = f"{format_level_label(lvl)} ({lvl})"
        options[lvl] = label
    return options


def _build_table(store, level, tag, search_query) -> None:
    if search_query and search_query.strip():
        filter_levels = [level] if level is not None else None
        entries = store.query_fts(
            search_query.strip(), limit=100, filter_levels=filter_levels
        )
    else:
        entries = store.list_entries(
            tag=tag if tag else None,
            level=level,
        )

    if not entries:
        ui.label("No entries found.").classes("text-italic text-grey")
        return

    columns = [
        {
            "name": "key",
            "label": "Key",
            "field": "key",
            "align": "left",
            "sortable": True,
        },
        {"name": "level", "label": "Level", "field": "level_display", "align": "left"},
        {"name": "tags", "label": "Tags", "field": "tags", "align": "left"},
        {"name": "value", "label": "Value", "field": "value_snippet", "align": "left"},
        {
            "name": "updated",
            "label": "Updated",
            "field": "updated_at",
            "align": "left",
            "sortable": True,
        },
    ]

    rows = []
    for entry in entries:
        snippet = entry.value[:80] + "..." if len(entry.value) > 80 else entry.value
        level_label = format_level_label(entry)
        rows.append(
            {
                "id": entry.id,
                "key": entry.key,
                "level": entry.level,
                "level_display": level_label,
                "tags": entry.tags or "",
                "value_snippet": snippet,
                "updated_at": entry.updated_at or "",
            }
        )

    table = ui.table(
        columns=columns,
        rows=rows,
        row_key="id",
        pagination={"rowsPerPage": 20},
    ).classes("w-full")

    table.add_slot(
        "body-cell-key",
        r"""
        <q-td :props="props">
            <a class="cursor-pointer text-primary"
               @click="$parent.$emit('view', props.row)">
                {{ props.row.key }}
            </a>
        </q-td>
        """,
    )

    table.on("view", lambda e: _show_detail_dialog(store, e.args["id"]))


def _show_detail_dialog(store, entry_id: str) -> None:
    from lore.dashboard.pages.entry_detail import show_entry_detail

    show_entry_detail(store, entry_id)
