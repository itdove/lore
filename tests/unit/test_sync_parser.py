import hashlib

from lore.sync.parser import parse_markdown, path_to_key, scan_repo

# --- path_to_key ---


def test_path_to_key_simple():
    assert (
        path_to_key("convention/naming/snake-case.md") == "convention:naming:snake-case"
    )


def test_path_to_key_deep_nesting():
    assert path_to_key("a/b/c/d.md") == "a:b:c:d"


def test_path_to_key_markdown_extension():
    assert path_to_key("topic/file.markdown") == "topic:file"


def test_path_to_key_preserves_hyphens():
    assert path_to_key("my-topic/my-file.md") == "my-topic:my-file"


def test_path_to_key_single_file():
    assert path_to_key("standalone.md") == "standalone"


# --- parse_markdown ---


def _write_md(tmp_path, rel_path, content):
    p = tmp_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_parse_markdown_with_frontmatter(tmp_path):
    content = (
        "---\nlock: true\ntags: [security, api]\n"
        "created_by: jdoe\nprojects: [svc]\n---\nBody text.\n"
    )
    path = _write_md(tmp_path, "topic/entry.md", content)
    result = parse_markdown(path, tmp_path)
    assert result.key == "topic:entry"
    assert result.value == "Body text.\n"
    assert result.tags == "security,api"
    assert result.locked is True
    assert result.created_by == "jdoe"
    assert result.projects == "svc"
    assert result.file_path == "topic/entry.md"


def test_parse_markdown_no_frontmatter(tmp_path):
    content = "Just some markdown.\n"
    path = _write_md(tmp_path, "plain/file.md", content)
    result = parse_markdown(path, tmp_path)
    assert result.key == "plain:file"
    assert result.value == "Just some markdown.\n"
    assert result.tags is None
    assert result.locked is False
    assert result.created_by is None
    assert result.projects is None


def test_parse_markdown_lock_true(tmp_path):
    content = "---\nlock: true\n---\nLocked.\n"
    path = _write_md(tmp_path, "a/b.md", content)
    result = parse_markdown(path, tmp_path)
    assert result.locked is True


def test_parse_markdown_lock_false_default(tmp_path):
    content = "---\ntags: [x]\n---\nBody.\n"
    path = _write_md(tmp_path, "a/b.md", content)
    result = parse_markdown(path, tmp_path)
    assert result.locked is False


def test_parse_markdown_tags_list(tmp_path):
    content = "---\ntags: [a, b, c]\n---\nBody.\n"
    path = _write_md(tmp_path, "a/b.md", content)
    result = parse_markdown(path, tmp_path)
    assert result.tags == "a,b,c"


def test_parse_markdown_content_hash(tmp_path):
    content = "---\ntags: [x]\n---\nBody.\n"
    path = _write_md(tmp_path, "a/b.md", content)
    result = parse_markdown(path, tmp_path)
    expected = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
    assert result.content_hash == expected


def test_parse_markdown_malformed_yaml(tmp_path):
    content = "---\n: invalid: yaml: [[\n---\nBody.\n"
    path = _write_md(tmp_path, "a/b.md", content)
    result = parse_markdown(path, tmp_path)
    assert result.value == "Body.\n"
    assert result.tags is None


# --- scan_repo ---


def test_scan_repo_finds_md_files(tmp_path):
    _write_md(tmp_path, "topic/a.md", "---\ntags: [x]\n---\nA.\n")
    _write_md(tmp_path, "topic/b.markdown", "B.\n")
    results = scan_repo(tmp_path)
    assert len(results) == 2
    keys = {r.key for r in results}
    assert keys == {"topic:a", "topic:b"}


def test_scan_repo_skips_root_readme(tmp_path):
    _write_md(tmp_path, "README.md", "Root readme.\n")
    _write_md(tmp_path, "topic/entry.md", "Entry.\n")
    results = scan_repo(tmp_path)
    assert len(results) == 1
    assert results[0].key == "topic:entry"


def test_scan_repo_skips_dotfiles(tmp_path):
    _write_md(tmp_path, ".hidden/secret.md", "Secret.\n")
    _write_md(tmp_path, "topic/entry.md", "Entry.\n")
    results = scan_repo(tmp_path)
    assert len(results) == 1
    assert results[0].key == "topic:entry"


def test_scan_repo_skips_lore_yml(tmp_path):
    _write_md(tmp_path, "lore.yml", "config stuff")
    _write_md(tmp_path, "topic/entry.md", "Entry.\n")
    results = scan_repo(tmp_path)
    assert len(results) == 1


def test_scan_repo_includes_nested_readme(tmp_path):
    _write_md(tmp_path, "topic/README.md", "Nested readme.\n")
    results = scan_repo(tmp_path)
    assert len(results) == 1
    assert results[0].key == "topic:README"


def test_scan_repo_empty(tmp_path):
    assert scan_repo(tmp_path) == []
