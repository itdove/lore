# Lore

Shared knowledge MCP server for AI coding agents. Persistent, cross-team memory that survives sessions, spans repositories, and scales from solo developer to enterprise.

## The Problem

Every AI coding session starts from zero. The agent re-reads files, re-derives conclusions, and re-discovers patterns already found in previous sessions. MEMORY.md helps but is per-project, per-user, agent-driven (unreliable capture), and doesn't scale. Cross-project knowledge sharing doesn't exist natively.

The cost is real: cache creation from repeated file reads and re-derivation accounts for ~50% of AI coding spend.

## What Lore Will Do

> **Status: design phase — not yet implemented.** See [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) for the phased roadmap.

Lore will be a local MCP server backed by git repos (shared knowledge) and SQLite (individual + cache). A cheap LLM handles retrieval and capture — the expensive main model never touches Lore operations.

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
- **Hybrid search** — FTS5 (MVP), with vector + BM25 + reciprocal rank fusion + LLM synthesis in Phase 2.
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

## Status

Design phase. See [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) for the phased roadmap and [LORE_INITIATIVE.md](LORE_INITIATIVE.md) for the full initiative proposal including market comparison.

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
