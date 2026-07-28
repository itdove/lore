from __future__ import annotations

import json

from nicegui import ui

from lore.config.utils import state_dir


def render_capture() -> None:
    container = ui.column().classes("w-full")

    def refresh():
        container.clear()
        with container:
            _build_capture_view()

    with ui.row().classes("items-center q-mb-md"):
        ui.label("Capture History").classes("text-h6")
        ui.button(icon="refresh", on_click=lambda: refresh()).props("flat dense")

    refresh()


def _build_capture_view() -> None:
    log_path = state_dir() / "capture.jsonl"
    if not log_path.exists():
        ui.label("No capture history yet.").classes("text-italic text-grey")
        ui.label(
            "Captures are recorded when a Claude Code session ends "
            "and the SessionEnd hook extracts knowledge."
        ).classes("text-body2 text-grey q-mt-sm")
        return

    entries = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    if not entries:
        ui.label("No capture history yet.").classes("text-italic text-grey")
        return

    entries.reverse()

    for entry in entries:
        ts = entry.get("timestamp", "unknown")
        if "T" in ts:
            ts = ts.split("T")[0] + " " + ts.split("T")[1][:8]

        stored = entry.get("stored", 0)
        prs = entry.get("prs_created", 0)
        neg = entry.get("negated", 0)
        proposed = entry.get("proposed", 0)
        total = entry.get("total_actions", 0)

        with ui.expansion(
            f"{ts} — {total} actions ({stored} stored, {prs} PRs, "
            f"{neg} negated, {proposed} proposed)"
        ).classes("w-full q-mb-sm"):
            actions = entry.get("actions", [])
            if not actions:
                ui.label("No actions recorded.").classes("text-italic text-grey")
                continue

            columns = [
                {
                    "name": "action",
                    "label": "Action",
                    "field": "action",
                    "align": "left",
                },
                {"name": "key", "label": "Key", "field": "key", "align": "left"},
                {
                    "name": "detail",
                    "label": "Detail",
                    "field": "detail",
                    "align": "left",
                },
            ]

            rows = []
            for act in actions:
                detail = ""
                if act.get("level"):
                    detail = f"level: {act['level']}"
                if act.get("reason"):
                    detail = act["reason"]
                if act.get("from"):
                    detail = f"from: {act['from']}"
                if act.get("snippet"):
                    detail = act["snippet"][:80]

                rows.append(
                    {
                        "action": act.get("action", ""),
                        "key": act.get("key", ""),
                        "detail": detail,
                    }
                )

            ui.table(
                columns=columns,
                rows=rows,
                row_key="key",
            ).props(
                "dense flat bordered"
            ).classes("w-full")
