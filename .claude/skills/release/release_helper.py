#!/usr/bin/env python3
"""
Project-Agnostic Release Helper

Automation utilities for release management:
- Auto-detects version files in your project
- Supports multiple project types (Python, Node.js, etc.)
- Updates CHANGELOG.md with proper formatting
- Validates version consistency
- Calculates next version based on release type

Adapted from ai-guardian's release skill.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


class VersionFile:
    """Represents a file containing version information."""

    def __init__(self, path: Path, pattern: str, description: str = ""):
        self.path = path
        self.pattern = pattern
        self.description = description

    def read_version(self) -> str | None:
        try:
            if not self.path.exists():
                return None
            content = self.path.read_text()
            regex_pattern = self.pattern.replace("{version}", r"([^\"']+)")
            match = re.search(regex_pattern, content, re.MULTILINE)
            return match.group(1) if match else None
        except Exception as e:
            print(f"Error reading {self.path}: {e}", file=sys.stderr)
            return None

    def write_version(self, new_version: str) -> bool:
        try:
            if not self.path.exists():
                print(f"Warning: {self.path} does not exist", file=sys.stderr)
                return False
            content = self.path.read_text()
            regex_pattern = self.pattern.replace("{version}", r"[^\"']+")
            new_content = self.pattern.replace("{version}", new_version)
            updated = re.sub(regex_pattern, new_content, content, count=1, flags=re.MULTILINE)
            self.path.write_text(updated)
            return True
        except Exception as e:
            print(f"Error writing {self.path}: {e}", file=sys.stderr)
            return False


class ReleaseHelper:
    """Project-agnostic release helper with auto-detection."""

    VERSION_PATTERNS = [
        {"glob": "**/pyproject.toml", "pattern": 'version = "{version}"', "description": "Python project metadata (pyproject.toml)"},
        {"glob": "**/setup.py", "pattern": 'version="{version}"', "description": "Python setup.py"},
        {"glob": "**/__init__.py", "pattern": '__version__ = "{version}"', "description": "Python package __init__.py"},
        {"glob": "**/__version__.py", "pattern": '__version__ = "{version}"', "description": "Python __version__.py"},
        {"glob": "**/package.json", "pattern": '"version": "{version}"', "description": "Node.js package.json"},
        {"glob": "**/VERSION", "pattern": "{version}", "description": "VERSION file"},
    ]

    def __init__(self, repo_path: str = ".", config_file: str = ".release-config.json"):
        self.repo_path = Path(repo_path).resolve()
        self.config_path = self.repo_path / config_file
        self.changelog_path = self.repo_path / "CHANGELOG.md"
        self.config = self._load_or_detect_config()
        self.version_files = self._create_version_files()

    def _load_or_detect_config(self) -> dict[str, Any]:
        if self.config_path.exists():
            try:
                config = json.loads(self.config_path.read_text())
                print(f"Loaded configuration from {self.config_path.name}", file=sys.stderr)
                return config
            except Exception as e:
                print(f"Warning: Could not load {self.config_path}: {e}", file=sys.stderr)

        print("Auto-detecting version files...", file=sys.stderr)
        detected = self._auto_detect_version_files()

        if not detected:
            print("No version files auto-detected. Please create .release-config.json", file=sys.stderr)
            return {"version_files": [], "changelog": "CHANGELOG.md"}

        config = {"version_files": detected, "changelog": "CHANGELOG.md"}
        self._save_config(config)
        return config

    def _auto_detect_version_files(self) -> list[dict[str, str]]:
        detected = []
        for pattern_def in self.VERSION_PATTERNS:
            for file_path in self.repo_path.glob(pattern_def["glob"]):
                try:
                    rel_path = file_path.relative_to(self.repo_path)
                except ValueError:
                    continue
                if any(part.startswith(".") for part in rel_path.parts[:-1]):
                    continue
                if any(part in ["node_modules", "venv", "__pycache__", "dist", "build"] for part in rel_path.parts):
                    continue
                test_file = VersionFile(file_path, pattern_def["pattern"])
                version = test_file.read_version()
                if version:
                    detected.append({
                        "path": str(rel_path),
                        "pattern": pattern_def["pattern"],
                        "description": pattern_def["description"],
                        "detected_version": version,
                    })
                    print(f"  Found: {rel_path} (version: {version})", file=sys.stderr)
        return detected

    def _save_config(self, config: dict[str, Any]) -> bool:
        try:
            self.config_path.write_text(json.dumps(config, indent=2))
            print(f"Saved configuration to {self.config_path.name}", file=sys.stderr)
            return True
        except Exception as e:
            print(f"Warning: Could not save config: {e}", file=sys.stderr)
            return False

    def _create_version_files(self) -> list[VersionFile]:
        return [
            VersionFile(self.repo_path / vf["path"], vf["pattern"], vf.get("description", ""))
            for vf in self.config.get("version_files", [])
        ]

    def get_current_version(self) -> tuple[str | None, bool]:
        if not self.version_files:
            print("Error: No version files configured", file=sys.stderr)
            return None, False

        versions = {}
        for vf in self.version_files:
            ver = vf.read_version()
            if ver:
                versions[str(vf.path.relative_to(self.repo_path))] = ver

        if not versions:
            return None, False

        unique = set(versions.values())
        all_match = len(unique) == 1

        if not all_match:
            print("Version mismatch detected:", file=sys.stderr)
            for file, ver in versions.items():
                print(f"  {file}: {ver}", file=sys.stderr)

        return (list(unique)[0] if all_match else None), all_match

    def update_version(self, new_version: str) -> bool:
        if not self.version_files:
            print("Error: No version files configured", file=sys.stderr)
            return False
        for vf in self.version_files:
            if not vf.write_version(new_version):
                return False
        version, all_match = self.get_current_version()
        if version == new_version and all_match:
            print(f"Version updated to {new_version} in all files", file=sys.stderr)
            return True
        print("Error: Version update verification failed", file=sys.stderr)
        return False

    def calculate_next_version(self, current_version: str, release_type: str) -> str | None:
        base_version = re.sub(r"-dev|-test\d*", "", current_version)
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", base_version)
        if not match:
            print(f"Error: Invalid version format: {base_version}", file=sys.stderr)
            return None
        major, minor, patch = map(int, match.groups())
        if release_type == "major":
            return f"{major + 1}.0.0"
        elif release_type == "minor":
            return f"{major}.{minor + 1}.0"
        elif release_type == "patch":
            return f"{major}.{minor}.{patch + 1}"
        elif release_type == "test":
            return f"{major}.{minor}.{patch}-test1"
        print(f"Error: Invalid release type: {release_type}", file=sys.stderr)
        return None

    def update_changelog(self, version: str, date: str | None = None) -> bool:
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        changelog_file = self.repo_path / self.config.get("changelog", "CHANGELOG.md")
        if not changelog_file.exists():
            print(f"Warning: {changelog_file.name} not found", file=sys.stderr)
            return False
        try:
            content = changelog_file.read_text()
            if "## [Unreleased]" not in content:
                print("Warning: No [Unreleased] section found in CHANGELOG", file=sys.stderr)
                return False
            unreleased_pattern = r"## \[Unreleased\]\s*(.*?)(?=## \[|$)"
            unreleased_match = re.search(unreleased_pattern, content, re.DOTALL)
            if not unreleased_match:
                print("Warning: Could not parse Unreleased section", file=sys.stderr)
                return False
            unreleased_content = unreleased_match.group(1).strip()
            if not unreleased_content or unreleased_content.isspace():
                print("Warning: Unreleased section is empty", file=sys.stderr)
                return False
            version_section = f"## [{version}] - {date}\n\n{unreleased_content}\n\n"
            new_content = re.sub(
                r"## \[Unreleased\]\s*.*?(?=## \[|$)",
                f"## [Unreleased]\n\n{version_section}",
                content, count=1, flags=re.DOTALL,
            )
            repo_url_match = re.search(
                r"\[Unreleased\]: (https://github\.com/[^/]+/[^/]+)/compare/v([^.]+\.[^.]+\.[^.]+)\.\.\.HEAD",
                new_content,
            )
            if repo_url_match:
                repo_url = repo_url_match.group(1)
                new_content = re.sub(
                    r"\[Unreleased\]: .*?\n",
                    f"[Unreleased]: {repo_url}/compare/v{version}...HEAD\n",
                    new_content, count=1,
                )
                new_version_link = f"[{version}]: {repo_url}/releases/tag/v{version}\n"
                new_content = re.sub(
                    r"(\[Unreleased\]: .*?\n)",
                    f"\\1{new_version_link}",
                    new_content, count=1,
                )
            changelog_file.write_text(new_content)
            print(f"Updated CHANGELOG.md for version {version}", file=sys.stderr)
            return True
        except Exception as e:
            print(f"Error updating CHANGELOG: {e}", file=sys.stderr)
            return False

    def validate_prerequisites(self, release_type: str = "regular") -> tuple[bool, list[str]]:
        errors = []
        if not self.version_files:
            errors.append("No version files configured")
        else:
            for vf in self.version_files:
                if not vf.path.exists():
                    errors.append(f"{vf.path.relative_to(self.repo_path)} not found")
        changelog_file = self.repo_path / self.config.get("changelog", "CHANGELOG.md")
        if not changelog_file.exists():
            errors.append(f"{changelog_file.name} not found")
        if errors:
            return False, errors
        version, all_match = self.get_current_version()
        if not all_match:
            errors.append("Version mismatch between files")
        if release_type == "regular":
            try:
                content = changelog_file.read_text()
                if "## [Unreleased]" not in content:
                    errors.append("CHANGELOG missing [Unreleased] section")
                else:
                    unreleased_pattern = r"## \[Unreleased\]\s*(.*?)(?=## \[|$)"
                    match = re.search(unreleased_pattern, content, re.DOTALL)
                    if match:
                        unreleased_content = match.group(1).strip()
                        if not unreleased_content or unreleased_content.isspace():
                            errors.append("CHANGELOG [Unreleased] section is empty")
            except Exception as e:
                errors.append(f"Error reading CHANGELOG: {e}")
        return len(errors) == 0, errors

    def show_config(self):
        print("\nCurrent Configuration", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print(f"Config file: {self.config_path.name}", file=sys.stderr)
        print(f"Repository: {self.repo_path}", file=sys.stderr)
        print(f"\nVersion files ({len(self.version_files)}):", file=sys.stderr)
        for vf in self.version_files:
            rel_path = vf.path.relative_to(self.repo_path)
            version = vf.read_version()
            print(f"  {rel_path}", file=sys.stderr)
            print(f"    Pattern: {vf.pattern}", file=sys.stderr)
            print(f"    Current: {version}", file=sys.stderr)
            if vf.description:
                print(f"    ({vf.description})", file=sys.stderr)
        print(f"\nChangelog: {self.config.get('changelog', 'CHANGELOG.md')}", file=sys.stderr)
        print("=" * 60, file=sys.stderr)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Project-agnostic release helper")
    parser.add_argument("--repo", default=".", help="Repository path (default: current directory)")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    subparsers.add_parser("show-config", help="Show current configuration")
    subparsers.add_parser("get-version", help="Get current version from all files")

    update_parser = subparsers.add_parser("update-version", help="Update version in all files")
    update_parser.add_argument("version", help="New version (e.g., 1.2.0)")

    calc_parser = subparsers.add_parser("calc-version", help="Calculate next version")
    calc_parser.add_argument("current", help="Current version")
    calc_parser.add_argument("type", choices=["major", "minor", "patch", "test"], help="Release type")

    changelog_parser = subparsers.add_parser("update-changelog", help="Update CHANGELOG.md")
    changelog_parser.add_argument("version", help="Version to release")
    changelog_parser.add_argument("--date", help="Release date (YYYY-MM-DD, default: today)")

    validate_parser = subparsers.add_parser("validate", help="Validate prerequisites")
    validate_parser.add_argument("--type", default="regular", choices=["regular", "hotfix", "test"], help="Release type")

    subparsers.add_parser("detect", help="Re-run auto-detection and update config")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    helper = ReleaseHelper(args.repo)

    if args.command == "show-config":
        helper.show_config()
    elif args.command == "get-version":
        version, all_match = helper.get_current_version()
        if version:
            print(f"Current version: {version}")
            print(f"All files match: {all_match}")
            sys.exit(0 if all_match else 1)
        else:
            print("Could not determine version", file=sys.stderr)
            sys.exit(1)
    elif args.command == "update-version":
        sys.exit(0 if helper.update_version(args.version) else 1)
    elif args.command == "calc-version":
        next_version = helper.calculate_next_version(args.current, args.type)
        if next_version:
            print(next_version)
        else:
            sys.exit(1)
    elif args.command == "update-changelog":
        sys.exit(0 if helper.update_changelog(args.version, args.date) else 1)
    elif args.command == "validate":
        valid, errors = helper.validate_prerequisites(args.type)
        if valid:
            print("All prerequisites validated")
        else:
            print("Validation failed:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "detect":
        detected = helper._auto_detect_version_files()
        if detected:
            config = {"version_files": detected, "changelog": "CHANGELOG.md"}
            helper._save_config(config)
            print(f"Detected {len(detected)} version files")
        else:
            print("No version files detected", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
