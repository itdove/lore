from __future__ import annotations

from pathlib import Path

from nicegui import app, ui

from lore.config.utils import is_configured

_STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> None:
    app.add_static_files("/static", str(_STATIC_DIR))

    @ui.page("/")
    def index():
        with ui.header().classes("items-center justify-between"):
            with ui.row().classes("items-center q-gutter-sm"):
                ui.image("/static/lore-logo.png").classes("w-10 h-10 rounded")
                ui.label("Lore Dashboard").classes("text-h5 text-weight-bold")

        if not is_configured():
            with ui.column().classes("w-full items-center q-pa-xl"):
                ui.icon("info", size="xl", color="warning")
                ui.label("Lore is not configured yet").classes(
                    "text-h5 text-weight-bold q-mt-md"
                )
                ui.label(
                    "Run 'lore init' in your project directory to set up "
                    "the knowledge base, then restart the dashboard."
                ).classes("text-body1 text-grey-8 q-mt-sm")
                with ui.card().classes("q-pa-md q-mt-lg bg-grey-2"):
                    ui.label("$ lore init").classes("font-mono text-body1")
            return

        with ui.left_drawer(value=True).classes("bg-grey-2"):
            tabs = ui.tabs().props("vertical").classes("w-full")
            with tabs:
                overview_tab = ui.tab("overview", label="Overview", icon="dashboard")
                browse_tab = ui.tab("browse", label="Browse", icon="search")
                create_tab = ui.tab("create", label="New Entry", icon="add_circle")
                conflicts_tab = ui.tab("conflicts", label="Conflicts", icon="warning")
                sync_tab = ui.tab("sync", label="Sync", icon="sync")

        with ui.tab_panels(tabs, value=overview_tab).classes("w-full h-full"):
            with ui.tab_panel(overview_tab):
                from lore.dashboard.pages.overview import render_overview

                render_overview()

            with ui.tab_panel(browse_tab):
                from lore.dashboard.pages.browser import render_browser

                render_browser()

            with ui.tab_panel(create_tab):
                from lore.dashboard.pages.individual import render_create_form

                render_create_form()

            with ui.tab_panel(conflicts_tab):
                from lore.dashboard.pages.conflicts import render_conflicts

                render_conflicts()

            with ui.tab_panel(sync_tab):
                from lore.dashboard.pages.sync import render_sync

                render_sync()
