#!/usr/bin/env bash
set -euo pipefail
set -x

# ============================================================
# Lore Demo Setup Script
# Creates knowledge repo, demo project, and configures lore
# ============================================================

DEMO_DIR=~/development/ai/lore-demo
KNOWLEDGE_DIR=~/development/ai/lore-demo-knowledge
REPO_NAME=lore-demo-knowledge

# --- 1. Create Knowledge Repository ---

if [ -d "$KNOWLEDGE_DIR" ]; then
    echo "Knowledge repo already exists at $KNOWLEDGE_DIR, skipping creation"
else
    mkdir -p "$KNOWLEDGE_DIR" && cd "$KNOWLEDGE_DIR"
    git init

    mkdir -p convention/naming decision/arch bug/api

    cat > convention/naming/snake-case.md << 'EOF'
---
tags: [convention, naming]
---
Use snake_case for all Python identifiers and database column names.

Matches Postgres schema naming convention and avoids mixed casing
inconsistencies between ORM models and raw SQL queries.
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

    git add -A && git commit -m "Initial knowledge base"
    gh repo create "$REPO_NAME" --private --source=. --push
fi

# --- 2. Create Demo Project ---

mkdir -p "$DEMO_DIR" && cd "$DEMO_DIR"

# --- 3. Initialize Lore (non-interactive) ---

lore init --no-levels

# --- 4. Add hierarchy level ---

lore config add-level \
  --level 1 \
  --name team \
  --repo github.com/itdove/lore-demo-knowledge \
  --branch main \
  --writable \
  --description "Store here when knowledge applies to all projects this team works on: shared bug patterns, team conventions, cross-project decisions"

# --- 5. Configure global settings ---

lore config set lore.search.embedding_provider ollama
lore config set lore.search.embedding_model nomic-embed-text
lore config set lore.search.min_similarity 0.3
lore config set lore.llm.provider ollama
lore config set lore.llm.model phi4-mini

# --- 6. First sync ---

lore sync --force

echo ""
echo "============================================================"
echo "Demo setup complete!"
echo ""
echo "Knowledge repo: $KNOWLEDGE_DIR"
echo "Demo project:   $DEMO_DIR"
echo "Global config:  ~/.config/lore/config.json"
echo ""
echo "Next steps:"
echo "  cd $DEMO_DIR"
echo "  lore search 'jwt'"
echo "  lore dashboard"
echo "============================================================"
