# Lore

Shared knowledge MCP server for AI coding agents. Persistent, cross-team memory that survives sessions, spans repositories, and scales from solo developer to enterprise.

## The Problem

Every AI coding session starts from zero. The agent re-reads files, re-derives conclusions, and re-discovers patterns already found in previous sessions. MEMORY.md helps but is per-project, per-user, agent-driven (unreliable capture), and doesn't scale. Cross-project knowledge sharing doesn't exist natively.

The cost is real: cache creation from repeated file reads and re-derivation accounts for ~50% of AI coding spend.

## What Lore Does

Lore is a local MCP server backed by git repos (shared knowledge) and SQLite (individual + cache). A cheap LLM handles retrieval and capture — the expensive main model never touches Lore operations.

```
without lore                          with lore
────────────────────────────────      ────────────────────────────────
session starts                        session starts
→ read auth code       (tokens)       → query_knowledge("auth")  (1 MCP call)
→ read related files   (tokens)       → phi4-mini searches DB    (free/near-free)
→ main model reasons   ($$$ tokens)   → main model gets answer   (no re-derivation)
→ same conclusion as last session
→ repeat next session
```

### Key Features

- **Git-backed shared knowledge** — levels 1-N of git repos (single repo with branches, or separate repos). PR-based review using familiar workflows. Branch rulesets or CODEOWNERS for access control.
- **Local-first** — each developer runs their own MCP server with local SQLite. Git repos are the source of truth. No infrastructure to deploy.
- **Project-scoped config** — each project's `.lore/config.json` defines its hierarchy (committed to repo, shared with team). Global config registers projects + provider settings.
- **Bidirectional** — agents both store and retrieve knowledge. Session-end hook captures discoveries via cheap LLM. Level 0 (individual) writes immediately; shared levels go through PR review.
- **Numbered levels** — level 0 = individual (implicit, highest priority), levels 1-N = shared (admin-defined). Lower level = higher priority = wins in conflicts. No org/product/team assumptions — any structure fits.
- **Locked entries** — any level's maintainers can mark entries as immutable via frontmatter (`lock: true`). Lower levels cannot override.
- **Conflict tracking** — when non-locked entries conflict across levels, both are stored with bidirectional links. Lower level wins (more specific). Conflicts are queryable and reportable.
- **Hybrid search** — FTS5 (implemented), with vector + BM25 + reciprocal rank fusion + LLM synthesis planned for Phase 2.
- **Anti-poisoning** — shared writes require PR approval. Individual writes are immediate (your knowledge, your risk). No hallucination propagation to team store.
- **Token cost reduction** — replaces N file reads + reasoning with 1 MCP call returning a short synthesis. Fewer tokens in context = less cache churn = lower cost.
- **13-agent hooks** — Claude Code, Cursor, Copilot, Codex, Windsurf, Gemini CLI, Cline, Kiro, Augment, OpenCode, AiderDesk, OpenClaw, Junie. Hook adapter architecture adapted from [ai-guardian](https://github.com/itdove/ai-guardian).
- **Ingester framework** — auto-capture from ReasonsForge, OpenWolf, Debuggernaut, sdlc-mcp, Jira, git at session end. Lore is a knowledge aggregator, not just a store.

### Architecture

```
GIT REPOS (levels 1-N)                      LOCAL (per developer)
──────────────────────                      ────────────────────

level N repo@branch ──── PR ────┐
level 2 repo@branch ──── PR ────┤           FastMCP Server (stdio)
level 1 repo@branch ──── PR ────┤           ├── SQLite DB (all projects)
                                │           ├── LLM (Ollama local or remote)
level 0 (individual) ───────────┘           └── periodic git pull + reindex
(local only, highest priority)

Project A/.lore/config.json → hierarchy for project A
Project B/.lore/config.json → hierarchy for project B (can differ)
~/.config/lore/config.json  → project registry + provider settings
```

### Knowledge Lifecycle

```
SESSION START  → query_knowledge(topic) → cheap LLM synthesizes → agent acts
MID-SESSION    → PostToolUse nudge → agent stores (user chooses level)
SESSION END    → cheap LLM extracts candidates from transcript
               → individual entries → local SQLite (immediate)
               → shared entries → auto-PR to appropriate repo
               → stale entries detected → negate with reason
               → PR merged → individual entry with same key auto-cleaned
```

## Getting Started

```bash
# Clone and install
git clone https://github.com/itdove/lore.git
cd lore
pip install -e ".[dev]"

# Initialize lore in your project
cd /path/to/your/project
lore init
```

`lore init` walks you through setup:
1. Creates XDG directories and global config
2. Prompts for shared hierarchy levels (repo URLs + branches), or reuse an existing project's hierarchy
3. Creates `.lore/config.json` in your project
4. Sets up the SQLite database
5. Registers the MCP server in `~/.claude.json`
6. Runs the first sync

### CLI Commands

```bash
# Initialize lore in current project directory
lore init

# Sync all knowledge repos across registered projects
lore sync
lore sync --verbose

# Search knowledge scoped to current project's hierarchy
lore search "authentication patterns"

# Show conflict report
lore conflicts

# View and edit configuration
lore config show              # Merged config (global + project)
lore config show --global     # Global config only
lore config show --project    # Project config only
lore config set <key> <value> # Set value using dot notation
lore config set --global <key> <value>  # Set in global config
lore config edit              # Open project config in $EDITOR
lore config edit --global     # Open global config in $EDITOR

# Start MCP server (used by AI agents, not run directly)
lore mcp-server
```

### MCP Tools

Once the MCP server is registered, AI agents have access to:

| Tool | Description |
|------|-------------|
| `query_knowledge` | FTS5 search with priority resolution across hierarchy levels |
| `list_knowledge` | List entries with optional tag/level filters and history |
| `list_conflicts` | Show all conflicting entries with both sides linked |
| `health_check` | Entry counts per level, conflict count, staleness info |

### Running Tests

```bash
python -m pytest tests/ -v
```

## Status

**MVP Sprint 1 complete.** Core functionality implemented:

- Config loading with XDG paths and project hierarchy ([#2](https://github.com/itdove/lore/issues/2))
- SQLite schema with FTS5 full-text search ([#3](https://github.com/itdove/lore/issues/3))
- FastMCP server with bundled LORE.md instructions ([#4](https://github.com/itdove/lore/issues/4))
- MCP tool handlers: query, list, conflicts, health ([#5](https://github.com/itdove/lore/issues/5))
- Git repo sync engine: clone/pull, parse markdown frontmatter, index to SQLite ([#6](https://github.com/itdove/lore/issues/6))
- CLI: `lore init`, `lore sync`, `lore search`, `lore conflicts`, `lore mcp-server` ([#7](https://github.com/itdove/lore/issues/7))
- Config CLI: `lore config show`, `lore config set`, `lore config edit` ([#29](https://github.com/itdove/lore/issues/29))
- CI/CD with pytest, black, ruff ([#22](https://github.com/itdove/lore/issues/22))

See [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) for the phased roadmap.

## Landscape

Lore is complementary to existing tools, not competing:

| Tool | Solves | Scope |
|------|--------|-------|
| sdlc-mcp | Static process docs → agents | Per-project |
| OpenWolf | Token waste reduction (middleware) | Per-project |
| ReasonsForge | Deep codebase analysis + reasoning | Per-codebase |
| OpenClaw Memory | Single-user session memory | Per-workspace |
| HiveShare | Team shared memory (closest competitor) | Per-hiveshare (flat) |
| **Lore** | **Cross-team knowledge sharing + aggregation** | **N-level hierarchy** |

## License

Apache License 2.0 — see [LICENSE](LICENSE)
