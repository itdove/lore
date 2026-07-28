#!/usr/bin/env bash
set -euo pipefail
set -x

# ============================================================
# Lore Demo Setup Script
# Creates knowledge repo, demo project, and configures lore
#
# Usage: ./create-demo-config.sh [GITHUB_USER]
#   GITHUB_USER defaults to your GitHub username (via gh api)
#
# Level 0 (individual): implicit, SQLite only
# Level 1 (project): implicit, .lore/knowledge/ in project repo
# Level 2+ (user-defined): configured git repos
# ============================================================

GITHUB_USER="${1:-$(gh api user --jq .login 2>/dev/null || echo "")}"
if [ -z "$GITHUB_USER" ]; then
    echo "ERROR: Could not detect GitHub username. Pass it as argument: $0 <username>"
    exit 1
fi
echo "Using GitHub user: $GITHUB_USER"

DEMO_DIR=~/development/ai/lore-demo
DEMO_REPO_NAME=lore-demo
TEAM_KNOWLEDGE_DIR=~/development/ai/lore-demo-team-knowledge
TEAM_REPO_NAME=lore-demo-team-knowledge
DOCS_DIR=~/development/ai/lore-demo-docs

# --- 1. Create Team Knowledge Repository (level 2) ---

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

# --- 2. Create Docs Repository (level 3, local, doc-repo ingester) ---

if [ -d "$DOCS_DIR" ]; then
    echo "Docs repo already exists at $DOCS_DIR, skipping creation"
else
    mkdir -p "$DOCS_DIR" && cd "$DOCS_DIR"
    git init

    mkdir -p docs/guides docs/reference docs/internal

    cat > docs/guides/deployment.md << 'EOF'
# Kubernetes Deployment Guide

## Prerequisites

Ensure you have kubectl configured and access to the target cluster.
All services use Helm charts stored in the `charts/` directory.

## Deploying a Service

1. Build the Docker image: `docker build -t myapp:latest .`
2. Push to the container registry: `docker push registry.example.com/myapp:latest`
3. Update the Helm values file with the new image tag
4. Run `helm upgrade --install myapp charts/myapp -f values-prod.yaml`

## Rolling Updates

Services are configured with `maxSurge: 1` and `maxUnavailable: 0` to ensure
zero-downtime deployments. The readiness probe must pass before traffic is
routed to new pods.

## Rollback

If a deployment fails, run `helm rollback myapp` to revert to the previous
release. Helm keeps the last 10 releases by default.
EOF

    cat > docs/guides/monitoring.md << 'EOF'
# Monitoring and Alerting

## Metrics Collection

All services expose Prometheus metrics on `/metrics`. The standard metrics
include request latency (p50, p95, p99), error rate, and active connections.

## Alerting Rules

Critical alerts page the on-call engineer via PagerDuty:
- Error rate > 5% for 5 minutes
- P99 latency > 2 seconds for 10 minutes
- Pod restarts > 3 in 15 minutes

Warning alerts go to the team Slack channel:
- Error rate > 1% for 10 minutes
- P95 latency > 1 second for 15 minutes
- Disk usage > 80%

## Dashboards

Each service has a Grafana dashboard with request rate, latency distribution,
error breakdown by status code, and resource utilization panels.
EOF

    cat > docs/reference/api-auth.md << 'EOF'
# API Authentication Reference

## Authentication Methods

All API endpoints require authentication via one of:
- Bearer token (JWT) in the Authorization header
- API key in the X-API-Key header (for service-to-service calls)

## JWT Token Format

Tokens are signed with RS256 using rotating keys. The public key set is
available at `/.well-known/jwks.json`. Tokens expire after 1 hour.

Required claims: `sub`, `iss`, `exp`, `iat`, `scope`.

## Rate Limiting

- Authenticated users: 1000 requests/minute
- Service accounts: 5000 requests/minute
- Unauthenticated: 60 requests/minute (public endpoints only)

Rate limit headers: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset.
EOF

    cat > docs/internal/roadmap.md << 'EOF'
# Internal Roadmap (Confidential)

This file should be excluded from ingestion via exclude_paths.

Q3 2026: Launch v2 API with breaking changes.
Q4 2026: Deprecate v1 API.
EOF

    git add -A && git commit -m "Initial documentation"
fi

# --- 3. Create Demo Project ---

mkdir -p "$DEMO_DIR" && cd "$DEMO_DIR"
git init

# --- 4. Configure global embedding (before init to skip interactive prompts) ---

lore config set lore.search.embedding_provider ollama
lore config set lore.search.embedding_model nomic-embed-text

# --- 5. Initialize Lore (non-interactive) ---
# Level 1 (project) is implicit — .lore/knowledge/ created by init
# Global embedding already configured above, so init skips provider prompt

lore init --no-levels

# --- 5b. Configure per-project settings (after init creates project config) ---

lore config set lore.search.min_similarity 0.6
lore config set lore.llm.provider ollama
lore config set lore.llm.model phi4-mini

# --- 5c. Configure ai-guardian ---

mkdir -p .ai-guardian
cat > .ai-guardian/ai-guardian.json << 'EOF'
{
  "prompt_injection": {
    "allowlist_patterns": [
      "__init__",
      "__import__",
      "__class__",
      "__globals__",
      "__builtins__",
      "__mro__",
      "__subclasses__"
    ]
  },
  "permissions": {
    "rules": [
      {
        "mode": "allow",
        "matcher": "mcp__lore__*",
        "patterns": [
          "mcp__lore__*"
        ]
      }
    ]
  }
}
EOF
touch .ai-guardian/ai-guardian.json.lock

# --- 6. Add project-level knowledge to .lore/knowledge/ ---
# These live in the project repo itself (level 1, implicit)

mkdir -p .lore/knowledge/decision/arch .lore/knowledge/pattern/config .lore/knowledge/bug/deploy

cat > .lore/knowledge/decision/arch/nicegui-dashboard.md << 'EOF'
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

cat > .lore/knowledge/pattern/config/global-vs-project.md << 'EOF'
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

cat > .lore/knowledge/bug/deploy/sqlite-vec-macos.md << 'EOF'
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

git add -A && git commit -m "Add project-level knowledge"
gh repo create "$DEMO_REPO_NAME" --private --source=. --push

# --- 7. Add team hierarchy level (level 2) ---

lore config add-level \
  --level 2 \
  --name team \
  --repo github.com/$GITHUB_USER/$TEAM_REPO_NAME \
  --branch main \
  --writable \
  --description "Store here when knowledge applies to all projects this team works on: shared conventions, cross-project decisions, general coding rules"

# --- 8. Add docs hierarchy level (level 3, doc-repo ingester) ---

lore config add-level \
  --level 3 \
  --name docs \
  --repo "$DOCS_DIR" \
  --branch main \
  --no-writable \
  --ingester doc-repo \
  --doc-paths "docs/guides,docs/reference" \
  --exclude-paths "docs/internal" \
  --description "LLM-extracted knowledge from unstructured documentation"

# --- 9. Commit and push final config ---

git add -A && git commit -m "Add hierarchy levels and config" && git push

# --- 10. First sync ---

lore sync --force

echo ""
echo "============================================================"
echo "Demo setup complete!"
echo ""
echo "Project knowledge:   $DEMO_DIR/.lore/knowledge/ (level 1, implicit)"
echo "Team knowledge repo: $TEAM_KNOWLEDGE_DIR (level 2)"
echo "Docs repo:           $DOCS_DIR (level 3, doc-repo ingester)"
echo "Demo project:        $DEMO_DIR"
echo "Global config:       ~/.config/lore/config.json"
echo ""
echo "Next steps:"
echo "  cd $DEMO_DIR"
echo "  lore search 'jwt'"
echo "  lore dashboard"
echo "============================================================"
