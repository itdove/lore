#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Lore Demo Cleanup Script
# Removes everything created by create-demo-config.sh
#
# Usage: ./delete-demo-config.sh [GITHUB_USER]
#   GITHUB_USER defaults to your GitHub username (via gh api)
# ============================================================

GITHUB_USER="${1:-$(gh api user --jq .login 2>/dev/null || echo "")}"
if [ -z "$GITHUB_USER" ]; then
    echo "ERROR: Could not detect GitHub username. Pass it as argument: $0 <username>"
    exit 1
fi

DEMO_DIR=~/development/ai/lore-demo
DEMO_REPO_NAME=lore-demo
TEAM_KNOWLEDGE_DIR=~/development/ai/lore-demo-team-knowledge
TEAM_REPO_NAME=lore-demo-team-knowledge
DOCS_DIR=~/development/ai/lore-demo-docs

echo "============================================================"
echo "This will PERMANENTLY DELETE:"
echo ""
echo "  Local directories:"
echo "    $DEMO_DIR"
echo "    $TEAM_KNOWLEDGE_DIR"
echo "    $DOCS_DIR"
echo "    ~/.config/lore"
echo "    ~/.local/share/lore"
echo "    ~/.local/state/lore"
echo "    ~/.cache/lore"
echo ""
echo "  GitHub repos:"
echo "    $GITHUB_USER/$DEMO_REPO_NAME"
echo "    $GITHUB_USER/$TEAM_REPO_NAME"
echo ""
echo "  Claude settings:"
echo "    Remove 'lore' from enabledMcpjsonServers"
echo "============================================================"
echo ""
read -p "Are you sure? Type 'yes' to confirm: " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

set -x

# 1. Remove demo project (includes .mcp.json, .claude/settings.json, .lore/)
rm -rf "$DEMO_DIR"

# 2. Remove team knowledge repo local clone and docs repo
rm -rf "$TEAM_KNOWLEDGE_DIR"
rm -rf "$DOCS_DIR"

# 3. Delete GitHub repo (and any PR branches created during demo)
gh repo delete "$GITHUB_USER/$DEMO_REPO_NAME" --yes 2>/dev/null || echo "GitHub repo $DEMO_REPO_NAME not found or already deleted"
gh repo delete "$GITHUB_USER/$TEAM_REPO_NAME" --yes 2>/dev/null || echo "GitHub repo $TEAM_REPO_NAME not found or already deleted"

# 4. Remove lore global config, database, cache, and state
rm -rf ~/.config/lore
rm -rf ~/.local/share/lore
rm -rf ~/.local/state/lore
rm -rf ~/.cache/lore

# 5. Remove lore from enabledMcpjsonServers in global Claude settings
python3 -c "
import json; from pathlib import Path
p = Path.home() / '.claude' / 'settings.json'
if p.exists():
    d = json.loads(p.read_text())
    servers = d.get('enabledMcpjsonServers', [])
    if 'lore' in servers:
        servers.remove('lore')
        p.write_text(json.dumps(d, indent=2) + '\n')
        print('Removed lore from enabledMcpjsonServers')
    else:
        print('lore not in enabledMcpjsonServers')
"

set +x

echo ""
echo "============================================================"
echo "Cleanup complete. Verify:"
echo ""
ls "$DEMO_DIR" 2>/dev/null || echo "  demo project: cleaned"
ls "$TEAM_KNOWLEDGE_DIR" 2>/dev/null || echo "  team knowledge repo: cleaned"
ls "$DOCS_DIR" 2>/dev/null || echo "  docs repo: cleaned"
gh repo view "$GITHUB_USER/$DEMO_REPO_NAME" 2>/dev/null || echo "  GitHub repo $DEMO_REPO_NAME: cleaned"
gh repo view "$GITHUB_USER/$TEAM_REPO_NAME" 2>/dev/null || echo "  GitHub repo $TEAM_REPO_NAME: cleaned"
ls ~/.config/lore 2>/dev/null || echo "  global config: cleaned"
ls ~/.local/share/lore 2>/dev/null || echo "  database: cleaned"
ls ~/.cache/lore 2>/dev/null || echo "  cache: cleaned"
echo "============================================================"
