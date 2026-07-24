from lore.sync.state import RepoSyncState, SyncStateManager


def test_load_empty(tmp_path):
    mgr = SyncStateManager(tmp_path / "sync-state.json")
    assert mgr.load() == {}


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "sync-state.json"
    mgr = SyncStateManager(path)
    states = {
        "abc123": RepoSyncState(
            repo="github.com/org/k",
            branch="main",
            last_commit="deadbeef",
            last_sync="2026-01-01T00:00:00",
            file_hashes={"topic/a.md": "sha256:abc"},
        )
    }
    mgr.save(states)
    loaded = mgr.load()
    assert "abc123" in loaded
    s = loaded["abc123"]
    assert s.repo == "github.com/org/k"
    assert s.branch == "main"
    assert s.last_commit == "deadbeef"
    assert s.file_hashes == {"topic/a.md": "sha256:abc"}


def test_load_corrupted_file(tmp_path):
    path = tmp_path / "sync-state.json"
    path.write_text("not json", encoding="utf-8")
    mgr = SyncStateManager(path)
    assert mgr.load() == {}
