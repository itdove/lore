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

- **Git-backed shared knowledge** — N-level hierarchy of git repos (admin-defined: org, product, team, or any structure). PR-based review using familiar workflows. CODEOWNERS = locked entries.
- **Local-first** — each developer runs their own MCP server with local SQLite. Git repos are the source of truth. No infrastructure to deploy.
- **Bidirectional** — agents both store and retrieve knowledge. Session-end hook captures discoveries via cheap LLM. Individual knowledge writes immediately; shared knowledge goes through PR review.
- **N-level hierarchy** — admin defines levels, names, and repos. Default template: Org/Product/Team/Individual. Solo developer to large enterprise — same codebase.
- **Locked entries** — any level's maintainers can mark entries as immutable via frontmatter (`lock: true`). Lower levels cannot override. Compliance, security standards, architectural constraints stay enforced.
- **Conflict tracking** — when non-locked entries conflict across levels, both are stored with bidirectional links. Lower hierarchy wins (more specific). Conflicts are queryable and reportable.
- **Hybrid search** — FTS5 (MVP), with vector + BM25 + reciprocal rank fusion + LLM synthesis in Phase 2.
- **Anti-poisoning** — shared writes require PR approval. Individual writes are immediate (your knowledge, your risk). No hallucination propagation to team store.
- **Token cost reduction** — replaces N file reads + reasoning with 1 MCP call returning a short synthesis. Fewer tokens in context = less cache churn = lower cost.
- **13-agent hooks** — Claude Code, Cursor, Copilot, Codex, Windsurf, Gemini CLI, Cline, Kiro, Augment, OpenCode, AiderDesk, OpenClaw, Junie. Hook adapter architecture adapted from [ai-guardian](https://github.com/itdove/ai-guardian).
- **Ingester framework** — auto-capture from ReasonsForge, OpenWolf, Debuggernaut, sdlc-mcp, Jira, git at session end. Lore is a knowledge aggregator, not just a store.

### Architecture

```
GIT REPOS (N levels, admin-defined)         LOCAL (per developer)
───────────────────────────────────         ────────────────────

level-1 repo (e.g. org)  ←── PR ───┐
level-2 repo (e.g. product) PR ────┤      FastMCP Server (stdio)
level-N repo (e.g. team) ←── PR ───┤      ├── SQLite DB (cache + individual)
                                    │      ├── LLM (Ollama local or remote)
individual knowledge ───────────────┘      └── periodic git pull + reindex
(local only, always last)
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
