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
- **Hybrid search** — FTS5 + vector cosine distance + reciprocal rank fusion + LLM synthesis. sqlite-vec for SQL-level distance when available, pure-Python fallback otherwise.
- **Anti-poisoning** — shared writes require PR approval. Individual writes are immediate (your knowledge, your risk). No hallucination propagation to team store.
- **Token cost reduction** — replaces N file reads + reasoning with 1 MCP call returning a short synthesis. Fewer tokens in context = less cache churn = lower cost.
- **Auto-sync** — hook-triggered sync on session start, with staleness detection and configurable thresholds.
- **Web dashboard** — NiceGUI-based browser UI for browsing entries, managing individual knowledge, resolving conflicts, and monitoring sync status.

### Architecture

```
GIT REPOS (levels 1-N)                      LOCAL (per developer)
──────────────────────                      ────────────────────

level N repo@branch ──── PR ────┐
level 2 repo@branch ──── PR ────┤           FastMCP Server (stdio)
level 1 repo@branch ──── PR ────┤           ├── SQLite DB (all projects)
                                │           ├── LLM (Ollama local or remote)
level 0 (individual) ───────────┘           └── auto-sync via hook + staleness
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
5. Registers the MCP server (`.mcp.json` + `.claude/settings.json`)
6. Runs the first sync

### CLI Commands

```bash
# Initialize lore in current project directory
lore init

# Sync all knowledge repos across registered projects
lore sync
lore sync --verbose
lore sync --force              # Sync even if fresh
lore sync --status             # Show sync status without syncing

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

# Claude Code hook handlers
lore hook recall               # Recall context (UserPromptSubmit)
lore hook nudge                # Mid-session nudge (PostToolUse)
lore hook capture              # Capture knowledge (SessionEnd)

# Launch web dashboard
lore dashboard
lore dashboard --port 8765 --host 127.0.0.1

# Start MCP server (used by AI agents, not run directly)
lore mcp-server
```

### MCP Tools

Once the MCP server is registered, AI agents have access to:

| Tool | Description |
|------|-------------|
| `query_knowledge` | Hybrid search (FTS5 + vector + RRF) with priority resolution and LLM synthesis |
| `list_knowledge` | List entries with optional tag/level filters and history |
| `list_conflicts` | Show all conflicting entries with both sides linked |
| `health_check` | Entry counts per level, conflict count, staleness, sqlite-vec status |
| `store_knowledge` | Store or update a knowledge entry (individual or shared via PR) |
| `negate_knowledge` | Mark an entry as incorrect/outdated with reason |
| `delete_knowledge` | Delete an individual entry (shared entries rejected with PR message) |

### Vector Search Performance

Lore uses [sqlite-vec](https://github.com/asg017/sqlite-vec) for SQL-level cosine distance when available. If the Python build lacks SQLite extension loading support, Lore falls back to a pure-Python implementation automatically.

**macOS (pyenv):** The default build links against macOS system SQLite, which omits `load_extension`. Rebuild Python to enable sqlite-vec:

```bash
brew install sqlite
LDFLAGS="-L$(brew --prefix sqlite)/lib" \
CPPFLAGS="-I$(brew --prefix sqlite)/include" \
PYTHON_CONFIGURE_OPTS="--enable-loadable-sqlite-extensions" \
pyenv install 3.12 --force
```

**macOS (uv):** uv uses python-build-standalone binaries which also lack extension loading. Use uv with a pyenv-built Python instead:

```bash
brew install sqlite
LDFLAGS="-L$(brew --prefix sqlite)/lib" \
CPPFLAGS="-I$(brew --prefix sqlite)/include" \
PYTHON_CONFIGURE_OPTS="--enable-loadable-sqlite-extensions" \
pyenv install 3.12
uv venv --python $(pyenv prefix 3.12)/bin/python
```

**Linux:** Most distributions ship Python with extension loading enabled — no extra steps needed.

### Running Tests

```bash
python -m pytest tests/ -v
```

## Status

**MVP + Phase 2 complete.** All core functionality and hybrid search implemented:

**MVP Sprint 1 — Core:**
- Config loading with XDG paths and project hierarchy ([#2](https://github.com/itdove/lore/issues/2))
- SQLite schema with FTS5 full-text search ([#3](https://github.com/itdove/lore/issues/3))
- FastMCP server with bundled LORE.md instructions ([#4](https://github.com/itdove/lore/issues/4))
- MCP tool handlers: query, list, conflicts, health ([#5](https://github.com/itdove/lore/issues/5))
- Git repo sync engine: clone/pull, parse markdown frontmatter, index to SQLite ([#6](https://github.com/itdove/lore/issues/6))
- CLI: init, sync, search, conflicts, mcp-server ([#7](https://github.com/itdove/lore/issues/7))
- Config CLI: show, set, edit ([#29](https://github.com/itdove/lore/issues/29))
- CI/CD with pytest, black, ruff ([#22](https://github.com/itdove/lore/issues/22))

**MVP Sprint 2 — Write Path:**
- Write-path MCP tools: store, negate, delete ([#8](https://github.com/itdove/lore/issues/8))
- LLM provider ABC + Ollama: synthesis + capture ([#10](https://github.com/itdove/lore/issues/10))
- GitInterface ABC + GitHub PR creation ([#11](https://github.com/itdove/lore/issues/11))
- Conflict detection + tracking at sync time ([#12](https://github.com/itdove/lore/issues/12))
- NiceGUI dashboard: browser, CRUD, conflicts, sync ([#13](https://github.com/itdove/lore/issues/13))
- Auto-sync: scheduled and hook-triggered ([#40](https://github.com/itdove/lore/issues/40))

**Phase 2 — Hybrid Search:**
- Embedding provider ABC + Ollama + sqlite-vec + RRF ([#14](https://github.com/itdove/lore/issues/14))

See [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) for the full roadmap.

## Landscape

Lore is complementary to existing tools, not competing:

| Tool | Solves | Scope |
|------|--------|-------|
| sdlc-mcp | Static process docs → agents | Per-project |
| OpenWolf | Token waste reduction (middleware) | Per-project |
| ReasonsForge | Deep codebase analysis + reasoning | Per-codebase |
| OpenClaw Memory | Single-user session memory | Per-workspace |
| HiveShare | Team shared memory (closest competitor) | Per-hiveshare (flat) |
| MemoryHub | Structured memory with tags | Per-user (flat) |
| **Lore** | **Cross-team knowledge sharing + aggregation** | **N-level hierarchy** |

## License

Apache License 2.0 — see [LICENSE](LICENSE)
