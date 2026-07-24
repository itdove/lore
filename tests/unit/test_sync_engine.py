import json
from unittest import mock

import pytest

from lore.store.base import KnowledgeEntry
from lore.store.sqlite import SQLiteStore, create_schema
from lore.sync.engine import SyncEngine
from lore.sync.git import GitRepoManager
from lore.sync.log import SyncLogWriter
from lore.sync.state import SyncStateManager


@pytest.fixture
def store():
    conn = create_schema(":memory:")
    return SQLiteStore(conn)


@pytest.fixture
def sync_env(tmp_path, store):
    cache = tmp_path / "cache"
    state = tmp_path / "state"
    cache.mkdir(exist_ok=True)
    state.mkdir(exist_ok=True)

    git_mgr = GitRepoManager(cache)
    state_mgr = SyncStateManager(state / "sync-state.json")
    log_writer = SyncLogWriter(state / "sync.md")
    engine = SyncEngine(store, git_mgr, state_mgr, log_writer)

    return {
        "engine": engine,
        "store": store,
        "cache": cache,
        "state": state,
        "state_mgr": state_mgr,
        "git_mgr": git_mgr,
    }


def _setup_repo(cache_dir, repo, branch, files):
    """Create a fake repo directory with markdown files."""
    repo_hash = GitRepoManager.repo_dir_hash(repo, branch)
    repo_path = cache_dir / repo_hash
    repo_path.mkdir(parents=True, exist_ok=True)
    for rel_path, content in files.items():
        f = repo_path / rel_path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
    return repo_path


def _mock_project_config(hierarchy):
    """Return a mock get_project_config that returns given hierarchy."""
    from lore.config.models import HierarchyLevel, ProjectConfig

    levels = [HierarchyLevel(**h) for h in hierarchy]
    cfg = ProjectConfig(hierarchy=levels)
    return mock.patch("lore.sync.engine.get_project_config", return_value=cfg)


def _mock_clone_or_pull(git_mgr, sha="abc123"):
    """Mock clone_or_pull to return a fixed SHA without running git."""
    return mock.patch.object(git_mgr, "clone_or_pull", return_value=sha)


# --- Core sync tests ---


def test_sync_insert_new_entries(sync_env):
    repo = "github.com/org/k"
    branch = "main"
    _setup_repo(
        sync_env["cache"],
        repo,
        branch,
        {
            "convention/naming/snake-case.md": (
                "---\ntags: [python]\n---\nUse snake_case.\n"
            )
        },
    )
    hierarchy = [{"level": 1, "repo": repo, "branch": branch, "name": "team"}]

    with _mock_project_config(hierarchy), _mock_clone_or_pull(sync_env["git_mgr"]):
        result = sync_env["engine"].sync_all(["/fake/project"])

    assert result.created == 1
    assert result.updated == 0
    entry = sync_env["store"].get("convention:naming:snake-case")
    assert entry is not None
    assert entry.value == "Use snake_case.\n"
    assert entry.tags == "python"
    assert entry.level == 1
    assert entry.level_name == "team"
    assert entry.ingested_from == "git"
    assert entry.repo_url == repo
    assert entry.repo_branch == branch


def test_sync_update_changed_entry(sync_env):
    repo = "github.com/org/k"
    branch = "main"
    _setup_repo(
        sync_env["cache"],
        repo,
        branch,
        {"topic/a.md": "---\ntags: [x]\n---\nOriginal.\n"},
    )
    hierarchy = [{"level": 1, "repo": repo, "branch": branch}]

    with _mock_project_config(hierarchy), _mock_clone_or_pull(sync_env["git_mgr"]):
        sync_env["engine"].sync_all(["/fake"])

    _setup_repo(
        sync_env["cache"],
        repo,
        branch,
        {"topic/a.md": "---\ntags: [y]\n---\nUpdated.\n"},
    )

    with (
        _mock_project_config(hierarchy),
        _mock_clone_or_pull(sync_env["git_mgr"], sha="def456"),
    ):
        result = sync_env["engine"].sync_all(["/fake"])

    assert result.updated == 1
    entry = sync_env["store"].get("topic:a")
    assert entry.value == "Updated.\n"
    assert entry.tags == "y"


def test_sync_skip_unchanged(sync_env):
    repo = "github.com/org/k"
    branch = "main"
    content = "---\ntags: [x]\n---\nStable.\n"
    _setup_repo(sync_env["cache"], repo, branch, {"topic/a.md": content})
    hierarchy = [{"level": 1, "repo": repo, "branch": branch}]

    with _mock_project_config(hierarchy), _mock_clone_or_pull(sync_env["git_mgr"]):
        r1 = sync_env["engine"].sync_all(["/fake"])

    with _mock_project_config(hierarchy), _mock_clone_or_pull(sync_env["git_mgr"]):
        r2 = sync_env["engine"].sync_all(["/fake"])

    assert r1.created == 1
    assert r2.created == 0
    assert r2.updated == 0


def test_sync_delete_removed_file(sync_env):
    repo = "github.com/org/k"
    branch = "main"
    _setup_repo(
        sync_env["cache"],
        repo,
        branch,
        {
            "topic/a.md": "A.\n",
            "topic/b.md": "B.\n",
        },
    )
    hierarchy = [{"level": 1, "repo": repo, "branch": branch}]

    with _mock_project_config(hierarchy), _mock_clone_or_pull(sync_env["git_mgr"]):
        sync_env["engine"].sync_all(["/fake"])

    assert sync_env["store"].get("topic:a") is not None
    assert sync_env["store"].get("topic:b") is not None

    repo_path = sync_env["git_mgr"].repo_path(repo, branch)
    (repo_path / "topic" / "b.md").unlink()

    with (
        _mock_project_config(hierarchy),
        _mock_clone_or_pull(sync_env["git_mgr"], sha="new"),
    ):
        result = sync_env["engine"].sync_all(["/fake"])

    assert result.deleted == 1
    assert sync_env["store"].get("topic:b") is None

    entry_a = sync_env["store"].get("topic:a")
    assert entry_a is not None

    rows = (
        sync_env["store"]
        ._conn.execute(
            "SELECT action FROM knowledge_history WHERE action = 'synced_out'"
        )
        .fetchall()
    )
    assert len(rows) >= 1


def test_sync_provenance_set(sync_env):
    repo = "github.com/org/k"
    branch = "main"
    _setup_repo(
        sync_env["cache"],
        repo,
        branch,
        {"topic/entry.md": "---\ntags: [x]\n---\nBody.\n"},
    )
    hierarchy = [{"level": 1, "repo": repo, "branch": branch}]

    with (
        _mock_project_config(hierarchy),
        _mock_clone_or_pull(sync_env["git_mgr"], sha="abc123"),
    ):
        sync_env["engine"].sync_all(["/fake"])

    entry = sync_env["store"].get("topic:entry")
    assert entry.ingested_from == "git"
    prov = json.loads(entry.provenance)
    assert prov["commit_sha"] == "abc123"
    assert prov["file_path"] == "topic/entry.md"
    assert prov["content_hash"].startswith("sha256:")


def test_sync_key_from_path(sync_env):
    repo = "github.com/org/k"
    branch = "main"
    _setup_repo(
        sync_env["cache"],
        repo,
        branch,
        {"convention/naming/snake-case.md": "Body.\n"},
    )
    hierarchy = [{"level": 1, "repo": repo, "branch": branch}]

    with _mock_project_config(hierarchy), _mock_clone_or_pull(sync_env["git_mgr"]):
        sync_env["engine"].sync_all(["/fake"])

    assert sync_env["store"].get("convention:naming:snake-case") is not None


def test_sync_promotion_cleanup(sync_env):
    sync_env["store"].store(KnowledgeEntry(key="topic:a", value="individual", level=0))

    repo = "github.com/org/k"
    branch = "main"
    _setup_repo(sync_env["cache"], repo, branch, {"topic/a.md": "Shared version.\n"})
    hierarchy = [{"level": 1, "repo": repo, "branch": branch}]

    with _mock_project_config(hierarchy), _mock_clone_or_pull(sync_env["git_mgr"]):
        result = sync_env["engine"].sync_all(["/fake"])

    assert result.promoted == 1
    entries = sync_env["store"].list_entries()
    assert len(entries) == 1
    assert entries[0].level == 1


def test_sync_promotion_preserves_unmatched(sync_env):
    sync_env["store"].store(
        KnowledgeEntry(key="topic:individual", value="mine", level=0)
    )

    repo = "github.com/org/k"
    branch = "main"
    _setup_repo(sync_env["cache"], repo, branch, {"topic/shared.md": "Shared.\n"})
    hierarchy = [{"level": 1, "repo": repo, "branch": branch}]

    with _mock_project_config(hierarchy), _mock_clone_or_pull(sync_env["git_mgr"]):
        sync_env["engine"].sync_all(["/fake"])

    assert sync_env["store"].get("topic:individual") is not None
    assert sync_env["store"].get("topic:shared") is not None


def test_sync_locked_entry_preserved(sync_env):
    repo = "github.com/org/k"
    branch = "main"
    _setup_repo(
        sync_env["cache"],
        repo,
        branch,
        {"topic/locked.md": "---\nlock: true\n---\nLocked content.\n"},
    )
    hierarchy = [{"level": 1, "repo": repo, "branch": branch}]

    with _mock_project_config(hierarchy), _mock_clone_or_pull(sync_env["git_mgr"]):
        sync_env["engine"].sync_all(["/fake"])

    entry = sync_env["store"].get("topic:locked")
    assert entry.locked is True


def test_sync_tags_stored(sync_env):
    repo = "github.com/org/k"
    branch = "main"
    _setup_repo(
        sync_env["cache"],
        repo,
        branch,
        {"topic/tagged.md": "---\ntags: [security, api, compliance]\n---\nBody.\n"},
    )
    hierarchy = [{"level": 1, "repo": repo, "branch": branch}]

    with _mock_project_config(hierarchy), _mock_clone_or_pull(sync_env["git_mgr"]):
        sync_env["engine"].sync_all(["/fake"])

    entry = sync_env["store"].get("topic:tagged")
    assert entry.tags == "security,api,compliance"


def test_sync_multiple_repos(sync_env):
    repo1 = "github.com/org/team"
    repo2 = "github.com/org/company"
    _setup_repo(sync_env["cache"], repo1, "main", {"topic/a.md": "Team rule.\n"})
    _setup_repo(sync_env["cache"], repo2, "main", {"topic/b.md": "Company rule.\n"})
    hierarchy = [
        {"level": 1, "repo": repo1, "branch": "main", "name": "team"},
        {"level": 2, "repo": repo2, "branch": "main", "name": "company"},
    ]

    with (
        _mock_project_config(hierarchy),
        mock.patch.object(sync_env["git_mgr"], "clone_or_pull", return_value="sha"),
    ):
        result = sync_env["engine"].sync_all(["/fake"])

    assert result.created == 2
    a = sync_env["store"].get("topic:a")
    b = sync_env["store"].get("topic:b")
    assert a.level == 1
    assert b.level == 2


def test_sync_idempotent(sync_env):
    repo = "github.com/org/k"
    branch = "main"
    content = "---\ntags: [x]\n---\nStable.\n"
    _setup_repo(sync_env["cache"], repo, branch, {"topic/a.md": content})
    hierarchy = [{"level": 1, "repo": repo, "branch": branch}]

    with _mock_project_config(hierarchy), _mock_clone_or_pull(sync_env["git_mgr"]):
        r1 = sync_env["engine"].sync_all(["/fake"])

    with _mock_project_config(hierarchy), _mock_clone_or_pull(sync_env["git_mgr"]):
        r2 = sync_env["engine"].sync_all(["/fake"])

    assert r1.created == 1
    assert r2.created == 0
    assert r2.updated == 0
    assert r2.deleted == 0

    entries = sync_env["store"].list_entries()
    assert len(entries) == 1


def test_sync_log_written(sync_env):
    repo = "github.com/org/k"
    branch = "main"
    _setup_repo(sync_env["cache"], repo, branch, {"topic/a.md": "Content.\n"})
    hierarchy = [{"level": 1, "repo": repo, "branch": branch}]

    with _mock_project_config(hierarchy), _mock_clone_or_pull(sync_env["git_mgr"]):
        sync_env["engine"].sync_all(["/fake"])

    log_path = sync_env["state"] / "sync.md"
    assert log_path.exists()
    log_content = log_path.read_text()
    assert "## Sync" in log_content
    assert "**Created:** 1" in log_content


def test_sync_error_continues(sync_env):
    from lore.sync.git import SyncError

    repo1 = "github.com/org/bad"
    repo2 = "github.com/org/good"
    _setup_repo(sync_env["cache"], repo2, "main", {"topic/a.md": "Good.\n"})
    hierarchy = [
        {"level": 1, "repo": repo1, "branch": "main"},
        {"level": 2, "repo": repo2, "branch": "main"},
    ]

    def side_effect(repo, branch):
        if repo == repo1:
            raise SyncError("clone failed")
        return "sha"

    with (
        _mock_project_config(hierarchy),
        mock.patch.object(
            sync_env["git_mgr"], "clone_or_pull", side_effect=side_effect
        ),
    ):
        result = sync_env["engine"].sync_all(["/fake"])

    assert len(result.errors) == 1
    assert "clone failed" in result.errors[0]
    assert result.created == 1
    assert sync_env["store"].get("topic:a") is not None


def test_sync_result_counts(sync_env):
    repo = "github.com/org/k"
    branch = "main"
    _setup_repo(
        sync_env["cache"],
        repo,
        branch,
        {
            "topic/a.md": "A.\n",
            "topic/b.md": "B.\n",
        },
    )
    hierarchy = [{"level": 1, "repo": repo, "branch": branch}]

    with _mock_project_config(hierarchy), _mock_clone_or_pull(sync_env["git_mgr"]):
        r1 = sync_env["engine"].sync_all(["/fake"])

    assert r1.created == 2
    assert r1.updated == 0
    assert r1.deleted == 0

    _setup_repo(
        sync_env["cache"],
        repo,
        branch,
        {"topic/a.md": "A updated.\n"},
    )
    repo_path = sync_env["git_mgr"].repo_path(repo, branch)
    (repo_path / "topic" / "b.md").unlink()

    with (
        _mock_project_config(hierarchy),
        _mock_clone_or_pull(sync_env["git_mgr"], sha="new"),
    ):
        r2 = sync_env["engine"].sync_all(["/fake"])

    assert r2.created == 0
    assert r2.updated == 1
    assert r2.deleted == 1


# --- Conflict detection during sync ---


def test_sync_conflict_detected(sync_env):
    """Same key at different levels → both stored with conflict fields."""
    org_repo = "github.com/org/shared"
    team_repo = "github.com/team/shared"
    _setup_repo(
        sync_env["cache"], org_repo, "main", {"naming/snake.md": "use snake_case\n"}
    )
    _setup_repo(
        sync_env["cache"], team_repo, "main", {"naming/snake.md": "use camelCase\n"}
    )
    hierarchy = [
        {"level": 1, "repo": org_repo, "branch": "main", "name": "org"},
        {"level": 3, "repo": team_repo, "branch": "main", "name": "team"},
    ]

    with _mock_project_config(hierarchy), _mock_clone_or_pull(sync_env["git_mgr"]):
        result = sync_env["engine"].sync_all(["/fake"])

    assert result.conflicts >= 1
    assert result.created == 2

    org_entry = sync_env["store"].get_by_key_and_level("naming:snake", 1)
    team_entry = sync_env["store"].get_by_key_and_level("naming:snake", 3)
    assert org_entry is not None
    assert team_entry is not None
    assert team_entry.conflict_status == "active"
    assert org_entry.conflict_status == "overridden"
    assert team_entry.conflict_with == org_entry.id
    assert org_entry.conflict_with == team_entry.id


def test_sync_locked_blocks_lower(sync_env):
    """Locked org entry blocks team entry from being stored."""
    org_repo = "github.com/org/shared"
    team_repo = "github.com/team/shared"
    _setup_repo(
        sync_env["cache"],
        org_repo,
        "main",
        {"naming/snake.md": "---\nlock: true\n---\nuse snake_case\n"},
    )
    _setup_repo(
        sync_env["cache"],
        team_repo,
        "main",
        {"naming/snake.md": "use camelCase\n"},
    )
    hierarchy = [
        {"level": 1, "repo": org_repo, "branch": "main", "name": "org"},
        {"level": 3, "repo": team_repo, "branch": "main", "name": "team"},
    ]

    with _mock_project_config(hierarchy), _mock_clone_or_pull(sync_env["git_mgr"]):
        result = sync_env["engine"].sync_all(["/fake"])

    assert result.blocked == 1
    assert result.created == 1

    org_entry = sync_env["store"].get_by_key_and_level("naming:snake", 1)
    team_entry = sync_env["store"].get_by_key_and_level("naming:snake", 3)
    assert org_entry is not None
    assert team_entry is None


def test_sync_conflict_cleared_on_delete(sync_env):
    """File removed from repo → counterpart's conflict cleared."""
    org_repo = "github.com/org/shared"
    team_repo = "github.com/team/shared"
    _setup_repo(
        sync_env["cache"], org_repo, "main", {"naming/snake.md": "use snake_case\n"}
    )
    _setup_repo(
        sync_env["cache"], team_repo, "main", {"naming/snake.md": "use camelCase\n"}
    )
    hierarchy = [
        {"level": 1, "repo": org_repo, "branch": "main", "name": "org"},
        {"level": 3, "repo": team_repo, "branch": "main", "name": "team"},
    ]

    with _mock_project_config(hierarchy), _mock_clone_or_pull(sync_env["git_mgr"]):
        sync_env["engine"].sync_all(["/fake"])

    org_entry = sync_env["store"].get_by_key_and_level("naming:snake", 1)
    assert org_entry.conflict_with is not None

    repo_path = sync_env["git_mgr"].repo_path(org_repo, "main")
    (repo_path / "naming" / "snake.md").unlink()

    with (
        _mock_project_config(hierarchy),
        _mock_clone_or_pull(sync_env["git_mgr"], sha="new"),
    ):
        result = sync_env["engine"].sync_all(["/fake"])

    assert result.deleted == 1
    team_entry = sync_env["store"].get_by_key_and_level("naming:snake", 3)
    assert team_entry.conflict_with is None
    assert team_entry.conflict_status is None


def test_sync_conflict_higher_level_wins(sync_env):
    """Team (level=3) wins over org (level=1) for non-locked entries."""
    org_repo = "github.com/org/shared"
    team_repo = "github.com/team/shared"
    _setup_repo(sync_env["cache"], org_repo, "main", {"api/rate.md": "100 req/min\n"})
    _setup_repo(sync_env["cache"], team_repo, "main", {"api/rate.md": "500 req/min\n"})
    hierarchy = [
        {"level": 1, "repo": org_repo, "branch": "main", "name": "org"},
        {"level": 3, "repo": team_repo, "branch": "main", "name": "team"},
    ]

    with _mock_project_config(hierarchy), _mock_clone_or_pull(sync_env["git_mgr"]):
        sync_env["engine"].sync_all(["/fake"])

    org_entry = sync_env["store"].get_by_key_and_level("api:rate", 1)
    team_entry = sync_env["store"].get_by_key_and_level("api:rate", 3)
    assert team_entry.conflict_status == "active"
    assert org_entry.conflict_status == "overridden"
