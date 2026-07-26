#!/usr/bin/env bash
set -euo pipefail
set -x

# ============================================================
# Lore Demo Setup Script
# Creates knowledge repo, demo project, and configures lore
# ============================================================

DEMO_DIR=~/development/ai/lore-demo
PROJECT_KNOWLEDGE_DIR=~/development/ai/lore-demo-project-knowledge
TEAM_KNOWLEDGE_DIR=~/development/ai/lore-demo-team-knowledge
PROJECT_REPO_NAME=lore-demo-project-knowledge
TEAM_REPO_NAME=lore-demo-team-knowledge

# --- 1. Create Project Knowledge Repository (level 1) ---

if [ -d "$PROJECT_KNOWLEDGE_DIR" ]; then
    echo "Project knowledge repo already exists at $PROJECT_KNOWLEDGE_DIR, skipping creation"
else
    mkdir -p "$PROJECT_KNOWLEDGE_DIR" && cd "$PROJECT_KNOWLEDGE_DIR"
    git init

    mkdir -p decision/arch pattern/config bug/deploy

    cat > decision/arch/nicegui-dashboard.md << 'EOF'
---
tags: [decision, architecture, dashboard]
lock: true
---
NiceGUI chosen for the web dashboard over Streamlit and Dash.

Reasons:
- Pure Python — no JS build step, fits our all-Python stack
- Supports async handlers natively (critical for SQLite thread safety)
- Left-drawer tab layout works well for our browse/sync/config pages
- Dialogs and reactive UI without React complexity

Decision date: 2026-07-20. Revisit: 2027-Q1.
EOF

    cat > pattern/config/global-vs-project.md << 'EOF'
---
tags: [pattern, config, architecture]
---
Config split: global vs per-project.

Global-only (shared resources): store.path, store.type,
search.embedding_provider, search.embedding_model.

Per-project (can vary): llm.provider, llm.model, search.min_similarity,
hierarchy, sync settings, git.provider.

Embedding must be global because all entries share one vector space.
LLM synthesis can vary — different projects may want different models.
EOF

    cat > bug/deploy/sqlite-vec-macos.md << 'EOF'
---
tags: [bug, sqlite, macos]
---
Python 3.12 on macOS (pyenv) lacks enable_load_extension.

sqlite_vec.load(conn) calls conn.load_extension() internally and fails
with AttributeError. The sqlite_vec.Connection wrapper doesn't help —
it's just a re-export of sqlite3.Connection.

Fix: Use _VEC_LOADED flag in store/sqlite.py to branch between SQL
and Python distance paths. Cosine distance computed in Python as
fallback — same results, just slower at scale.
EOF

    git add -A && git commit -m "Initial project knowledge base"
    gh repo create "$PROJECT_REPO_NAME" --private --source=. --push
fi

# --- 2. Create Team Knowledge Repository (level 2) ---

if [ -d "$TEAM_KNOWLEDGE_DIR" ]; then
    echo "Team knowledge repo already exists at $TEAM_KNOWLEDGE_DIR, skipping creation"
else
    mkdir -p "$TEAM_KNOWLEDGE_DIR" && cd "$TEAM_KNOWLEDGE_DIR"
    git init

    mkdir -p convention/naming convention/testing decision/arch bug/api

    cat > convention/naming/snake-case.md << 'EOF'
---
tags: [convention, naming]
---
Use snake_case for all Python identifiers and database column names.

Matches Postgres schema naming convention and avoids mixed casing
inconsistencies between ORM models and raw SQL queries.
EOF

    cat > convention/testing/fixtures-over-mocks.md << 'EOF'
---
tags: [convention, testing]
---
Prefer pytest fixtures with real database connections over mocks.

Mocked tests passed but production migration failed (2026-Q1 incident).
Use testcontainers for Postgres fixtures in CI.
EOF

    cat > decision/arch/fastapi-over-flask.md << 'EOF'
---
tags: [decision, architecture]
lock: true
---
FastAPI chosen over Flask for all new HTTP services.

Reasons:
- Native async support reduces thread pool sizing
- Pydantic validation built-in (no marshmallow dependency)
- OpenAPI docs auto-generated
- 3x throughput improvement in load tests (see perf/2026-Q1-results)

Decision date: 2026-03-15. Revisit: 2027-Q1.
EOF

    cat > bug/api/jwt-clock-skew.md << 'EOF'
---
tags: [bug, auth, jwt]
---
JWT validation failures during deployments caused by clock skew
between API servers and auth service.

Root cause: NTP sync interval was 1 hour. Tokens with <30s remaining
would fail on servers 10-15s behind.

Fix: Reduced NTP sync to 5 minutes + added 30s leeway to
`jwt.decode(leeway=30)`. Applied to all services using shared
auth middleware.
EOF

    git add -A && git commit -m "Initial team knowledge base"
    gh repo create "$TEAM_REPO_NAME" --private --source=. --push
fi

# --- 3. Create Demo Project ---

mkdir -p "$DEMO_DIR" && cd "$DEMO_DIR"

# --- 4. Initialize Lore (non-interactive) ---

lore init --no-levels

# --- 5. Add hierarchy levels ---

lore config add-level \
  --level 1 \
  --name project \
  --repo github.com/itdove/$PROJECT_REPO_NAME \
  --branch main \
  --writable \
  --description "Store here when knowledge is specific to this project: architecture decisions, project-specific patterns, known bugs in this codebase"

lore config add-level \
  --level 2 \
  --name team \
  --repo github.com/itdove/$TEAM_REPO_NAME \
  --branch main \
  --writable \
  --description "Store here when knowledge applies to all projects this team works on: shared conventions, cross-project decisions, general coding rules"

# --- 6. Configure global settings ---

lore config set lore.search.embedding_provider ollama
lore config set lore.search.embedding_model nomic-embed-text
lore config set lore.search.min_similarity 0.3
lore config set lore.llm.provider ollama
lore config set lore.llm.model phi4-mini

# --- 7. First sync ---

lore sync --force

echo ""
echo "============================================================"
echo "Demo setup complete!"
echo ""
echo "Project knowledge repo: $PROJECT_KNOWLEDGE_DIR"
echo "Team knowledge repo:    $TEAM_KNOWLEDGE_DIR"
echo "Demo project:           $DEMO_DIR"
echo "Global config:          ~/.config/lore/config.json"
echo ""
echo "Next steps:"
echo "  cd $DEMO_DIR"
echo "  lore search 'jwt'"
echo "  lore dashboard"
echo "============================================================"
