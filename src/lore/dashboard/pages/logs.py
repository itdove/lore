from __future__ import annotations

from nicegui import ui

from lore.config.utils import state_dir

_MAX_LINES = 200


def render_logs() -> None:
    container = ui.column().classes("w-full")

    def refresh():
        container.clear()
        with container:
            _build_log_view()

    with ui.row().classes("items-center q-mb-md"):
        ui.label("Logs").classes("text-h6")
        ui.button(icon="refresh", on_click=lambda: refresh()).props("flat dense")

    refresh()


def _build_log_view() -> None:
    log_path = state_dir() / "lore.log"
    if not log_path.exists():
        ui.label("No log entries yet.").classes("text-italic text-grey")
        return

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    lines = lines[-_MAX_LINES:]

    if not lines:
        ui.label("No log entries yet.").classes("text-italic text-grey")
        return

    ui.label(f"Showing last {len(lines)} lines from {log_path}").classes(
        "text-caption text-grey q-mb-sm"
    )
    ui.code("\n".join(lines)).classes("w-full").style(
        "max-height: 600px; overflow-y: auto; font-size: 12px"
    )
