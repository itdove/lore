# Lore — Development Plan

Incremental delivery. Each phase is independently usable. MVP is fully functional, not a throwaway — enterprise features layer on top without replacing anything.

**Core principle:** git repos are the source of truth for shared knowledge. Local SQLite is a cache + individual store. ABCs enable enterprise upgrades without refactoring.

---

## Architecture Overview

```
GIT REPOS (levels 1-N, admin-defined)       LOCAL (per developer)
─────────────────────────────────────       ────────────────────

level N repo@branch ──── PR ────┐
level 2 repo@branch ──── PR ────┤           FastMCP Server (stdio)
level 1 repo@branch ──── PR ────┤           ├── SQLite DB (all entries, all projects)
                                │           ├── LLM (Ollama local or remote)
level 0 (individual) ───────────┘           └── periodic git pull + reindex
(local only, highest priority)
```

**Level numbering:**
- Level 0 = individual (implicit, always exists, local SQLite, highest priority)
- Level 1 = closest shared level (most specific)
- Level N = broadest scope (lowest priority)
- Lower level number = higher priority = wins in conflicts (unless locked from above)

**Two config files:**

| Config | Location | Contains | Committed? |
|--------|----------|----------|-----------|
| Global | `$XDG_CONFIG_HOME/lore/config.json` | Project registry, LLM/store/git settings | No (per-developer) |
| Project | `.lore/config.json` | Hierarchy levels + repos/branches for THIS project | Yes (shared with team) |
| Protocol | `.lore/LORE.md` | Agent instructions | Yes (shared with team) |
| DB | `$XDG_DATA_HOME/lore/knowledge.db` | All entries across all projects | No (per-developer cache) |

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
├── level            INTEGER NOT NULL  -- 0=individual, 1-N=shared levels
├── level_name       TEXT NULL         -- optional display name (e.g. "team", "product")
├── repo_url         TEXT NULL         -- which knowledge repo this came from
├── repo_branch      TEXT NULL         -- which branch
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

**Global config** (`$XDG_CONFIG_HOME/lore/config.json`) — per-developer, not committed:

```json
{
  "lore": {
    "projects": [
      "/home/dev/project-A",
      "/home/dev/project-B"
    ],
    "store": {"type": "sqlite"},
    "llm": {"provider": "ollama", "model": "phi4-mini"},
    "git": {"provider": "github"},
    "sync_interval": "30m"
  }
}
```

`projects` array is populated by `lore init` — each project registers itself.

**Project config** (`.lore/config.json`) — committed to project repo, shared with team:

```json
{
  "lore": {
    "hierarchy": [
      {"level": 1, "name": "team", "repo": "github.com/org/knowledge", "branch": "team"},
      {"level": 2, "name": "product", "repo": "github.com/org/knowledge", "branch": "product"},
      {"level": 3, "name": "company", "repo": "github.com/org/knowledge", "branch": "org"}
    ]
  }
}
```

Two repo strategies: **single repo with branches** (default, simpler — PR auth via GitHub branch rulesets) or **separate repos** (enterprise — PR auth via CODEOWNERS + repo permissions).

**Examples:**

```
# Solo developer (level 0 only):
"hierarchy": []

# Small team (single repo, one branch):
"hierarchy": [
  {"level": 1, "repo": "github.com/team/knowledge"}
]

# Single repo with branches (default):
"hierarchy": [
  {"level": 1, "name": "team", "repo": "github.com/org/knowledge", "branch": "team"},
  {"level": 2, "name": "product", "repo": "github.com/org/knowledge", "branch": "product"},
  {"level": 3, "name": "company", "repo": "github.com/org/knowledge", "branch": "org"}
]

# Separate repos (enterprise):
"hierarchy": [
  {"level": 1, "name": "team", "repo": "github.com/org/team-knowledge"},
  {"level": 2, "name": "product", "repo": "github.com/org/product-knowledge"},
  {"level": 3, "name": "company", "repo": "github.com/org/org-knowledge"}
]

# Multiple repos at same level:
"hierarchy": [
  {"level": 1, "repo": "github.com/org/team-alpha-knowledge"},
  {"level": 1, "repo": "github.com/org/team-beta-knowledge"},
  {"level": 2, "repo": "github.com/org/product-knowledge"}
]
```

**Core data model:**

```python
@dataclass
class HierarchyLevel:
    level: int            # 1-N (0 = individual, implicit)
    repo: str             # git repo URL
    branch: str = "main"  # branch within repo
    name: str | None = None  # display name (optional, for UI/reports)

@dataclass
class GlobalConfig:
    projects: list[str]   # registered project paths
    store: StoreConfig
    llm: LLMConfig
    git: GitConfig
    sync_interval: str = "30m"

@dataclass
class ProjectConfig:
    hierarchy: list[HierarchyLevel]
```

**MCP server startup:**
1. Read global config → provider settings + project list
2. For each project: read `.lore/config.json` → hierarchy
3. Sync all unique `repo@branch` across all projects
4. On query → detect CWD → match to project → use that project's hierarchy for scoping

**Query scoping:**
```python
def query_knowledge(self, topic):
    project_config = get_project_config(cwd=self.working_dir)
    allowed = [(h.repo, h.branch) for h in project_config.hierarchy]
    results = self.store.query_fts(topic, filter_repos=allowed, include_level_0=True)
    # level 0 (individual) always included
```

Code never references level names — everything is `level: int`. Lower level = higher priority = wins in conflicts (unless locked from above).

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
- Global config: `$XDG_CONFIG_HOME/lore/config.json` (project registry + provider settings)
- Project config: `.lore/config.json` (hierarchy for this project, committed to repo)
- MCP server reads global config → loads all registered projects → serves per-project queries based on CWD

*Git knowledge repos:*
- Levels 1-N of git repos, defined in each project's `.lore/config.json`
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
- Level maintainer reviews via normal git diff
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
- Group → role mapping: IdP groups → Lore roles (user, level_maintainer, admin)
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

**Deliverable:** level maintainers and admins get visibility and control without CLI.

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
    level 1 (old) → level 1 (new): 182 entries (repos changed)
    level 2 (old) → level 2 (new): 45 entries (unchanged)
    level 3 (old) → split into level 3 + level 4: 20 entries
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
