from __future__ import annotations

from pathlib import Path

from nicegui import app, ui

from lore.config.utils import is_configured

_STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> None:
    app.add_static_files("/static", str(_STATIC_DIR))

    @ui.page("/")
    def index(tab: str = "overview"):
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
                capture_tab = ui.tab("capture", label="Capture", icon="auto_fix_high")
                logs_tab = ui.tab("logs", label="Logs", icon="article")
                config_tab = ui.tab("config", label="Config", icon="settings")

        tab_map = {
            "overview": overview_tab,
            "browse": browse_tab,
            "create": create_tab,
            "conflicts": conflicts_tab,
            "sync": sync_tab,
            "capture": capture_tab,
            "logs": logs_tab,
            "config": config_tab,
        }
        initial_tab = tab_map.get(tab, overview_tab)

        browse_container = None
        capture_container = None
        logs_container = None

        def on_tab_change(e):
            if e.value == "browse" and browse_container is not None:
                browse_container.clear()
                with browse_container:
                    from lore.dashboard.pages.browser import render_browser

                    render_browser()
            elif e.value == "capture" and capture_container is not None:
                capture_container.clear()
                with capture_container:
                    from lore.dashboard.pages.capture import render_capture

                    render_capture()
            elif e.value == "logs" and logs_container is not None:
                logs_container.clear()
                with logs_container:
                    from lore.dashboard.pages.logs import render_logs

                    render_logs()

        with ui.tab_panels(tabs, value=initial_tab, on_change=on_tab_change).classes(
            "w-full h-full"
        ):
            with ui.tab_panel(overview_tab):
                from lore.dashboard.pages.overview import render_overview

                render_overview()

            with ui.tab_panel(browse_tab):
                browse_container = ui.column().classes("w-full")
                with browse_container:
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

            with ui.tab_panel(capture_tab):
                capture_container = ui.column().classes("w-full")
                with capture_container:
                    from lore.dashboard.pages.capture import render_capture

                    render_capture()

            with ui.tab_panel(logs_tab):
                logs_container = ui.column().classes("w-full")
                with logs_container:
                    from lore.dashboard.pages.logs import render_logs

                    render_logs()

            with ui.tab_panel(config_tab):
                from lore.dashboard.pages.config_editor import render_config

                render_config()
