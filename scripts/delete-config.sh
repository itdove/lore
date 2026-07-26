set -x

# 1. Remove demo project (includes .mcp.json, .claude/settings.json, .lore/)
rm -rf ~/development/ai/lore-demo

# 2. Remove knowledge repo local clone
rm -rf ~/development/ai/lore-demo-knowledge

# 3. Delete GitHub repo (and any PR branches created during demo)
gh repo delete itdove/lore-demo-knowledge --yes

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
