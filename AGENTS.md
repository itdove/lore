# Agent Instructions for Lore

## General Instructions

**IMPORTANT**: The following instructions apply to the Lore project and MUST be followed when contributing to this codebase.

---

### Git Workflow

**IMPORTANT**: Never commit directly to the `main` branch. Always create a feature branch before making any commits.

#### Creating Branches and Pull Requests

1. **Check if a branch already exists** for this work. If the current branch matches the issue (e.g., the branch name contains the issue number), use it directly — do **not** create a new branch.

2. **If no branch exists**, update main and create one:
   ```bash
   git checkout main
   git pull origin main
   git checkout -b <issue-number>-<short-description>
   ```

3. **Make your changes** and commit them to the branch

4. **Push the branch** to remote:
   ```bash
   git push -u origin <branch-name>
   ```

5. **Create a PR** using the GitHub CLI (`gh`)

---

### Project Structure

```
src/lore/
├── __init__.py
├── config/
│   ├── __init__.py        # Re-exports public API
│   ├── models.py          # Dataclasses (GlobalConfig, ProjectConfig, etc.)
│   ├── loaders.py         # JSON loading, mtime cache, deep merge
│   ├── manager.py         # get_global_config(), get_project_config()
│   └── utils.py           # XDG path helpers
tests/
├── conftest.py            # Autouse isolation fixture
└── unit/
    └── test_config_*.py   # Config module tests
```

### Architecture Patterns

This project adapts patterns from [ai-guardian](https://github.com/itdove/ai-guardian):

- **Config loading**: Mtime-based caching, env var overlays, deep merge (`config/loaders.py`)
- **XDG paths**: `LORE_CONFIG_DIR` > `XDG_CONFIG_HOME/lore` > `~/.config/lore` (`config/utils.py`)
- **Test isolation**: Autouse fixture redirects all paths to `tmp_path`, clears caches (`conftest.py`)
- **ABCs for extensibility**: `StoreBackend`, `GitInterface`, `LLMProvider`, `EmbeddingProvider` (future phases)

### Key Environment Variables

| Variable | Purpose |
|----------|---------|
| `LORE_CONFIG_DIR` | Override config directory (testing) |
| `LORE_DATA_DIR` | Override data directory |
| `LORE_CACHE_DIR` | Override cache directory |
| `LORE_STATE_DIR` | Override state directory |
| `LORE_CONFIG_INLINE` | JSON string overlay for global config |

---

### Testing

**CRITICAL**: All code changes MUST include appropriate tests.

#### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests related to your changes
python -m pytest tests/unit/test_<module>.py -v

# Run tests matching a keyword
python -m pytest -k "test_something" -v

# Run full suite
python -m pytest tests/ -v
```

#### Test Structure

- Place unit tests in `tests/unit/`
- Place integration tests in `tests/integration/`
- Test files: `test_*.py`
- Test functions: `test_*`
- Use pytest fixtures for common setup

#### Test Isolation

The autouse `_isolate_config` fixture in `conftest.py` ensures:
- All `LORE_*_DIR` env vars point to temp directories
- `LORE_CONFIG_INLINE` is cleared
- Config cache is cleared before and after each test
- No test reads the developer's real config files

When adding new config-dependent code, rely on this fixture. Call `_clear_config_cache()` explicitly if you modify config files mid-test.

#### Test Coverage

- Target: >70% code coverage
- Add tests for new features and bug fixes
- Run `python -m pytest --cov=lore --cov-report=term-missing` for coverage reports

---

### Configuration

Lore uses two config files:

1. **Global config** (`~/.config/lore/config.json`) — per-developer, NOT committed
   - Project registry, LLM/store/git provider settings
   - Env var overlay: `LORE_CONFIG_INLINE`

2. **Project config** (`.lore/config.json`) — committed to project repo
   - Hierarchy levels with repo URLs and branches

See issue #2 and `DEVELOPMENT_PLAN.md` for full config specification.

---

### Code Style

- Python 3.10+ (use `from __future__ import annotations` for forward refs)
- Dataclasses for data models (no Pydantic in MVP)
- No type: ignore comments without explanation
- Prefer `pathlib.Path` over `os.path`
- Use `json` stdlib for config files (no TOML/YAML dependencies in MVP)

### Dependencies

- Keep dependencies minimal for MVP
- No CLI framework (argparse only)
- No web framework until NiceGUI phase
- Dev dependencies: pytest, pytest-cov
