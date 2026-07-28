# Lore Demo Scenario (MVP + Phase 2)

## What Lore Delivers

Lore is an MCP server that gives AI coding agents shared team knowledge stored in git repositories.

**Git repo → SQLite + FTS5 + vector embeddings → MCP tools + Claude Code hooks → auto-recall, capture, PR review**

### Capabilities

| Feature | CLI | MCP Tool | Hook |
|---------|-----|----------|------|
| Initialize project | `lore init` | — | — |
| Sync knowledge repos | `lore sync` | — | Auto (recall hook) |
| Search knowledge | `lore search <query>` | `query_knowledge` | — |
| Semantic search | `lore search <query>` | `query_knowledge` | — |
| List entries | — | `list_knowledge` | — |
| Store knowledge | — | `store_knowledge` | Capture (Stop hook) |
| Negate stale entry | — | `negate_knowledge` | Capture (Stop hook) |
| Delete knowledge | — | `delete_knowledge` | — |
| View conflicts | `lore conflicts` | `list_conflicts` | — |
| Health check | — | `health_check` | — |
| Auto-recall context | — | — | UserPromptSubmit |
| Mid-session nudge | — | — | PostToolUse |
| Session-end capture | — | — | SessionEnd |
| View/edit config | `lore config show\|set\|edit` | — | — |
| Web dashboard | `lore dashboard` | — | — |
| Check sync status | `lore sync --status` | — | — |
| Doc repo ingestion | `lore sync` | — | — |

---

## Demo Setup (One-Time)

### 1. Install Lore

```bash
cd /path/to/lore
pip install -e ".[dev]"
lore --help
```

### 2. Run Setup Script

The script creates the knowledge repo, demo project, and configures everything:

```bash
cd /path/to/lore
./scripts/create-demo-config.sh
```

This creates:
- `~/development/ai/lore-demo/` — demo project with lore initialized
- `~/development/ai/lore-demo/.lore/knowledge/` — project-level knowledge (level 1, implicit, in project repo)
- `~/development/ai/lore-demo-team-knowledge/` — git repo with 4 team-wide entries (level 2)
- `~/development/ai/lore-demo-docs/` — local git repo with unstructured docs for doc-repo ingestion (level 3)
- `.lore/config.json` — project config with team hierarchy (levels 2-3)
- `.mcp.json` — MCP server registration
- `.claude/settings.json` — Claude Code hooks (recall, nudge, capture)
- `~/.config/lore/config.json` — global config (ollama embedding, LLM, capture settings)
- SQLite database at `~/.local/share/lore/lore.db`

See `scripts/create-demo-config.sh` for the full setup details.

### Configuration Architecture

Settings are split between global and project config:

| Setting | Location | Why |
|---------|----------|-----|
| `search.embedding_provider` | Global | All entries share one vector space |
| `search.embedding_model` | Global | Same vector space |
| `store.path` | Global | Single shared DB |
| `llm.provider` | Per-project | Different projects may use different synthesis models |
| `search.min_similarity` | Per-project | Different thresholds per project |
| `hierarchy` | Per-project | Each project defines its own levels |
| `sync.*` | Per-project | Per-project sync preferences |
| `git.provider` | Per-project | GitHub vs GitLab |

`lore config set` auto-routes global-only keys to global config.

### Hierarchy Levels

The demo uses 4 levels:

| Level | Name | Description | Storage | Ingester |
|-------|------|-------------|---------|----------|
| 0 | individual | Local entries, no review needed | SQLite only | — |
| 1 | project | Discoveries about this specific project | SQLite + `.lore/knowledge/` in project repo (implicit) | — |
| 2 | team | General coding and development rules | `lore-demo-team-knowledge` repo | default (frontmatter) |
| 3 | docs | LLM-extracted knowledge from unstructured docs | `lore-demo-docs` local repo | `doc-repo` |

Levels 0 and 1 are **implicit** — no config entry needed. Level 1 uses `.lore/knowledge/` in the project repo itself. User-defined levels (2+) each point to a separate git repo.

Level 3 uses `ingester: "doc-repo"` with `doc_paths` and `exclude_paths` to scan specific directories and extract knowledge via LLM. Requires Ollama.

Each user-defined level can have:
- `writable: true` (default) — agents can store via MCP, creates PRs
- `writable: false` — read-only, maintained by humans via git only
- `description` — helps LLM capture hook decide where to store knowledge

### Key Format

Keys use 1-N colon-separated segments:
- `jwt-leeway` (1 segment)
- `bug:jwt` (2 segments)
- `bug:api:jwt-clock-skew` (3 segments)
- `bug:api:auth:jwt-clock-skew` (4+ segments)

Git sync derives keys from file path: `bug/api/jwt.md` → `bug:api:jwt`

### Write Isolation

- **Levels 1+ (project and shared repos):** `store_knowledge` creates a PR only — no DB write. DB entries are populated exclusively by `lore sync` after PR merge. Git repo is the single source of truth.

### Optional: Ollama Setup (for semantic search + LLM synthesis + session-end capture)

Ollama is **not required** for basic keyword search. Without it, lore uses FTS5 only (exact keyword matching), no synthesis, and session-end capture is disabled.

`lore init` now defaults to `ollama` for embedding provider. To enable the full feature set:

```bash
# Install Ollama (if not already installed)
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama server
ollama serve

# Pull models
ollama pull phi4-mini           # LLM synthesis + capture
ollama pull nomic-embed-text    # Embeddings for semantic search
```

The setup script (`create-demo-config.sh`) already configures embedding and LLM providers. If running manually, the equivalent commands are:

```bash
lore config set lore.search.embedding_provider ollama
lore config set lore.search.embedding_model nomic-embed-text
lore config set lore.llm.provider ollama
lore config set lore.llm.model phi4-mini
```

With Ollama enabled:
- **Semantic search** — `query_knowledge` uses hybrid search (FTS5 + vector embeddings + RRF fusion). Natural language queries like "API framework standard" match entries containing "FastAPI chosen over Flask"
- **LLM synthesis** — `query_knowledge` returns a `synthesized` field summarizing results
- **Dedup on store** — `store_knowledge` detects near-duplicate entries via cosine similarity
- **Session-end capture** — `SessionEnd` hook extracts knowledge from transcript, enriches existing entries, proposes shared-level entries for review
- **Embeddings computed on sync** — `lore sync` generates embeddings for all entries
- **sqlite-vec** — native SQL-level vector distance when available, falls back to Python implementation

> **Recommended for the demo:** Enable Ollama to show semantic search (Scene 3b). Without it, queries must use exact keywords from the documents.

> **macOS (pyenv) note:** To enable native sqlite-vec support, rebuild Python with SQLite extension loading:
> ```bash
> brew install sqlite3
> PYTHON_CONFIGURE_OPTS="--enable-loadable-sqlite-extensions" \  # ai-guardian:allow
> LDFLAGS="-L$(brew --prefix sqlite3)/lib" \
> CPPFLAGS="-I$(brew --prefix sqlite3)/include" \
> pyenv install 3.12.11 --force
> pyenv rehash && pip install -e ".[dev]"
> ```
> Without this, lore falls back to Python cosine distance — same results, just slower at scale. Not required for the demo.

---

## Demo Script

### Scene 1: CLI Search

Show that knowledge is indexed and searchable from the terminal.

```bash
# Search for naming conventions
lore search "snake_case naming"
```

Expected output:

```
  convention:naming:snake-case  (team)
    Use snake_case for all Python identifiers and database column names...

1 result(s)
```

```bash
# Search for JWT issues — exact keyword match
lore search "jwt validation"
```

Expected output:

```
  bug:api:jwt-clock-skew  (team)
    JWT validation failures during deployments caused by clock skew...

1 result(s)
```

```bash
# Same entry found with different words — semantic match (requires Ollama)
lore search "jwt authentication"
```

Expected output (same entry, matched via embeddings):

```
  bug:api:jwt-clock-skew  (team)
    JWT validation failures during deployments caused by clock skew...

1 result(s)
```

### Scene 2: Auto-Recall via Hook

Open Claude Code in the project directory. The hooks auto-registered during `lore init`.

**How it works:** When you type a prompt, the `UserPromptSubmit` hook fires `lore hook recall` — it checks staleness, spawns a background sync if needed, queries the knowledge base, and injects relevant context before Claude processes your prompt.

**Prompt Claude Code:**

> "I'm adding JWT validation to the new payments service"

Before Claude even sees this, the recall hook has already injected the JWT clock skew knowledge into context. Claude advises adding `leeway=30` to `jwt.decode()` — without being asked to check lore.

### Scene 3: MCP Tool Query

For explicit queries, Claude calls the MCP tools directly.

**Prompt Claude Code:**

> "Check lore for our team's decision on FastAPI vs Flask"

Claude Code calls `query_knowledge(topic="FastAPI Flask")` and gets the locked decision entry. It knows FastAPI is the standard — no debate needed.

> **Demo tip:** Phrasing like "check lore" explicitly triggers the MCP tool. Without it, Claude may answer from its own training data and skip the tool call.

### Scene 3b: Semantic Search (requires Ollama)

Show that natural language queries work even without exact keyword matches.

**From CLI:**

```bash
# "authentication" doesn't appear in the entry (it uses "validation")
lore search "jwt authentication"
```

Expected: only `bug:api:jwt-clock-skew` returned — semantic match via vector similarity.

**From Claude Code:**

> "check lore for API framework standard"

Claude finds `decision:arch:fastapi-over-flask` — "API framework standard" matches "FastAPI chosen over Flask" semantically.

> **Key differentiator:** Without embeddings, users must know the exact words in the knowledge base. With embeddings, they describe what they're looking for in natural language.

### Scene 4: Store Individual Knowledge via MCP

Show that Claude Code can write knowledge during a session — stored locally, no review needed.

**Prompt Claude Code:**

> "Store in lore as an individual entry: key 'bug:deploy:docker-layer-cache', value 'Docker layer cache invalidation causes 15-minute builds when requirements.txt changes. Fix: use --mount=type=cache for pip install layer.', tags 'bug,docker,ci'"

Claude Code calls `store_knowledge(key="bug:deploy:docker-layer-cache", value="...", tags="bug,docker,ci", level="individual")` and the entry is stored locally in SQLite.

Verify from CLI:

```bash
lore search "docker layer cache"
```

Expected: entry appears with `(individual)` level label.

### Scene 5: Store Knowledge at Project Level (PR-based)

Show the PR-based store flow. The agent only stores when explicitly asked. When storing at level "project", lore creates a PR to `.lore/knowledge/` in the project repo. The entry appears in the DB after the PR is merged and `lore sync` runs.

**Prompt Claude Code:**

> "Store in lore at project level: key 'bug:deploy:docker-layer-cache', value 'Docker layer cache invalidation causes 15-minute builds when requirements.txt changes. Fix: use --mount=type=cache for pip install layer.', tags 'bug,docker,ci'"

Claude Code calls `store_knowledge(..., level="project")` which:
1. Creates a branch `lore/lore-knowledge-bug-deploy-docker-layer-cache-<timestamp>`
2. Writes the markdown file at `.lore/knowledge/bug/deploy/docker-layer-cache.md`
3. Pushes and creates a PR via `gh pr create`
4. Returns `{"key": "...", "level": 1, "pr_url": "https://github.com/..."}`

> **Variation:** To store at team level (level 2), use `level="team"` instead. This targets the team knowledge repo — useful when the knowledge applies across all projects.

The team reviews the PR in normal git workflow. Once merged, `lore sync` picks it up for everyone.

> **Note:** After the PR is created, show it in the GitHub UI — the file appears at `.lore/knowledge/bug/deploy/docker-layer-cache.md` with proper frontmatter.

### Scene 6: Negate Stale Knowledge

Show that outdated knowledge can be contradicted with a reason.

**Prompt Claude Code:**

> "Negate the lore entry 'bug:api:jwt-clock-skew' with reason 'Fixed permanently in auth-service v3.2 — NTP replaced with PTP, leeway no longer needed'"

Claude Code calls `negate_knowledge(key="bug:api:jwt-clock-skew", reason="...")`. The entry is marked as negated with the reason recorded in history. It stops appearing in query results.

### Scene 7: Locked Entry Priority

Demonstrate that locked entries always win regardless of level.

```bash
# The FastAPI decision is locked — it can't be overridden
lore search "fastapi"
```

The `lock: true` frontmatter ensures this decision propagates unchanged. Even if a local project has a different preference, the locked shared entry takes priority.

### Scene 8: Sync Updates

Show that knowledge stays current with git.

```bash
# Add a new entry to the team knowledge repo
cd ~/development/ai/lore-demo-team-knowledge
mkdir -p convention/logging

cat > convention/logging/structured-json.md << 'EOF'
---
tags: [convention, logging]
---
Use structured JSON logging in all services. No free-form string logs.

Use structlog with processors for consistent key ordering.
Required fields: timestamp, level, service, trace_id, message.
This enables centralized log aggregation and alerting via Datadog.
EOF

git add -A && git commit -m "Add structured logging convention"

git push

# Back in your project
cd ~/development/ai/lore-demo
lore sync
```

Expected output:

```
Sync complete: 1 created, 0 updated, 0 deleted, 0 promoted
```

Now Claude Code can surface this when someone writes mocked DB tests.

> **Note:** With auto-sync enabled (#40), the recall hook checks staleness and spawns a background sync automatically. Manual `lore sync` is still available for immediate sync.

### Scene 9: Doc Repo Ingestion (requires Ollama)

Show that `lore sync` can ingest unstructured documentation repos using LLM extraction. Unlike team knowledge (level 2) which uses frontmatter-based markdown, the docs repo (level 3) uses `ingester: "doc-repo"` to extract knowledge from plain documentation files.

The demo docs repo was created by the setup script with guides and architecture docs — no lore frontmatter, just regular documentation.

```bash
cd ~/development/ai/lore-demo
lore sync --force --verbose
```

Expected output includes entries extracted from the docs:

```
Sync complete: N created, 0 updated, 0 deleted, 0 promoted
  [+] guide:deployment:k8s-setup (docs/guides/deployment.md)
  [+] reference:api:auth-endpoints (docs/reference/api-auth.md)
```

The LLM generates structured keys, summaries, and tags from unstructured documentation. Each entry has provenance tracking back to the source file and commit.

```bash
lore search "deployment kubernetes"
```

Expected: entries extracted from the deployment guide, with `(docs)` level label.

**Configuration in `.lore/config.json`:**

```json
{
  "level": 3,
  "repo": "/path/to/lore-demo-docs",
  "branch": "main",
  "name": "docs",
  "ingester": "doc-repo",
  "doc_paths": ["docs/guides", "docs/reference"],
  "exclude_paths": ["docs/internal"]
}
```

- `doc_paths` — only scan these directories (omit to scan entire repo)
- `exclude_paths` — skip these directories
- `ingester: "doc-repo"` — use LLM extraction instead of frontmatter parser

### Scene 10: Conflict Detection

```bash
lore conflicts
```

Shows entries where the same key exists at different hierarchy levels with different values. Each conflict displays both sides and the resolution status.

### Scene 11: Web Dashboard

Launch the NiceGUI dashboard to browse knowledge visually:

```bash
lore dashboard
```

Opens `http://127.0.0.1:8765` with:
- **Overview** — entry counts, sync status, health
- **Browse** — all entries filterable by level/type/domain/tags, refreshes on tab switch
- **New Entry** — create level 0 entries with key validation
- **Conflicts** — both sides linked, resolve (keep A/B, merge, dismiss)
- **Sync** — status card, hierarchy table, manual trigger
- **Config** — visual editor for global and per-project config
  - **Global tab**: embedding provider/model (global-only), default LLM, sync, git
  - **Project tab**: project selector dropdown, hierarchy table (add/remove levels, writable flag), LLM override, search thresholds
  - Raw JSON toggle for power users, backup on save

Entry detail dialog shows:
- Level 0: Edit, Delete, Promote buttons
- Shared writable levels: view only (no edit/delete — managed via git)
- Read-only levels: "Read-only" badge, no action buttons

### Scene 12: Health Check (via MCP)

Claude Code can call `health_check()` to get:

```json
{
  "total": 8,
  "per_level": {"0": 1, "1": 3, "2": 4},
  "conflicts": 0,
  "stale_count": 0,
  "last_sync": {}
}
```

### Scene 13: Configuration

View and edit config without touching JSON files:

```bash
# View merged config (global + project)
lore config show

# View project config only
lore config show --project

# Set a value (auto-routes global-only keys to global config)
lore config set lore.search.embedding_provider ollama  # → global config
lore config set lore.search.min_similarity 0.5         # → project config

# Open in editor
lore config edit
```

### Scene 14: Session-End Capture

When a Claude Code session ends, the `SessionEnd` hook fires `lore hook capture`. The hook forks a background process (so Claude Code exits immediately) that extracts knowledge from the session.

**How to trigger:** Have a conversation that mentions knowledge WITHOUT asking Claude to store it. The capture hook picks up what the agent didn't explicitly save.

```bash
cd ~/development/ai/lore-demo
claude
```

Example conversation (do NOT say "store in lore"):

> "We found that our Celery workers deadlock when using Redis as both broker and result backend on the same connection. The fix was to use a separate Redis instance for the result backend."

Then exit (`/exit` or Ctrl+D). Wait ~15 seconds for the background LLM extraction.

**Check results:**

```bash
cat ~/.local/state/lore/capture.jsonl
```

Or open the dashboard and click the **Capture** tab:

```bash
lore dashboard
```

**Pipeline:**

1. Reads session transcript from stdin, forks to background
2. LLM extracts knowledge candidates (bugs, decisions, patterns)
3. Candidates classified:
   - **NEW** → stored individually (if `auto_store_individual: true`)
   - **ENRICH** → merged into existing similar entry (embedding dedup)
   - **UPDATE** → updates existing entry with new value
   - **NEGATE** → marks contradicted entries as negated
   - **SKIP** → exact duplicates or rate-limited
4. Results logged to `capture.jsonl` and visible in the dashboard Capture tab

> **Note:** Agents only call `store_knowledge` when the user explicitly asks (e.g., "store in lore"). Session-end capture is the automatic safety net for knowledge that would otherwise be lost.

Capture config:

```json
{
  "lore": {
    "capture": {
      "max_entries_per_session": 5,
      "min_novelty_score": 0.3,
      "auto_store_individual": true,
      "auto_pr_shared": false
    }
  }
}
```

---

## Key Talking Points

1. **Knowledge lives in git** — version controlled, reviewable via PRs, no vendor lock-in
2. **Markdown + frontmatter** — files humans can read and edit directly
3. **Hybrid search** — FTS5 keyword + vector embeddings + RRF fusion. Natural language queries work without exact keyword matches
4. **MCP integration** — any MCP-compatible AI agent can query and store knowledge
5. **Hierarchy levels** — team → project → individual knowledge with priority resolution
6. **Writable flag** — control which levels agents can write to, read-only for compliance
7. **Locked entries** — architectural decisions that can't be overridden locally
8. **Sync is incremental** — content-hash based, only processes changed files
9. **Write isolation** — level 0 writes SQLite only; levels 1+ create PRs only. DB populated by sync after merge. Git repo is source of truth
10. **Auto-recall** — knowledge injected into agent context before every prompt
11. **Session-end capture** — LLM extracts, dedup enriches, rate limits, proposes for review
12. **PR-based review** — shared knowledge changes auto-create PRs for team review
13. **Negate stale knowledge** — contradict outdated entries with a reason
14. **Flexible keys** — 1-N colon-separated segments, derived from file path for git sources
15. **Global vs per-project config** — embedding/store global (shared DB), LLM/thresholds per-project
16. **Project-level setup** — MCP + hooks scoped per project, not global
17. **Web dashboard** — NiceGUI UI with config editor, project selector, browse/CRUD/conflicts/sync
18. **Auto-sync** — background sync on staleness, never blocks the hook
19. **Ollama optional** — semantic search, LLM synthesis, and capture work with local Ollama, but basic FTS5 search works without it
20. **Dedup on store** — cosine similarity detects near-duplicate entries, prevents knowledge sprawl
21. **Doc repo ingestion** — `ingester: "doc-repo"` extracts structured knowledge from unstructured docs via LLM, with `doc_paths`/`exclude_paths` filtering

## Demo Cleanup

Run the cleanup script (shows what will be deleted, asks for confirmation):

```bash
cd /path/to/lore
./scripts/delete-demo-config.sh
```

The script auto-detects your GitHub username, or pass it explicitly:

```bash
./scripts/delete-demo-config.sh myusername
```

After cleanup, restart Claude Code and re-run from **Demo Setup** to demo again.

---

## What's Next (Phase 3+)

- **Multi-agent hooks** (#15) — Cursor, Copilot, Windsurf, and 10 more agents
- **Ingester framework** (#16) — Auto-ingest from external tools (ReasonsForge, OpenWolf, Jira)
- **Doc ingestion CLI** (#36) — `lore ingest --file <path>` for one-off file ingestion (doc-repo sync via #37 is done)
- **PyPI publication** (#34) — `pip install lorehive`
- **NotebookLM integration** (#38) — One notebook per hierarchy level
