from __future__ import annotations

import os
from unittest import mock

import pytest

from lore.hook_adapters import (
    ADAPTER_CLASSES,
    AiderDeskAdapter,
    AugmentAdapter,
    BaseAgentAdapter,
    ClineAdapter,
    CodexAdapter,
    CopilotAdapter,
    CursorAdapter,
    GeminiCLIAdapter,
    HookEvent,
    JunieAdapter,
    KiroAdapter,
    OpenClawAdapter,
    OpenCodeAdapter,
    WindsurfAdapter,
    detect_adapter,
)
from lore.hook_adapters.base import NormalizedHookInput


def test_normalized_hook_input_defaults_are_isolated():
    first = NormalizedHookInput(event=HookEvent.PROMPT)
    second = NormalizedHookInput(event=HookEvent.PROMPT)

    first.tool_input["command"] = "pwd"
    assert second.tool_input == {}


@pytest.mark.parametrize(
    ("payload", "adapter_type", "event"),
    [
        (
            {"hook_event_name": "UserPromptSubmit", "prompt": "hello"},
            BaseAgentAdapter,
            HookEvent.PROMPT,
        ),
        (
            {"cursor_version": "1", "hook_event_name": "beforeReadFile"},
            CursorAdapter,
            HookEvent.BEFORE_READ_FILE,
        ),
        (
            {"toolName": "read_file", "toolArgs": '{"path": "a.py"}'},
            CopilotAdapter,
            HookEvent.PRE_TOOL_USE,
        ),
        (
            {"agent_action_name": "post_run_command"},
            WindsurfAdapter,
            HookEvent.POST_TOOL_USE,
        ),
        (
            {"gemini_version": "1", "hook_event_name": "AfterTool"},
            GeminiCLIAdapter,
            HookEvent.POST_TOOL_USE,
        ),
        (
            {"clineVersion": "1", "hook_event_name": "PreToolUse"},
            ClineAdapter,
            HookEvent.PRE_TOOL_USE,
        ),
        (
            {"kiro_hook_type": "prompt", "hook_event_name": "prompt_submit"},
            KiroAdapter,
            HookEvent.PROMPT,
        ),
        (
            {
                "is_mcp_tool": False,
                "tool_name": "launch-process",
                "hook_event_name": "PreToolUse",
            },
            AugmentAdapter,
            HookEvent.PRE_TOOL_USE,
        ),
        (
            {"opencode_version": "1", "hook_event_name": "tool.execute.after"},
            OpenCodeAdapter,
            HookEvent.POST_TOOL_USE,
        ),
    ],
)
def test_detect_adapter_and_normalize(payload, adapter_type, event):
    adapter = detect_adapter(payload)

    assert isinstance(adapter, adapter_type)
    assert adapter.normalize(payload).event == event


def test_cursor_normalizes_command_and_synthesizes_bash():
    payload = {
        "hook_name": "beforeShellExecution",
        "command": "pytest",
        "cwd": "/project",
        "conversation_id": "session-1",
    }

    normalized = CursorAdapter().normalize(payload)

    assert normalized.event is HookEvent.PRE_TOOL_USE
    assert normalized.tool_name == "Bash"
    assert normalized.tool_input == {"command": "pytest"}
    assert normalized.working_dir == "/project"
    assert normalized.session_id == "session-1"


def test_copilot_decodes_tool_args_and_file_path():
    payload = {
        "toolName": "read_file",
        "toolArgs": '{"file_path": "/tmp/example.py"}',
        "cwd": "/project",
        "sessionId": "copilot-session",
    }

    normalized = CopilotAdapter().normalize(payload)

    assert normalized.tool_input == {"file_path": "/tmp/example.py"}
    assert normalized.file_path == "/tmp/example.py"
    assert normalized.session_id == "copilot-session"


def test_augment_maps_agent_tool_names():
    normalized = AugmentAdapter().normalize(
        {
            "is_mcp_tool": False,
            "tool_name": "str-replace-editor",
            "hook_event_name": "PreToolUse",
        }
    )

    assert normalized.tool_name == "Edit"


def test_explicit_and_environment_selection_take_priority():
    with mock.patch.dict(os.environ, {"LORE_IDE_TYPE": "claude"}, clear=True):
        assert isinstance(detect_adapter({"_ide_type": "cursor"}), CursorAdapter)
        assert isinstance(detect_adapter({}), BaseAgentAdapter)


def test_registry_contains_all_agent_adapter_classes():
    assert len(ADAPTER_CLASSES) == 13
    assert AiderDeskAdapter in ADAPTER_CLASSES
    assert OpenClawAdapter in ADAPTER_CLASSES
    assert CodexAdapter in ADAPTER_CLASSES
    assert JunieAdapter in ADAPTER_CLASSES


def test_codex_and_mcp_only_junie_are_explicit_adapters():
    assert isinstance(detect_adapter({}, ide_type="codex"), CodexAdapter)
    assert isinstance(detect_adapter({}, ide_type="junie"), JunieAdapter)
    assert JunieAdapter.can_handle({}) is False
