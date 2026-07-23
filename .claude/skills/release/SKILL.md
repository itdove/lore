---
name: release
description: Automate project release workflow with version management, CHANGELOG updates, and git operations
user-invocable: true
---

# Release Skill

Automates release management following semantic versioning and Keep a Changelog conventions. Works with Python, Node.js, and other project types through automatic version file detection.

## Usage

```bash
/release minor              # Create minor version release (1.1.0 -> 1.2.0)
/release patch              # Create patch version release (1.1.0 -> 1.1.1)
/release major              # Create major version release (1.0.0 -> 2.0.0)
/release hotfix v1.1.0      # Create hotfix from v1.1.0 tag
/release test               # Create test release
```

## Skill Invocation

When invoked with arguments (e.g., `/release minor`), this skill guides you through:

1. **Safety Checks**: Verify prerequisites before starting
2. **Version Management**: Update version in all detected files
3. **CHANGELOG Management**: Update CHANGELOG.md with proper format
4. **Git Operations**: Create branches, commits, and tags
5. **Post-Release Guidance**: Provide checklist for manual steps

## Release Types

### Regular Release (`/release major|minor|patch`)

**Prerequisites**:
- All tests pass on main
- CHANGELOG.md has Unreleased section with changes
- Main branch is up-to-date

**Steps**:
1. Verify prerequisites (clean working directory, tests pass, CHANGELOG updated)
2. Create release branch (e.g., `release-1.2`)
3. Determine new version based on release type
4. Update version in all files (remove `-dev` suffix)
5. Update CHANGELOG.md (move Unreleased to version section with date)
6. Commit changes with proper commit message format
7. Create tag and push
8. Provide post-release checklist

### Hotfix Release (`/release hotfix <tag>`)

**Preferred approach**: If the minor release branch (`release-x.y`) still exists, apply the patch fix there directly instead of creating a separate hotfix branch.

**Steps**:
1. Verify tag exists
2. Check if `release-x.y` branch exists
   - **If yes (preferred)**: Switch to `release-x.y`, apply fix there
   - **If no (fallback)**: Create `hotfix-x.y.z` branch from the specified tag
3. Guide through bug fix implementation
4. Calculate hotfix version (increment patch)
5. Update version in all files
6. Update CHANGELOG.md with patch/hotfix entry
7. Provide instructions for tagging
8. Provide cherry-pick-to-main and cleanup guidance

### Test Release (`/release test`)

**Steps**:
1. Create test release branch
2. Calculate test version (add `-test` suffix)
3. Update version in all files
4. Create test tag (v*-test* pattern)
5. Provide verification steps
6. Provide cleanup instructions

## Version Management

### Auto-Detection

On first use, the skill automatically detects version files by scanning for common patterns:

**Python projects**: `pyproject.toml`, `setup.py`, `__init__.py`
**Node.js projects**: `package.json`
**Generic projects**: `VERSION`, `version.txt`

Configuration saved to `.release-config.json` (add to `.gitignore`).

**CRITICAL**: All detected version files MUST be kept in sync.

**Version Format**:
- Production: `"1.0.0"` (semantic versioning)
- Development: `"1.1.0-dev"` (on main branch)
- Test: `"1.2.0-test1"` (for testing)

**Version Transitions**:
- Regular release: `1.1.0-dev` -> `1.2.0` (remove -dev)
- Hotfix: `1.1.0` -> `1.1.1` (increment patch)
- Test: `1.2.0-dev` -> `1.2.0-test1` (replace -dev with -test1)
- Post-release: `1.2.0` -> `1.3.0-dev` (increment minor, add -dev)

## CHANGELOG.md Format

**Format**: Keep a Changelog (https://keepachangelog.com/)

```markdown
## [Unreleased]

### Added
- New features

### Changed
- Changes to existing functionality

### Fixed
- Bug fixes

## [1.2.0] - 2026-04-08

### Added
- Feature X

[Unreleased]: https://github.com/owner/repo/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/owner/repo/releases/tag/v1.2.0
```

## Commit Message Format

```
<type>: <subject>

<body>

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
```

**Types**: `chore:` (version bumps), `docs:` (CHANGELOG), `fix:` (hotfix), `feat:` (new features)

**Always use HEREDOC** for commit messages:
```bash
git commit -m "$(cat <<'EOF'
chore: bump version to 1.2.0 for release

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

## Safety Checks

**Before starting any release**:
1. Verify git status is clean
2. Verify on correct branch (main for regular, tag for hotfix)
3. Verify tests pass: `python -m pytest`
4. Verify CHANGELOG.md has Unreleased section (regular releases only)
5. Verify versions match between files

## Git Operations

**Branch Naming**:
- Regular release: `release-X.Y`
- Patch fix: Prefer existing `release-X.Y` branch; use `hotfix-X.Y.Z` only when release branch is deleted
- Test release: `release-X.Y-test`

**Tag Naming**:
- Production: `vX.Y.Z` (e.g., `v1.2.0`)
- Test: `vX.Y.Z-testN` (e.g., `v1.2.0-test1`)

**Important**:
- DO NOT push tags automatically — provide command for user to review and push
- DO NOT run destructive operations without confirmation

## Post-Release Checklist

**After creating release tag:**
1. [ ] Push tag: `git push origin vX.Y.Z`
2. [ ] Monitor CI/CD pipeline
3. [ ] Verify package publication (PyPI)
4. [ ] Test installation from package registry
5. [ ] Merge release branch back to main
6. [ ] Bump version to next dev cycle (X.Y+1.0-dev)
7. [ ] Push main branch
8. [ ] (Hotfix only) Cherry-pick fix to main

## Implementation Guidelines

**When user invokes this skill**:

1. **Auto-detect version files** (first run only)
2. **Parse arguments**: Determine release type
3. **Run safety checks**: Verify prerequisites
4. **Calculate new version**: Based on current version and release type
5. **Update version files**: Edit all detected files atomically
6. **Update CHANGELOG**: Move Unreleased to version section with date
7. **Create commits**: Use proper commit message format
8. **Create tag**: Provide tag creation command
9. **Validate**: Ensure versions match between all files

## Configuration

Auto-generated `.release-config.json`:
```json
{
  "version_files": [
    {
      "path": "pyproject.toml",
      "pattern": "version = \"{version}\"",
      "description": "Python project metadata"
    },
    {
      "path": "src/lore/__init__.py",
      "pattern": "__version__ = \"{version}\"",
      "description": "Python package version"
    }
  ],
  "changelog": "CHANGELOG.md"
}
```
