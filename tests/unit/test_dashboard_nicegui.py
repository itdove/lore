from __future__ import annotations

import json
import warnings
from unittest import mock

import pytest
from nicegui import app
from nicegui.client import Client
from nicegui.page import page
from nicegui.testing.general import nicegui_reset_globals, prepare_simulation

import lore.dashboard as dashboard
import lore.dashboard.app as dashboard_app
import lore.dashboard.state as dashboard_state
from lore.config.loaders import _clear_config_cache, save_config
from lore.dashboard.state import reset_store
from lore.store.base import KnowledgeEntry
from lore.store.sqlite import SQLiteStore, create_schema


@pytest.fixture(autouse=True)
def _reset_dashboard_state():
    reset_store()
    yield
    reset_store()


@pytest.fixture
def dashboard_demo(tmp_path, monkeypatch):
    project_dir = tmp_path / "project"
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    cache_dir = tmp_path / "cache"
    state_dir = tmp_path / "state"
    project_dir.joinpath(".lore").mkdir(parents=True)
    for directory in (config_dir, data_dir, cache_dir, state_dir):
        directory.mkdir(exist_ok=True)

    monkeypatch.chdir(project_dir)
    monkeypatch.setenv("LORE_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("LORE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("LORE_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("LORE_STATE_DIR", str(state_dir))
    _clear_config_cache()

    database_path = data_dir / "knowledge.db"
    save_config(
        config_dir / "config.json",
        {
            "lore": {
                "projects": [str(project_dir)],
                "search": {"embedding_provider": "none"},
                "store": {"path": str(database_path)},
                "git": {"provider": "github"},
            }
        },
    )
    save_config(
        project_dir / ".lore" / "config.json",
        {
            "lore": {
                "hierarchy": [
                    {
                        "level": 2,
                        "name": "Team",
                        "repo": "https://github.com/example/lore-demo",
                        "branch": "main",
                        "writable": True,
                    }
                ]
            }
        },
    )

    connection = create_schema(str(database_path))
    store = SQLiteStore(connection)
    store.store(
        KnowledgeEntry(
            key="demo:dashboard:individual",
            value="Individual dashboard smoke-test entry.",
            tags="demo, dashboard",
            level=0,
            level_name="individual",
        )
    )
    store.store(
        KnowledgeEntry(
            key="demo:dashboard:team",
            value="Team-level dashboard smoke-test entry.",
            tags="demo, team",
            level=2,
            level_name="Team",
            repo_url="https://github.com/example/lore-demo",
            repo_branch="main",
            provenance=json.dumps({"file_path": "knowledge/demo/dashboard.md"}),
        )
    )
    conflict_a = store.store(
        KnowledgeEntry(
            key="demo:dashboard:conflict",
            value="Local conflict value.",
            level=0,
            level_name="individual",
        )
    )
    conflict_b = store.store(
        KnowledgeEntry(
            key="demo:dashboard:conflict",
            value="Team conflict value.",
            level=2,
            level_name="Team",
            repo_url="https://github.com/example/lore-demo",
            repo_branch="main",
        )
    )
    store.apply_conflict(conflict_a, conflict_b)
    store.commit()

    (state_dir / "capture.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-09-08T18:00:00+00:00",
                "total_actions": 1,
                "stored": 1,
                "prs_created": 0,
                "negated": 0,
                "proposed": 0,
                "actions": [
                    {
                        "action": "stored",
                        "key": "demo:dashboard:individual",
                        "reason": "smoke test",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (state_dir / "lore.log").write_text(
        "2026-09-08T18:00:00Z INFO dashboard smoke test\n", encoding="utf-8"
    )

    yield project_dir

    connection.close()
    _clear_config_cache()


@pytest.fixture
def nicegui_client():
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"coroutine '(Timer\._run_in_loop|Outbox\.loop)' was never awaited",
            category=RuntimeWarning,
            module=r"nicegui\.app\.app",
        )
        with nicegui_reset_globals():
            prepare_simulation()
            client = Client(page("/"))
            try:
                yield client
            finally:
                client.delete()
                store = dashboard_state._store_instance
                reset_store()
                if store is not None:
                    store._conn.close()


def _active_elements(client: Client, type_name: str):
    return [
        element
        for element in client.elements.values()
        if type(element).__name__ == type_name
        and not getattr(element, "_deleted", False)
    ]


def _browser_table(client: Client):
    return next(
        table
        for table in _active_elements(client, "Table")
        if table.rows and "value_snippet" in table.rows[0]
    )


def _send_event(client: Client, element, event_type: str, *args) -> None:
    listener = next(
        listener
        for listener in element._event_listeners.values()
        if listener.type == event_type
    )
    client.handle_event(
        {
            "id": element.id,
            "listener_id": listener.id,
            "args": [json.dumps(arg) for arg in args],
        }
    )


def test_configured_dashboard_renders_all_tabs_and_static_route(
    dashboard_demo, nicegui_client
):
    with mock.patch("nicegui.ui.page", return_value=lambda function: function):
        dashboard_app.create_app()
    with nicegui_client:
        dashboard_app.render_dashboard()

    tab_labels = {
        element._props.get("label")
        for element in _active_elements(nicegui_client, "Tab")
    }
    assert tab_labels >= {
        "Overview",
        "Browse",
        "New Entry",
        "Conflicts",
        "Sync",
        "Capture",
        "Logs",
        "Config",
    }
    assert len(_browser_table(nicegui_client).rows) == 4
    assert any(row["level"] == 2 for row in _browser_table(nicegui_client).rows)
    assert any(
        row["action"] == "stored"
        for table in _active_elements(nicegui_client, "Table")
        for row in table.rows
        if "action" in row
    )
    assert "/static/{path:path}" in {
        route.path for route in app.routes if hasattr(route, "path")
    }


def test_browser_filter_rebuilds_table_with_nicegui_3(dashboard_demo, nicegui_client):
    with nicegui_client:
        dashboard_app.render_dashboard()

        level_select = next(
            element
            for element in _active_elements(nicegui_client, "Select")
            if element._props.get("label") == "Level"
        )
        option_index = list(level_select.options).index(2)
        _send_event(
            nicegui_client,
            level_select,
            "update:modelValue",
            {"value": option_index, "label": level_select.options[2]},
        )

    rows = _browser_table(nicegui_client).rows
    assert rows
    assert {row["level"] for row in rows} == {2}


def test_tab_navigation_and_entry_detail_work(dashboard_demo, nicegui_client):
    with nicegui_client:
        dashboard_app.render_dashboard()

        tab_panels = [
            panel
            for panel in _active_elements(nicegui_client, "TabPanels")
            if panel._props.get("model-value") == "overview"
        ]
        assert len(tab_panels) == 1
        _send_event(nicegui_client, tab_panels[0], "update:modelValue", "browse")

        table = _browser_table(nicegui_client)
        row = table.rows[0]
        _send_event(nicegui_client, table, "view", row)

    assert any(
        getattr(element, "_text", None) == row["key"]
        for element in nicegui_client.elements.values()
    )
    assert _active_elements(nicegui_client, "Dialog")


def test_launch_passes_supported_nicegui_run_options():
    with nicegui_reset_globals():
        prepare_simulation()
        with (
            mock.patch("lore.dashboard.app.create_app") as create_app,
            mock.patch("nicegui.ui.run") as run,
        ):
            dashboard.launch(host="0.0.0.0", port=9876)

        create_app.assert_called_once()
        run.assert_called_once()
        kwargs = run.call_args.kwargs
        assert kwargs["host"] == "0.0.0.0"
        assert kwargs["port"] == 9876
        assert kwargs["title"] == "Lore Dashboard"
        assert kwargs["reload"] is False
        assert kwargs["favicon"].startswith("data:image/png;base64,")
