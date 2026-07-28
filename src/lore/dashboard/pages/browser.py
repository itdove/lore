from __future__ import annotations

from dataclasses import dataclass

from nicegui import ui

from lore.dashboard.pages import format_level_label
from lore.dashboard.state import get_dashboard_store, reset_store


@dataclass
class _BrowserFilters:
    level: int | None = None
    tag: str = ""
    search: str = ""
    show_negated: bool = False


def render_browser() -> None:
    ui.label("Knowledge Browser").classes("text-h6 q-mb-md")

    store = get_dashboard_store()
    filters = _BrowserFilters()
    state: dict = {}

    def refresh_table():
        reset_store()
        tc = state["table_container"]
        tc.clear()
        with tc:
            _build_table(get_dashboard_store(), filters)

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

        ui.switch(
            "Show negated",
            value=False,
            on_change=_set_filter("show_negated"),
        ).props("dense")

        ui.button("Refresh", icon="refresh", on_click=lambda: refresh_table()).props(
            "flat"
        )

    state["table_container"] = ui.column().classes("w-full")

    refresh_table()


def _get_level_options(store) -> dict:
    from lore.config.manager import get_project_config
    from lore.dashboard.state import get_registered_projects

    health = store.health()
    counts = {int(k): v for k, v in health["entries_by_level"].items()}
    total = sum(counts.values())

    options: dict = {None: f"All Levels ({total})"}
    options[0] = f"Individual ({counts.get(0, 0)})"
    options[1] = f"Project ({counts.get(1, 0)})"

    for project_dir in get_registered_projects():
        try:
            cfg = get_project_config(project_dir)
            for h in cfg.hierarchy:
                if h.level not in options:
                    name = h.name or f"Level {h.level}"
                    c = counts.get(h.level, 0)
                    options[h.level] = f"{name} ({c})"
        except Exception:
            pass

    for lvl, c in sorted(counts.items()):
        if lvl not in options:
            options[lvl] = f"Level {lvl} ({c})"

    return options


def _build_table(store, filters: _BrowserFilters) -> None:
    if filters.search and filters.search.strip():
        filter_levels = [filters.level] if filters.level is not None else None
        entries = store.query_fts(
            filters.search.strip(),
            limit=100,
            filter_levels=filter_levels,
            include_negated=filters.show_negated,
        )
    else:
        entries = store.list_entries(
            tag=filters.tag if filters.tag else None,
            level=filters.level,
            include_negated=filters.show_negated,
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
        {"name": "status", "label": "", "field": "negated", "align": "left"},
        {"name": "level", "label": "Level", "field": "level_display", "align": "left"},
        {"name": "source", "label": "Source", "field": "source", "align": "left"},
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
                "source": _format_source(entry),
                "tags": entry.tags or "",
                "value_snippet": snippet,
                "updated_at": entry.updated_at or "",
                "negated": entry.negated or "",
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

    table.add_slot(
        "body-cell-status",
        r"""
        <q-td :props="props">
            <q-badge v-if="props.row.negated"
                     color="deep-purple" text-color="white"
                     label="NEGATED" />
        </q-td>
        """,
    )

    table.add_slot(
        "body-cell-value",
        r"""
        <q-td :props="props">
            <span v-if="props.row.negated"
                  class="text-strike text-grey">
                {{ props.row.value_snippet }}
            </span>
            <span v-else>{{ props.row.value_snippet }}</span>
        </q-td>
        """,
    )

    table.on("view", lambda e: _show_detail_dialog(store, e.args["id"]))


def _format_source(entry) -> str:
    if entry.level == 0:
        return "local"
    if not entry.repo_url:
        return ""
    url = entry.repo_url
    if "/" in url:
        url = url.rstrip("/").rsplit("/", 1)[-1]
    if url.endswith(".git"):
        url = url[:-4]
    return url


def _show_detail_dialog(store, entry_id: str) -> None:
    from lore.dashboard.pages.entry_detail import show_entry_detail

    show_entry_detail(store, entry_id)
