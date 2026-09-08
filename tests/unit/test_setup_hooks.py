from __future__ import annotations

import json

import pytest

from lore.setup.hooks import AGENT_CONFIGS, HookEvent, IDESetup, setup_agent


def test_setup_reexports_canonical_hook_event():
    assert HookEvent.PROMPT.value == "prompt"


def test_cursor_setup_preserves_settings_and_is_idempotent(tmp_path):
    project = tmp_path / "project"
    config_path = project / ".cursor" / "hooks.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps({"version": 1, "custom": True}))

    success, _ = setup_agent("cursor", project)
    assert success
    first = json.loads(config_path.read_text())

    success, _ = setup_agent("cursor", project)
    assert success
    assert json.loads(config_path.read_text()) == first
    assert first["custom"] is True
    assert first["hooks"]["beforeSubmitPrompt"][0]["command"].startswith(
        "lore hook recall"
    )
    assert first["hooks"]["postToolUse"][0]["command"].startswith("lore hook nudge")


@pytest.mark.parametrize(
    ("agent", "relative_path"),
    [
        ("claude", ".claude/settings.json"),
        ("codex", ".codex/hooks.json"),
        ("copilot", ".github/hooks/hooks.json"),
        ("windsurf", ".codeium/windsurf/hooks.json"),
        ("gemini", ".gemini/settings.json"),
        ("augment", ".augment/settings.json"),
    ],
)
def test_json_setup_targets_project_agent_location(tmp_path, agent, relative_path):
    success, message = setup_agent(agent, tmp_path)

    assert success, message
    assert (tmp_path / relative_path).exists()


@pytest.mark.parametrize(
    ("agent", "events"),
    [
        ("cline", ("UserPromptSubmit", "PostToolUse", "SessionEnd")),
        ("zoocode", ("UserPromptSubmit", "PostToolUse", "SessionEnd")),
        ("kiro", ("PromptSubmit", "PostToolUse", "SessionEnd")),
    ],
)
def test_script_setup_creates_executable_lifecycle_hooks(tmp_path, agent, events):
    success, message = setup_agent(agent, tmp_path)

    assert success, message
    for event in events:
        path = tmp_path / AGENT_CONFIGS[agent]["project_config_path"] / event
        assert path.exists()
        assert path.stat().st_mode & 0o111
        assert "lore hook" in path.read_text()


def test_opencode_setup_writes_plugin(tmp_path):
    success, message = setup_agent("opencode", tmp_path)

    assert success, message
    plugin = tmp_path / ".opencode" / "plugins" / "lore.ts"
    assert plugin.exists()
    assert "message.submit" in plugin.read_text()
    assert "--ide" in plugin.read_text()


def test_mcp_only_junie_setup_writes_guidance(tmp_path):
    success, message = setup_agent("junie", tmp_path)

    assert success, message
    guidance = tmp_path / ".junie" / "guidelines" / "lore.md"
    assert guidance.exists()
    assert "Lore MCP" in guidance.read_text()


def test_unknown_agent_is_rejected(tmp_path):
    success, message = IDESetup().setup_ide_hooks("unknown", tmp_path)

    assert success is False
    assert "Unsupported agent" in message


def test_dry_run_does_not_write(tmp_path):
    success, message = setup_agent("cursor", tmp_path, dry_run=True)

    assert success
    assert "DRY RUN" in message
    assert not (tmp_path / ".cursor").exists()
