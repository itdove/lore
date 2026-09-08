"""Per-agent hook registration.

The hook payloads differ between agents, but setup is intentionally small:
each writer adds Lore's recall, nudge, and capture commands while preserving
unrelated user configuration and remaining idempotent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lore.hook_adapters import SUPPORTED_IDES, HookEvent

SUPPORTED_AGENTS = SUPPORTED_IDES


def _command(agent: str, action: str) -> str:
    suffix = "" if agent in {"claude", "codex"} else f" --ide {agent}"
    return f"lore hook {action}{suffix}"


def _event_commands(agent: str) -> dict[str, str]:
    recall = _command(agent, "recall")
    nudge = _command(agent, "nudge")
    capture = _command(agent, "capture")
    return {
        "claude": {
            "UserPromptSubmit": recall,
            "PostToolUse": nudge,
            "SessionEnd": capture,
        },
        "codex": {
            "UserPromptSubmit": recall,
            "PostToolUse": nudge,
            "SessionEnd": capture,
        },
        "cursor": {
            "beforeSubmitPrompt": recall,
            "postToolUse": nudge,
        },
        "copilot": {
            "userPromptSubmitted": recall,
            "postToolUse": nudge,
        },
        "windsurf": {
            "pre_user_prompt": recall,
            "post_run_command": nudge,
            "post_read_code": nudge,
            "post_write_code": nudge,
            "post_mcp_tool_use": nudge,
        },
        "gemini": {
            "BeforeAgent": recall,
            "AfterTool": nudge,
        },
        "augment": {
            "PostToolUse": nudge,
        },
    }.get(agent, {})


# config_path values mirror the agent locations used by ai-guardian. The
# project_config_path values keep Lore's integrations project-scoped by
# default, as required by Lore's opt-in setup model.
AGENT_CONFIGS: dict[str, dict[str, Any]] = {
    "claude": {
        "name": "Claude Code",
        "config_path": "~/.claude/settings.json",
        "project_config_path": ".claude/settings.json",
        "kind": "nested",
        "hooks": _event_commands("claude"),
    },
    "cursor": {
        "name": "Cursor",
        "config_path": "~/.cursor/hooks.json",
        "project_config_path": ".cursor/hooks.json",
        "kind": "top_level",
        "hooks": _event_commands("cursor"),
        "version": 1,
        "nested_hooks_key": "hooks",
    },
    "copilot": {
        "name": "GitHub Copilot",
        "config_path": "~/.github/hooks/hooks.json",
        "project_config_path": ".github/hooks/hooks.json",
        "kind": "top_level",
        "hooks": _event_commands("copilot"),
    },
    "codex": {
        "name": "OpenAI Codex",
        "config_path": "~/.codex/hooks.json",
        "project_config_path": ".codex/hooks.json",
        "kind": "nested",
        "hooks": _event_commands("codex"),
        "post_tool_matcher": ".*",
    },
    "windsurf": {
        "name": "Windsurf",
        "config_path": "~/.codeium/windsurf/hooks.json",
        "project_config_path": ".codeium/windsurf/hooks.json",
        "kind": "top_level",
        "hooks": _event_commands("windsurf"),
        "nested_hooks_key": "hooks",
    },
    "gemini": {
        "name": "Google Gemini CLI",
        "config_path": "~/.gemini/settings.json",
        "project_config_path": ".gemini/settings.json",
        "kind": "event_list",
        "hooks": _event_commands("gemini"),
    },
    "cline": {
        "name": "Cline / ZooCode",
        "config_path": ".clinerules/hooks",
        "project_config_path": ".clinerules/hooks",
        "kind": "scripts",
        "scripts": {
            "UserPromptSubmit": "recall",
            "PostToolUse": "nudge",
            "SessionEnd": "capture",
        },
    },
    "zoocode": {
        "name": "Cline / ZooCode",
        "config_path": ".clinerules/hooks",
        "project_config_path": ".clinerules/hooks",
        "kind": "scripts",
        "scripts": {
            "UserPromptSubmit": "recall",
            "PostToolUse": "nudge",
            "SessionEnd": "capture",
        },
    },
    "kiro": {
        "name": "Kiro",
        "config_path": ".kiro/hooks",
        "project_config_path": ".kiro/hooks",
        "kind": "scripts",
        "scripts": {
            "PromptSubmit": "recall",
            "PostToolUse": "nudge",
            "SessionEnd": "capture",
        },
    },
    "augment": {
        "name": "Augment Code",
        "config_path": "~/.augment/settings.json",
        "project_config_path": ".augment/settings.json",
        "kind": "nested_wrapper",
        "hooks": _event_commands("augment"),
    },
    "opencode": {
        "name": "OpenCode",
        "config_path": "~/.config/opencode/plugins",
        "project_config_path": ".opencode/plugins",
        "kind": "plugin",
    },
    "aiderdesk": {
        "name": "AiderDesk",
        "config_path": "~/.aider-desk/extensions/lore",
        "project_config_path": ".aider-desk/extensions/lore",
        "kind": "extension",
    },
    "openclaw": {
        "name": "OpenClaw",
        "config_path": "~/.openclaw/plugins/lore",
        "project_config_path": ".openclaw/plugins/lore",
        "kind": "extension",
    },
    "junie": {
        "name": "Junie",
        "config_path": ".junie/guidelines/lore.md",
        "project_config_path": ".junie/guidelines/lore.md",
        "kind": "mcp_only",
    },
}

IDE_CONFIGS = AGENT_CONFIGS


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _contains_command(value: Any, command: str) -> bool:
    if isinstance(value, dict):
        if value.get("command") == command:
            return True
        return any(_contains_command(item, command) for item in value.values())
    if isinstance(value, list):
        return any(_contains_command(item, command) for item in value)
    return False


def _merge_nested_hooks(
    data: dict[str, Any],
    hooks_by_event: dict[str, str],
    *,
    post_tool_matcher: str = "",
) -> None:
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks

    for event, command in hooks_by_event.items():
        entries = hooks.get(event, [])
        if not isinstance(entries, list):
            entries = []
        if _contains_command(entries, command):
            hooks[event] = entries
            continue
        matcher = post_tool_matcher if event == "PostToolUse" else ""
        entries.append(
            {
                "matcher": matcher,
                "hooks": [{"type": "command", "command": command}],
            }
        )
        hooks[event] = entries


def _merge_top_level_hooks(
    data: dict[str, Any],
    hooks_by_event: dict[str, str],
    *,
    nested_key: str | None = None,
) -> None:
    target: dict[str, Any] = data
    if nested_key:
        value = data.setdefault(nested_key, {})
        if not isinstance(value, dict):
            value = {}
            data[nested_key] = value
        target = value

    for event, command in hooks_by_event.items():
        entries = target.get(event, [])
        if not isinstance(entries, list):
            entries = []
        if not _contains_command(entries, command):
            entries.append({"command": command})
        target[event] = entries


def _merge_event_list(
    data: dict[str, Any],
    hooks_by_event: dict[str, str],
) -> None:
    entries = data.setdefault("hooks", [])
    if not isinstance(entries, list):
        entries = []
        data["hooks"] = entries
    for event, command in hooks_by_event.items():
        if any(
            isinstance(item, dict)
            and item.get("event") == event
            and item.get("command") == command
            for item in entries
        ):
            continue
        item: dict[str, Any] = {"event": event, "command": command}
        if event in {"BeforeTool", "AfterTool"}:
            item["matcher"] = ".*"
        entries.append(item)


def _write_script(path: Path, command: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\nexec {command}\n", encoding="utf-8")
    path.chmod(0o755)


def _write_plugin(path: Path, agent: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """// Generated by Lore. OpenCode calls this plugin for lifecycle events.
import {{ execFileSync }} from "node:child_process";

function runLore(action, payload) {{
  return execFileSync(
    "lore",
    ["hook", action, "--ide", "{agent}"],
    {{ input: JSON.stringify(payload ?? {{}}), encoding: "utf8" }},
  );
}}

export default function lorePlugin() {{
  return {{
    hooks: {{
      "message.submit": (payload) => runLore("recall", payload),
      "tool.execute.after": (payload) => runLore("nudge", payload),
      "session.idle": (payload) => runLore("capture", payload),
    }},
  }};
}}
""".format(agent=agent),
        encoding="utf-8",
    )


def _write_extension(path: Path, agent: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "index.js").write_text(
        """// Generated by Lore for {agent}.
const {{ execFileSync }} = require("node:child_process");

function loreHook(action, payload) {{
  return execFileSync(
    "lore",
    ["hook", action, "--ide", "{agent}"],
    {{ input: JSON.stringify(payload ?? {{}}), encoding: "utf8" }},
  );
}}

module.exports = {{
  name: "lore",
  loreHook,
  hooks: {{
    "message.submit": (payload) => loreHook("recall", payload),
    "tool.execute.after": (payload) => loreHook("nudge", payload),
    "session.idle": (payload) => loreHook("capture", payload),
  }},
}};
""".format(agent=agent),
        encoding="utf-8",
    )


def _script_action(event: str) -> str:
    normalized = event.casefold()
    if "prompt" in normalized or "submit" in normalized:
        return "recall"
    if "sessionend" in normalized or normalized == "stop":
        return "capture"
    return "nudge"


class IDESetup:
    """Install or update Lore's hooks for one supported agent."""

    IDE_CONFIGS = IDE_CONFIGS

    @staticmethod
    def _canonical_agent(agent: str) -> str:
        aliases = {
            "claude-code": "claude",
            "github-copilot": "copilot",
            "github_copilot": "copilot",
            "gemini-cli": "gemini",
            "gemini_cli": "gemini",
            "zoo-code": "zoocode",
            "aider-desk": "aiderdesk",
            "open-claw": "openclaw",
            "augment-code": "augment",
            "open-code": "opencode",
        }
        normalized = agent.strip().casefold()
        return aliases.get(normalized, normalized)

    def get_config_path(
        self,
        agent: str,
        project_dir: str | Path | None = None,
    ) -> Path:
        """Resolve an agent config path for a project or the user profile."""

        canonical = self._canonical_agent(agent)
        if canonical not in self.IDE_CONFIGS:
            raise ValueError(
                f"Unsupported agent '{agent}'. "
                f"Choose one of: {', '.join(SUPPORTED_AGENTS)}"
            )

        config = self.IDE_CONFIGS[canonical]
        raw = (
            config.get("project_config_path")
            if project_dir is not None
            else config.get("config_path")
        )
        path = Path(str(raw)).expanduser()
        if project_dir is not None and not path.is_absolute():
            path = Path(project_dir) / path
        return path

    def _setup_scripts(
        self,
        agent: str,
        config: dict[str, Any],
        path: Path,
        *,
        dry_run: bool,
    ) -> str:
        scripts = config.get("scripts") or {
            event: _script_action(event) for event in config.get("hook_scripts", [])
        }
        commands = {event: _command(agent, action) for event, action in scripts.items()}
        if dry_run:
            files = ", ".join(str(path / event) for event in scripts)
            return f"[DRY RUN] Would configure {config['name']} hooks: {files}"
        for event, command in commands.items():
            _write_script(path / event, command)
        return f"Configured {config['name']} hooks in {path}"

    def _setup_json(
        self,
        agent: str,
        config: dict[str, Any],
        path: Path,
        *,
        dry_run: bool,
    ) -> str:
        if dry_run:
            return f"[DRY RUN] Would configure {config['name']} hooks in {path}"

        data = _load_json(path)
        kind = config.get("kind")
        if kind is None:
            if config.get("script_based"):
                kind = "scripts"
            elif isinstance(config.get("hooks"), list):
                kind = "event_list"
            else:
                kind = "nested"
        if kind == "nested":
            _merge_nested_hooks(
                data,
                config["hooks"],
                post_tool_matcher=config.get("post_tool_matcher", ""),
            )
        elif kind == "top_level":
            if "version" in config:
                data.setdefault("version", config["version"])
            _merge_top_level_hooks(
                data,
                config["hooks"],
                nested_key=config.get("nested_hooks_key"),
            )
        elif kind == "event_list":
            _merge_event_list(data, config["hooks"])
        elif kind == "nested_wrapper":
            _merge_nested_hooks(data, config["hooks"])
        _write_json(path, data)
        return f"Configured {config['name']} hooks in {path}"

    def setup_ide_hooks(
        self,
        agent: str,
        project_dir: str | Path | None = None,
        *,
        dry_run: bool = False,
        force: bool = False,
    ) -> tuple[bool, str]:
        """Configure hooks and preserve existing unrelated settings."""

        del force  # Hook merges are idempotent; existing settings are preserved.
        canonical = self._canonical_agent(agent)
        if canonical not in self.IDE_CONFIGS:
            return False, (
                f"Unsupported agent '{agent}'. "
                f"Choose one of: {', '.join(SUPPORTED_AGENTS)}"
            )

        config = self.IDE_CONFIGS[canonical]
        path = self.get_config_path(canonical, project_dir)
        try:
            kind = config["kind"]
            if kind == "scripts":
                message = self._setup_scripts(canonical, config, path, dry_run=dry_run)
            elif kind == "plugin":
                if dry_run:
                    message = f"[DRY RUN] Would configure {config['name']} at {path}"
                else:
                    _write_plugin(path / "lore.ts", canonical)
                    message = f"Configured {config['name']} plugin in {path}"
            elif kind == "extension":
                if dry_run:
                    message = f"[DRY RUN] Would configure {config['name']} at {path}"
                else:
                    _write_extension(path, canonical)
                    message = f"Configured {config['name']} extension in {path}"
            elif kind == "mcp_only":
                if dry_run:
                    message = f"[DRY RUN] Would add Lore MCP guidance to {path}"
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(
                        "# Lore MCP integration\n\n"
                        "Use the Lore MCP server for shared knowledge recall and "
                        "capture.\n",
                        encoding="utf-8",
                    )
                    message = f"Configured {config['name']} MCP guidance in {path}"
            else:
                message = self._setup_json(canonical, config, path, dry_run=dry_run)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return False, f"Could not configure {config['name']}: {exc}"
        return True, message

    def check_hooks_configured(self, path: Path, agent: str) -> bool:
        """Return whether a path already contains a Lore hook."""

        canonical = self._canonical_agent(agent)
        config = self.IDE_CONFIGS.get(canonical)
        if config is None or not path.exists():
            return False

        kind = config.get("kind")
        if kind == "scripts" or config.get("script_based"):
            scripts = config.get("scripts") or {
                event: _script_action(event) for event in config.get("hook_scripts", [])
            }
            return any(
                (path / event).is_file()
                and "lore hook" in (path / event).read_text(encoding="utf-8")
                for event in scripts
            )
        if kind == "plugin" or config.get("plugin_file"):
            return (path / "lore.ts").is_file()
        if kind == "extension" or config.get("extension_based"):
            return (path / "index.js").is_file()
        if kind == "mcp_only":
            try:
                return "Lore MCP" in path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                return False

        try:
            return "lore hook" in json.dumps(_load_json(path))
        except (OSError, ValueError, json.JSONDecodeError):
            return False

    def merge_hooks(
        self,
        existing_config: dict[str, Any],
        lore_hooks: dict[str, Any],
        agent: str,
    ) -> tuple[dict[str, Any], list[str]]:
        """Merge a hook template and return the config plus warnings.

        The method mirrors the upstream setup API so callers can preview or
        compose a configuration without writing it to disk.
        """

        canonical = self._canonical_agent(agent)
        config = self.IDE_CONFIGS.get(canonical)
        if config is None:
            raise ValueError(f"Unsupported agent '{agent}'")

        data = json.loads(json.dumps(existing_config))
        hooks = lore_hooks.get("hooks", lore_hooks)
        if config.get("kind") == "event_list" or isinstance(hooks, list):
            _merge_event_list(data, hooks)
        elif config.get("kind") == "top_level":
            _merge_top_level_hooks(
                data,
                hooks,
                nested_key=config.get("nested_hooks_key"),
            )
        else:
            _merge_nested_hooks(
                data,
                hooks,
                post_tool_matcher=config.get("post_tool_matcher", ""),
            )
        return data, []


def setup_agent(
    agent: str,
    project_dir: str | Path | None = None,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> tuple[bool, str]:
    """Convenience wrapper for configuring one agent."""

    return IDESetup().setup_ide_hooks(
        agent,
        project_dir=project_dir,
        dry_run=dry_run,
        force=force,
    )


__all__ = [
    "AGENT_CONFIGS",
    "IDE_CONFIGS",
    "SUPPORTED_AGENTS",
    "HookEvent",
    "IDESetup",
    "setup_agent",
]
