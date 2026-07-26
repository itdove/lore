from __future__ import annotations

import json
from typing import Callable

from nicegui import ui

from lore.dashboard.state import (
    get_registered_projects,
    load_raw_global_config,
    load_raw_project_config,
    save_global_config,
    save_project_config,
)


def render_config() -> None:
    ui.label("Configuration").classes("text-h6 q-mb-md")

    with ui.tabs().classes("w-full") as tabs:
        global_tab = ui.tab("global", label="Global", icon="public")
        project_tab = ui.tab("project", label="Project", icon="folder")

    with ui.tab_panels(tabs, value=global_tab).classes("w-full"):
        with ui.tab_panel(global_tab):
            _editor_scaffold(
                load_raw_global_config,
                save_global_config,
                "Global config saved. Restart MCP server to apply.",
                _render_global_form,
            )
        with ui.tab_panel(project_tab):
            _render_project_tab()


def _editor_scaffold(
    load_fn: Callable[[], dict],
    save_fn: Callable[[dict], None],
    success_msg: str,
    form_renderer: Callable[[dict, Callable], None],
) -> None:
    data = load_fn()
    raw_mode = {"active": False}
    form_container = ui.column().classes("w-full")
    raw_container = ui.column().classes("w-full")

    def do_save():
        save_fn(data)
        ui.notify(success_msg, type="positive")

    def refresh_view():
        form_container.clear()
        raw_container.clear()
        if raw_mode["active"]:
            with raw_container:
                _render_raw_editor(data, do_save)
        else:
            with form_container:
                form_renderer(data, do_save)

    def toggle_raw(e):
        raw_mode["active"] = e.value
        refresh_view()

    with ui.row().classes("items-center q-mb-md"):
        ui.switch("Raw JSON", on_change=toggle_raw)

    refresh_view()


def _render_global_form(data: dict, save_fn) -> None:
    lore = data.setdefault("lore", {})

    with ui.card().classes("w-full q-mb-md"):
        ui.label("Embedding (global-only)").classes("text-subtitle1 text-weight-bold")
        ui.label(
            "Shared across all projects — all entries must use " "the same vector space"
        ).classes("text-caption text-grey q-mb-sm")

        search = lore.setdefault("search", {})

        ui.select(
            ["none", "ollama"],
            label="Embedding Provider",
            value=search.get("embedding_provider", "none"),
            on_change=lambda e: search.update(embedding_provider=e.value),
        ).classes("w-full max-w-xs")

        ui.input(
            label="Embedding Model",
            value=search.get("embedding_model", ""),
            on_change=lambda e: search.update(embedding_model=e.value),
        ).classes("w-full max-w-xs")

        ui.input(
            label="Embedding Base URL",
            value=search.get("embedding_base_url", ""),
            on_change=lambda e: search.update(embedding_base_url=e.value),
        ).classes("w-full max-w-xs")

    with ui.card().classes("w-full q-mb-md"):
        ui.label("Store (global-only)").classes("text-subtitle1 text-weight-bold")
        store = lore.setdefault("store", {})

        ui.input(
            label="Database Path",
            value=store.get("path", ""),
            on_change=lambda e: store.update(path=e.value),
        ).classes("w-full max-w-md")

    with ui.card().classes("w-full q-mb-md"):
        ui.label("Default LLM").classes("text-subtitle1 text-weight-bold")
        ui.label("Default LLM for synthesis — projects can override").classes(
            "text-caption text-grey q-mb-sm"
        )

        llm = lore.setdefault("llm", {})

        ui.select(
            ["none", "ollama"],
            label="Provider",
            value=llm.get("provider", "none"),
            on_change=lambda e: llm.update(provider=e.value),
        ).classes("w-full max-w-xs")

        ui.input(
            label="Model",
            value=llm.get("model", ""),
            on_change=lambda e: llm.update(model=e.value),
        ).classes("w-full max-w-xs")

    with ui.card().classes("w-full q-mb-md"):
        ui.label("Default Sync").classes("text-subtitle1 text-weight-bold")
        sync = lore.setdefault("sync", {})

        ui.switch(
            "Auto Sync",
            value=sync.get("auto_sync", True),
            on_change=lambda e: sync.update(auto_sync=e.value),
        )

        ui.number(
            label="Staleness Threshold (minutes)",
            value=sync.get("staleness_threshold_minutes", 60),
            min=1,
            on_change=lambda e: sync.update(staleness_threshold_minutes=int(e.value)),
        ).classes("w-full max-w-xs")

    with ui.card().classes("w-full q-mb-md"):
        ui.label("Default Git").classes("text-subtitle1 text-weight-bold")
        git = lore.setdefault("git", {})

        ui.select(
            ["github"],
            label="Provider",
            value=git.get("provider", "github"),
            on_change=lambda e: git.update(provider=e.value),
        ).classes("w-full max-w-xs")

    ui.button("Save", icon="save", on_click=save_fn).props("color=primary")


def _render_project_tab() -> None:
    from pathlib import Path

    projects = get_registered_projects()

    if not projects:
        ui.label("No projects registered.").classes("text-italic text-grey")
        ui.label("Run 'lore init' in a project directory " "to register it.").classes(
            "text-caption text-grey"
        )
        return

    cwd = str(Path.cwd())
    default = cwd if cwd in projects else projects[0]
    options = {p: Path(p).name for p in projects}

    state = {"selected": default}

    def on_project_change(e):
        state["selected"] = e.value
        refresh_editor()

    ui.select(
        options=options,
        label="Project",
        value=state["selected"],
        on_change=on_project_change,
    ).classes("w-full max-w-lg q-mb-md")

    editor_container = ui.column().classes("w-full")

    def load_project():
        return load_raw_project_config(state["selected"])

    def save_project(data):
        save_project_config(data, state["selected"])

    def refresh_editor():
        editor_container.clear()
        with editor_container:
            ui.label(state["selected"]).classes("text-caption text-grey q-mb-sm")
            _editor_scaffold(
                load_project,
                save_project,
                f"Project config saved for " f"{Path(state['selected']).name}.",
                _render_project_form,
            )

    refresh_editor()


def _labeled_slider(label: str, section: dict, key: str, default: float) -> None:
    with ui.row().classes("items-center q-gutter-md w-full"):
        ui.label(label).classes("text-caption")
        val_label = ui.label(f"{section.get(key, default):.2f}")
        ui.slider(
            min=0,
            max=1,
            step=0.05,
            value=section.get(key, default),
            on_change=lambda e: (
                section.update({key: e.value}),
                val_label.set_text(f"{e.value:.2f}"),
            ),
        ).classes("w-48")


def _render_project_form(data: dict, save_fn) -> None:
    lore = data.setdefault("lore", {})
    hierarchy = lore.setdefault("hierarchy", [])

    with ui.card().classes("w-full q-mb-md"):
        ui.label("Hierarchy Levels").classes("text-subtitle1 text-weight-bold")

        table_container = ui.column().classes("w-full")

        def refresh_table():
            table_container.clear()
            with table_container:
                _render_hierarchy_table(hierarchy, refresh_table)

        refresh_table()

        def add_level():
            next_level = (
                max(
                    (h.get("level", 0) for h in hierarchy),
                    default=0,
                )
                + 1
            )
            hierarchy.append(
                {
                    "level": next_level,
                    "repo": "",
                    "branch": "main",
                    "name": "",
                    "writable": True,
                }
            )
            refresh_table()

        ui.button("Add Level", icon="add", on_click=add_level).props(
            "flat color=primary"
        ).classes("q-mt-sm")

    with ui.card().classes("w-full q-mb-md"):
        ui.label("LLM Override").classes("text-subtitle1 text-weight-bold")
        ui.label("Override global LLM for this project's synthesis").classes(
            "text-caption text-grey q-mb-sm"
        )

        llm = lore.setdefault("llm", {})
        with ui.row().classes("q-gutter-md"):
            ui.select(
                ["", "none", "ollama"],
                label="LLM Provider",
                value=llm.get("provider", ""),
                on_change=lambda e: (
                    llm.update(provider=e.value)
                    if e.value
                    else llm.pop("provider", None)
                ),
            ).classes("max-w-xs")

            ui.input(
                label="LLM Model",
                value=llm.get("model", ""),
                on_change=lambda e: llm.update(model=e.value),
            ).classes("max-w-xs")

    with ui.card().classes("w-full q-mb-md"):
        ui.label("Search Thresholds").classes("text-subtitle1 text-weight-bold")
        search = lore.setdefault("search", {})
        _labeled_slider("Min Similarity", search, "min_similarity", 0.3)
        _labeled_slider(
            "Dedup Threshold",
            search,
            "dedup_threshold",
            0.20,
        )

    with ui.card().classes("w-full q-mb-md"):
        ui.label("Sync").classes("text-subtitle1 text-weight-bold")
        sync = lore.setdefault("sync", {})

        ui.switch(
            "Auto Sync",
            value=sync.get("auto_sync", True),
            on_change=lambda e: sync.update(auto_sync=e.value),
        )

    with ui.card().classes("w-full q-mb-md"):
        ui.label("Git").classes("text-subtitle1 text-weight-bold")
        git = lore.setdefault("git", {})

        ui.select(
            ["github"],
            label="Provider",
            value=git.get("provider", "github"),
            on_change=lambda e: git.update(provider=e.value),
        ).classes("w-full max-w-xs")

    ui.button("Save", icon="save", on_click=save_fn).props("color=primary")


def _render_hierarchy_table(hierarchy: list, refresh_fn) -> None:
    if not hierarchy:
        ui.label("No hierarchy levels configured.").classes("text-italic text-grey")
        return

    for idx, h in enumerate(hierarchy):
        with ui.card().classes("w-full q-pa-sm q-mb-xs"):
            with ui.row().classes("items-center q-gutter-sm w-full"):
                ui.badge(f"Level {h.get('level', idx + 1)}").classes("q-mr-sm")
                ui.input(
                    label="Name",
                    value=h.get("name", ""),
                    on_change=lambda e, h=h: h.update(name=e.value),
                ).classes("max-w-[120px]")
                ui.input(
                    label="Repo URL",
                    value=h.get("repo", ""),
                    on_change=lambda e, h=h: h.update(repo=e.value),
                ).classes("col")
                ui.input(
                    label="Branch",
                    value=h.get("branch", "main"),
                    on_change=lambda e, h=h: h.update(branch=e.value),
                ).classes("max-w-[100px]")
                ui.switch(
                    "Writable",
                    value=h.get("writable", True),
                    on_change=lambda e, h=h: h.update(writable=e.value),
                )

                def remove(i=idx):
                    hierarchy.pop(i)
                    refresh_fn()

                ui.button(
                    icon="delete",
                    on_click=remove,
                    color="negative",
                ).props("flat dense round")


def _render_raw_editor(data: dict, save_fn) -> None:
    raw_text = json.dumps(data, indent=2)
    textarea = (
        ui.textarea(
            label="JSON Configuration",
            value=raw_text,
        )
        .classes("w-full font-mono")
        .props("rows=20")
    )

    def save_raw():
        try:
            parsed = json.loads(textarea.value)
        except json.JSONDecodeError as exc:
            ui.notify(f"Invalid JSON: {exc}", type="negative")
            return
        if not isinstance(parsed, dict):
            ui.notify(
                "Config must be a JSON object",
                type="negative",
            )
            return
        data.clear()
        data.update(parsed)
        save_fn()

    ui.button("Save JSON", icon="save", on_click=save_raw).props(
        "color=primary"
    ).classes("q-mt-sm")
