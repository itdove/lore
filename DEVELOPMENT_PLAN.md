# Lore — Development Plan

Incremental delivery. Each phase is independently usable. MVP is fully functional, not a throwaway — enterprise features layer on top without replacing anything.

**Core principle:** git repos are the source of truth for shared knowledge. Local SQLite is a cache + individual store. ABCs enable enterprise upgrades without refactoring.

---

## Architecture Overview

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

**N-level hierarchy:** admin defines their own structure. Number of levels, level names, and repos are fully configurable. Individual is always the last level (highest priority, local only).

**XDG paths:**

| Purpose | Path | Default |
|---------|------|---------|
| Config | `$XDG_CONFIG_HOME/lore/config.json` | `~/.config/lore/config.json` |
| Database | `$XDG_DATA_HOME/lore/knowledge.db` | `~/.local/share/lore/knowledge.db` |
| Cache | `$XDG_CACHE_HOME/lore/` | `~/.cache/lore/` (repo clones, embeddings) |
| State | `$XDG_STATE_HOME/lore/` | `~/.local/state/lore/` (sync logs, conflict reports) |
| Project | `.lore/config.json` | Project-level override |

**DB schema:**

```
knowledge
├── id               TEXT PRIMARY KEY
├── key              TEXT              -- type:domain:slug (derived from file path)
├── value            TEXT              -- knowledge content
├── tags             TEXT              -- comma-separated
├── level            TEXT              -- admin-defined level name (e.g. "org", "product", "team", "individual")
├── priority         INTEGER           -- derived from hierarchy position (lower = broader scope)
├── locked           BOOLEAN DEFAULT FALSE
├── conflict_with    TEXT NULL         -- references knowledge.id of conflicting entry
├── conflict_status  TEXT NULL         -- "active" (wins) | "overridden" (excluded)
├── ingested_from    TEXT NULL         -- "git", "reasonsforge", "openwolf", etc.
├── provenance       TEXT NULL         -- commit_sha, pr_url, source-specific metadata
├── times_seen       INTEGER DEFAULT 1 -- reinforcement counter (dedup increments)
├── embedding        BLOB NULL         -- float array, computed async (Phase 2)
├── created_at       TIMESTAMP
└── updated_at       TIMESTAMP

knowledge_history
├── id               TEXT PRIMARY KEY
├── knowledge_id     TEXT              -- references knowledge.id
├── action           TEXT              -- "created" | "updated" | "negated" | "deleted" | "synced_out"
├── previous_value   TEXT
├── actor            TEXT              -- user/agent identifier
├── reason           TEXT
└── timestamp        TIMESTAMP
```

**Config — N-level hierarchy:**

Two repo strategies supported: **single repo with branches** (simpler) or **separate repos** (stronger access control). `branch` field defaults to `main` when omitted.

**Single repo + branches (default template — simpler for onboarding):**

```json
{
  "lore": {
    "hierarchy": [
      {"level": "org", "priority": 1, "repo": "github.com/org/knowledge", "branch": "org"},
      {"level": "product", "priority": 2, "repo": "github.com/org/knowledge", "branch": "product"},
      {"level": "team", "priority": 3, "repo": "github.com/org/knowledge", "branch": "team"}
    ],
    "individual": {"priority": 100},
    "sync_interval": "30m",
    "store": {"type": "sqlite"},
    "llm": {"provider": "ollama", "model": "phi4-mini"},
    "git": {"provider": "github"}
  }
}
```

PR auth via GitHub branch rulesets — different required reviewers per branch.

**Separate repos (enterprise template — stronger access control):**

```json
{
  "lore": {
    "hierarchy": [
      {"level": "org", "priority": 1, "repo": "github.com/org/org-knowledge"},
      {"level": "product", "priority": 2, "repo": "github.com/org/product-myproduct-knowledge"},
      {"level": "team", "priority": 3, "repo": "github.com/org/team-myteam-knowledge"}
    ],
    "individual": {"priority": 100},
    "sync_interval": "30m",
    "store": {"type": "sqlite"},
    "llm": {"provider": "ollama", "model": "phi4-mini"},
    "git": {"provider": "github"}
  }
}
```

PR auth via CODEOWNERS + repo permissions. Read access restricted per repo.

**More examples:**

```
# Solo developer:
"hierarchy": []

# Flat (small company, single repo):
"hierarchy": [
  {"level": "company", "priority": 1, "repo": "github.com/co/knowledge", "branch": "main"}
]

# Deep enterprise (separate repos):
"hierarchy": [
  {"level": "org", "priority": 1, "repo": "..."},
  {"level": "division", "priority": 2, "repo": "..."},
  {"level": "product", "priority": 3, "repo": "..."},
  {"level": "team", "priority": 4, "repo": "..."}
]

# Multiple repos per level:
"hierarchy": [
  {"level": "org", "priority": 1, "repo": "..."},
  {"level": "team", "priority": 2, "repo": "github.com/org/team-alpha-knowledge"},
  {"level": "team", "priority": 2, "repo": "github.com/org/team-beta-knowledge"}
]
```

**Core data model — level-agnostic:**

```python
@dataclass
class HierarchyLevel:
    level: str          # admin-defined name (free text)
    priority: int       # lower = broader scope
    repo: str           # git repo URL
    branch: str = "main"  # branch within repo (enables single-repo-with-branches pattern)

class Config:
    hierarchy: list[HierarchyLevel]   # N levels, admin-defined
    individual_priority: int = 100     # always last
```

Code never references "org" or "product" by name — everything is `level: str` + `priority: int`. Sync engine pulls `repo@branch` regardless of strategy. Conflict resolution and lock behavior use priority values only.

**Knowledge repo structure — directory path = key:**

```
org-knowledge/
├── convention/
│   └── naming/
│       └── snake-case-columns.md    → key = convention:naming:snake-case-columns
├── security/
│   └── api/
│       └── auth-required.md         → key = security:api:auth-required  (lock: true)
└── lore.yml
```

**File frontmatter:**

```yaml
---
lock: true
tags: [security, api, compliance]
created_by: jdoe
---
All API endpoints must have auth middleware — no exceptions.
Why: compliance requirement from security audit Q2 2026.
```

---

## Phase 1 — MVP: Git-Backed Shared Knowledge

**Goal:** working shared knowledge store from day one. Git repos for shared knowledge, local SQLite for individual + cache, local LLM for synthesis + capture, PR-based review.

**Scope:**

*MCP server:*
- FastMCP server with bundled `LORE.md` injected via `instructions=`
- Local SQLite with FTS5 (`$XDG_DATA_HOME/lore/knowledge.db`)
- Config at `$XDG_CONFIG_HOME/lore/config.json` with project override at `.lore/config.json`

*Git knowledge repos:*
- N-level hierarchy of git repos, admin-defined (default: org/product/team)
- Directory structure = key format: `<type>/<domain>/<slug>.md` → `type:domain:slug`
- Frontmatter: `lock`, `tags`, `created_by`
- CODEOWNERS = locked entry enforcement (repo maintainers per level)
- `lore sync` pulls all configured repos, indexes into local SQLite
- File removed from repo → entry removed from DB (repo is authoritative)
- File added/changed → DB updated with provenance (commit_sha, file_path)
- Periodic sync via configurable interval (default 30m)

*Conflict tracking:*
- Locked entry in higher repo → always wins, conflicting lower entry rejected at sync
- Non-locked conflict → lower hierarchy wins (more specific)
- Both entries stored in DB: winner gets `conflict_status=active`, loser gets `conflict_status=overridden`
- `conflict_with` links both entries bidirectionally
- Only entries with `conflict_with IS NULL OR conflict_status = 'active'` returned in queries
- Conflict report: `lore conflicts` CLI or `WHERE conflict_with IS NOT NULL` in UI

*Two-LLM architecture:*
- Cheap LLM (Ollama phi4-mini / Haiku) handles retrieval synthesis + knowledge capture
- Main model (Opus/Sonnet) never involved in Lore operations
- Config: `llm.provider` + `llm.model` — same config for synthesis and capture
- `provider: "none"` disables LLM — raw FTS results returned

*Knowledge lifecycle hooks (Claude Code):*
- `UserPromptSubmit` → **recall**: query Lore for relevant context
- `PostToolUse` → **mid-session capture**: MCP instructions ask user which level to store
- `Stop` → **session-end capture + correction**:
  - Export session transcript
  - Cheap LLM extracts knowledge candidates
  - Cheap LLM deduplicates against existing entries (cosine/keyword similarity)
  - Individual entries → stored to local SQLite immediately
  - Shared entries → cheap LLM determines appropriate level → auto-PR created
  - Cheap LLM detects stale entries → negate with reason
- `lore setup --ide claude` registers hooks in settings

*PR-based review:*
- Session-end capture creates PRs in appropriate knowledge repo
- Product owner / team lead reviews via normal git diff
- Merge triggers next `lore sync` to pick up changes
- PR rejected → individual entry stays in local SQLite (still useful personally)
- PR merged → on next sync, individual entry with same key removed (promoted to shared)

*Individual knowledge:*
- Stored in local SQLite only, no git repo needed
- Immediate writes, no review
- CRUD via MCP tools or NiceGUI dashboard
- When promoted (PR merged at higher level with same key) → individual entry auto-cleaned

*Git interface:*
- `GitInterface` ABC with GitHub implementation (MVP)
- Methods: `create_pr(repo, branch, files, title, body)`, `list_repos()`, `pull(repo)`, `get_pr_status(pr_url)`
- GitLab / Bitbucket implementations added later

*MCP tools:*
- `store_knowledge(key, value, tags, level?)` — individual=immediate, shared=auto-PR to configured repo for that level
- `query_knowledge(topic, scope?)` — FTS + optional LLM synthesis, priority-aware, excludes overridden conflicts
- `list_knowledge(tag?, level?, include_history?)` — filterable by level/tag, optionally with change history
- `negate_knowledge(key, reason)` — contradict stale entry with explanation
- `delete_knowledge(key)` — permanently remove (individual only; shared = PR to remove file)
- `health_check()` — staleness detection, conflict count, sync status
- `list_conflicts()` — all entries with `conflict_with IS NOT NULL`

*CLI:*
- `lore init` — creates config, schema, registers MCP, detects git remote
- `lore sync` — pull all repos, reindex SQLite, detect conflicts, clean promoted entries
- `lore search <topic>` — FTS query from command line
- `lore conflicts` — show conflict report
- `lore ui` — launch NiceGUI dashboard

*NiceGUI dashboard:*
- Local web UI on `localhost:8765`
- Knowledge browser: all entries, filterable by level/type/domain/tags
- Individual CRUD: create, edit, delete, promote (creates PR)
- Shared entries: read-only (edit requires PR)
- Conflict viewer: both sides linked, acknowledge or escalate
- Sync status: last sync per repo, entries added/removed/updated
- Stats: entry count per scope, staleness, coverage

**Deliverable:** developer installs `pip install lore-mcp`, runs `lore init`, configures repos, runs `lore sync`. Claude Code sessions recall shared knowledge, capture discoveries, create PRs for team review. Individual knowledge persists locally across sessions. Conflicts tracked and reportable. All at near-zero cost (local LLM).

---

## Phase 2 — Hybrid Search + Embeddings

**Goal:** replace FTS-only with hybrid retrieval. Semantic queries find knowledge without exact keyword match.

**Adds:**
- `EmbeddingProvider` ABC: `embed(text) -> list[float]`
- Providers: `ollama` (`nomic-embed-text`), `openai` (`text-embedding-3-small`), `vertex` (`text-embedding-005`), `none` (FTS fallback)
- `embedding` column on knowledge table (nullable, stored as float array)
- `sqlite-vec` extension for vector search
- Embeddings computed async on write/sync — FTS works immediately, vector search improves as embeddings complete
- Retrieval pipeline: vector similarity + FTS5/BM25 → reciprocal rank fusion (RRF) → top-N → LLM synthesis
- Dedup on ingest uses cosine distance — below threshold → reinforce existing entry (`times_seen++`)
- Config: `search.embedding_provider`, `search.embedding_model`
- `lore migrate phase2` backfills embeddings for existing entries

**Migration 1→2:** adds nullable `embedding` column. Backfill async. No downtime — FTS fallback until embeddings ready.

**Deliverable:** "auth issues" finds "JWT token expiry." Semantic dedup catches near-duplicate entries across sessions.

---

## Phase 3 — Multi-Agent Hooks

**Goal:** hook-driven protocol enforcement for all agents, not just Claude Code.

**Adds:**
- Hook adapter architecture (mirrors ai-guardian's `hook_adapters/`)
- Adapters: Cursor, GitHub Copilot, OpenAI Codex, Windsurf, Gemini CLI, Cline/ZooCode, Kiro, Augment Code, OpenCode, AiderDesk, OpenClaw, Junie (MCP only)
- Hook event name normalization across agents
- `lore setup --ide <agent>` for all supported agents
- Config file locations per agent (matches ai-guardian locations)

**Deliverable:** any supported agent gets the same recall/capture/correction lifecycle. Not just Claude Code.

---

## Phase 4 — Ingester Framework

**Goal:** auto-ingest knowledge from external sources at session end and on schedule.

**Adds:**
- `LoreIngester` ABC: `detect()`, `extract_delta()`, `transform()`, `load()`
- Session-end hook extended: auto-detect local sources, ingest deltas
- Adapters ship independently:

| Source | Adapter | Trigger | Review | Detect |
|--------|---------|---------|--------|--------|
| ReasonsForge | `ReasonsDBIngester` | hook + manual | Immediate (pre-verified) | `reasons.db` exists |
| OpenWolf | `OpenWolfIngester` | hook | PR-based | `.wolf/` exists |
| OpenClaw | `OpenClawIngester` | hook | Immediate (personal) | `MEMORY.md` exists |
| Custom workflow | `CustomIngester` | scheduled | Immediate | Backend configured |
| sdlc-mcp | `SdlcMcpIngester` | scheduled + manual | Immediate | MCP config found |
| context-server | `ContextServerIngester` | scheduled + manual | Immediate | DB path configured |
| Jira | `JiraIngester` | scheduled | PR-based | Jira project configured |

- `lore ingest --source <name>` CLI for manual imports
- Provenance tracking: `ingested_from` + source-specific metadata

**Deliverable:** session-end hook auto-captures from local tools. Scheduled ingestion from remote sources. One knowledge aggregator.

---

## Phase 5 — Enterprise: Centralized DB

**Goal:** optional centralized backend for teams that need real-time sharing without git sync delay.

**Adds:**
- `StoreBackend` ABC: `store()`, `query()`, `health()`
- Turso (libSQL) backend — SQLite-compatible, FTS5 preserved
- Supabase (Postgres + RLS) backend — row-level security at DB level
- AlloyDB / Cloud SQL with pgvector (Google Cloud managed)
- Local SQLite stays as offline fallback
- `lore init` backend selector
- Data migration: `lore migrate --to turso|supabase`

**Deliverable:** teams choose centralized DB when git sync latency isn't acceptable. Local SQLite remains for offline/solo use.

---

## Phase 6 — Enterprise: Auth + ACL

**Goal:** plug into corporate identity systems. Control who reads/writes what.

**Adds:**
- HTTP transport for MCP server (alongside stdio)
- OIDC auth provider (JWT validation on every MCP call)
- Group → role mapping: IdP groups → Lore roles (user, product_owner, org_admin)
- Tested IdPs: Azure AD / Entra ID, Okta, Keycloak, Google Workspace
- Postgres RLS policies for Supabase backend (enforced at DB level)
- `auth.provider` config: `oidc` / `supabase` / `none`

**Deliverable:** enterprises use existing identity infrastructure. AD groups map to Lore roles. DB-level access control.

---

## Phase 7 — Enterprise: Hosted Dashboard

**Goal:** shared NiceGUI dashboard with SSO for team-wide visibility.

**Adds:**
- NiceGUI served on hosted infrastructure (not just localhost)
- SSO integration (same OIDC provider as Phase 6)
- Team-wide views: all entries across members, conflict reports, sync status
- Admin panel: manage repos, scopes, locked entries
- Webhook-driven sync (instant, replaces polling)

**Deliverable:** product owners and org admins get visibility and control without CLI.

---

## Phase Summary

| Phase | Value | Storage | Auth | Agents |
|-------|-------|---------|------|--------|
| **1 — MVP** | Git-backed shared knowledge, local SQLite, PR review, NiceGUI | SQLite + git repos | Git permissions | Claude Code (hooks) |
| **2 — Hybrid search** | Semantic retrieval + embeddings | + sqlite-vec | Same | Same |
| **3 — Multi-agent** | Hook adapters for 13 agents | Same | Same | All agents |
| **4 — Ingesters** | Auto-capture from external tools | Same | Same | Same |
| **5 — Centralized DB** | Optional Turso/Supabase/AlloyDB | + remote DB | Same | Same |
| **6 — Auth + ACL** | OIDC, RLS, HTTP transport | Same | + OIDC/RLS | Same |
| **7 — Hosted dashboard** | Team-wide NiceGUI + SSO + webhooks | Same | + SSO | Same |

---

## ABCs — Enterprise Migration Path

Every enterprise feature is a new implementation of an existing ABC. No refactoring of core logic.

```python
class StoreBackend(ABC):      # SQLite (Phase 1) → + Turso/Supabase (Phase 5)
class LLMProvider(ABC):       # Ollama (Phase 1) → + Anthropic/Vertex AI
class EmbeddingProvider(ABC): # none (Phase 1) → + Ollama/OpenAI/Vertex AI (Phase 2)
class GitInterface(ABC):      # GitHub (Phase 1) → + GitLab/Bitbucket
```

---

## Migrations

| Transition | Migration | Type | Effort |
|------------|-----------|------|--------|
| 1→2 | **Required** | Schema: add nullable `embedding` column + backfill async | Medium |
| 2→3 | None | Hook adapters are config/code only | — |
| 3→4 | None | Ingester framework is new code only | — |
| 4→5 | Optional | Data: SQLite → Turso/Supabase if changing backend | Medium |
| 5→6 | Minor | Config: add auth provider settings | Low |
| 6→7 | None | Deployment: host NiceGUI, add SSO middleware | — |

**Design principle:** all schema changes are additive and nullable. Teams upgrade incrementally without breaking existing data. MVP data is never thrown away.

---

## Hierarchy Migration Tool

When an admin restructures their hierarchy (adding/removing/renaming levels), a migration tool handles the transition:

```
lore migrate-hierarchy --from old-config.json --to new-config.json --dry-run

→ Scanning knowledge DB...
→ Found 247 entries
→ Level mapping:
    "project" (old) → "team" (new): 182 entries
    "product" (old) → "product" (new): 45 entries (unchanged)
    "org" (old) → "org" (new): 20 entries (unchanged)
→ Unmapped: 0 entries
→ Dry run complete. Run without --dry-run to apply.
```

Migration moves files between repos + updates DB entries. Interactive mapping when level names don't match 1:1.

---

## Reusable Patterns from ai-guardian

[ai-guardian](https://github.com/itdove/ai-guardian) provides battle-tested patterns for ~60% of Lore's codebase. The remaining ~40% is new (store, git, llm, sync, capture).

### What to Copy/Adapt

| Pattern | ai-guardian source | Lore usage |
|---------|-------------------|------------|
| FastMCP server | `mcp/server.py:44-147` — `create_server()` + `@server.tool()` | Same decorator pattern, swap tool functions |
| Skill instructions | `skills/ai-guardian-security/SKILL.md` loaded via `instructions=` | `.lore/LORE.md` loaded same way |
| Hook adapter ABC | `hook_adapters/base.py:40-101` — `HookAdapter` + `NormalizedHookInput` + `can_handle()` | Same ABC for all agents |
| Hook registration | `setup/hooks.py:23-96` — `IDESetup` + `HookEvent` enum + `IDE_CONFIGS` dict | `lore setup --ide <agent>` |
| Config XDG loading | `config/loaders.py` — mtime cache, overlay, deep merge | Rename env vars `AI_GUARDIAN_*` → `LORE_*` |
| Config manager | `config/manager.py` — installation/user/project resolution chain | Same chain |
| CLI structure | `cli.py:189-300` — argparse subcommands, function handlers, int exit codes | Same pattern, no Click/Typer |
| NiceGUI dashboard | `web/app.py:48-100` — localhost-only, auto port, Python-only pages | Same wrapper, different pages |
| NiceGUI pages | `web/pages/` — 60+ page modules, one per feature | Pattern for browser/CRUD/conflicts/sync pages |
| Daemon architecture | `daemon/server.py` — Unix socket + REST, idle timeout, observer pattern | Optional for Lore background sync |
| Packaging | `pyproject.toml` — hatchling, conditional deps, `__main__:main` entry point | Same build system |
| Test isolation | `conftest.py:14-51` — autouse fixture, env var isolation, cache clearing | Same pattern, rename env vars |
| ABC + registry | `hook_adapters/__init__.py` — `can_handle()` dispatch, no factory needed | `StoreBackend`, `GitInterface`, `LLMProvider`, `EmbeddingProvider` |

### Key ai-guardian Patterns to Follow

**FastMCP tool registration** (`mcp/server.py`):
```python
server = FastMCP("lore", instructions=_load_lore_instructions())

@server.tool()
def query_knowledge(topic: str, level: str = None) -> dict:
    ...
```

**Hook adapter ABC** (`hook_adapters/base.py`):
```python
class HookAdapter(ABC):
    @abstractmethod
    def can_handle(self, data: dict) -> bool: ...
    @abstractmethod
    def normalize(self, data: dict) -> NormalizedHookInput: ...
```

**Config loading** (`config/loaders.py`):
- Mtime-based cache key: `project_dir + global_mtime + project_mtime`
- Env var overlay: `LORE_CONFIG_INLINE` for programmatic config
- Deep merge with tightening rules
- `_clear_config_cache()` for test isolation

**Test isolation** (`conftest.py`):
- Autouse fixture sets `LORE_CONFIG_DIR`, `LORE_STATE_DIR`, `LORE_CACHE_DIR` to `tmp_path`
- `mock.patch.dict(os.environ)` for clean env
- Clear config cache before/after each test

### What's New (Lore-specific)

| Component | Why new | ai-guardian has nothing similar |
|-----------|---------|-------------------------------|
| `store/sqlite.py` | Full CRUD + FTS5 + conflict tracking | ai-guardian only reads SQLite (transcript scanning) |
| `store/base.py` | `StoreBackend` ABC | No DB backend abstraction |
| `git/base.py` + `github.py` | `GitInterface` ABC — PR creation, repo sync | No git integration |
| `llm/base.py` + `ollama.py` | `LLMProvider` ABC — synthesis + capture | No LLM layer |
| `sync.py` | Git repo → SQLite sync with conflict detection | Entirely new |
| `capture.py` | Session transcript → knowledge extraction | Entirely new |
| `ingesters/` | Ingester framework (Phase 4) | No external source ingestion |

## Project Structure (adapted from ai-guardian)

~60% adapted from ai-guardian patterns, ~40% new (store, git, llm, sync, capture).

```
src/lore/
├── __init__.py
├── __main__.py                    # minimal entry wrapper (ai-guardian pattern)
├── cli.py                         # argparse subcommands (ai-guardian pattern)
├── config/
│   ├── loaders.py                 # XDG + mtime cache (adapted from ai-guardian)
│   ├── manager.py                 # resolution chain (adapted)
│   └── utils.py                   # path helpers (adapted)
├── mcp/
│   ├── server.py                  # FastMCP + @server.tool() (adapted)
│   └── skills/
│       └── LORE.md                # instructions= content
├── store/
│   ├── base.py                    # StoreBackend ABC (new)
│   └── sqlite.py                  # SQLite + FTS5 + conflict tracking (new)
├── git/
│   ├── base.py                    # GitInterface ABC (new)
│   └── github.py                  # GitHub PR creation via gh CLI (new)
├── llm/
│   ├── base.py                    # LLMProvider ABC (new)
│   └── ollama.py                  # Ollama synthesis + capture (new)
├── hook_adapters/
│   ├── base.py                    # HookAdapter ABC (from ai-guardian)
│   ├── claude.py                  # Claude Code adapter (adapted)
│   └── ...                        # Other agents (Phase 3)
├── sync.py                        # Git repo → SQLite sync engine (new)
├── capture.py                     # Session transcript → knowledge extraction (new)
├── ingesters/
│   ├── base.py                    # LoreIngester ABC (new, Phase 4)
│   └── ...
├── web/
│   ├── app.py                     # NiceGUI wrapper (adapted from ai-guardian)
│   └── pages/
│       ├── browser.py             # Knowledge browser
│       ├── individual.py          # Individual CRUD
│       ├── conflicts.py           # Conflict viewer
│       └── sync_status.py         # Sync status
├── setup/
│   └── hooks.py                   # IDE hook registration (adapted from ai-guardian)
tests/
├── conftest.py                    # Isolation fixtures (adapted from ai-guardian)
├── unit/
└── integration/
```

---

## Sprint Breakdown (MVP)

| Sprint | Calendar | Days | Deliverable |
|--------|----------|------|-------------|
| **1 — Skeleton** | Week 1 | ~3d | Read path: MCP server + SQLite + config + git sync + query |
| **2 — Capture** | Week 2-3 | ~7d | Write path: hooks + LLM capture + PR creation + promotion |
| **3 — Dashboard** | Week 3-4 | ~5d | NiceGUI UI + conflict viewer + polish + packaging |
| **Total** | **~3 weeks** | **~15 days** | With AI assistance (ai-guardian patterns accelerate) |
