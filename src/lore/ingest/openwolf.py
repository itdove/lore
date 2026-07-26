from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from lore.ingest.base import LoreIngester
from lore.ingest.registry import register
from lore.store.base import KnowledgeEntry, StoreBackend, validate_key

log = logging.getLogger("lore.ingest")

_SECTION_MAP = {
    "User Preferences": "preference",
    "Key Learnings": "learning",
    "Do-Not-Repeat": "do-not-repeat",
    "Decision Log": "decision",
}

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_DATE_PREFIX = re.compile(r"^\[(\d{4}-\d{2}-\d{2})\]\s*")


@register
class OpenWolfIngester(LoreIngester):
    """Ingest knowledge from an OpenWolf .wolf/ directory.

    Reads cerebrum.md (structured learnings/preferences/decisions)
    and buglog.json (bug records with root cause and fix).
    """

    name = "openwolf"
    triggers = frozenset({"hook"})
    review_policy = "pr_based"

    def __init__(self, store: StoreBackend, project_dir: Path) -> None:
        super().__init__(store, project_dir)
        self._wolf_dir = project_dir / ".wolf"

    def detect(self, project_dir: Path) -> bool:
        wolf = project_dir / ".wolf"
        return wolf.is_dir() and (wolf / "cerebrum.md").is_file()

    def extract_delta(self, since: datetime | None = None) -> list[KnowledgeEntry]:
        entries: list[KnowledgeEntry] = []
        entries.extend(self._extract_cerebrum(since))
        entries.extend(self._extract_buglog(since))
        return entries

    def _extract_cerebrum(self, since: datetime | None = None) -> list[KnowledgeEntry]:
        path = self._wolf_dir / "cerebrum.md"
        if not path.exists():
            return []

        text = path.read_text(encoding="utf-8", errors="replace")
        text = _HTML_COMMENT.sub("", text)
        sections = self._parse_sections(text)
        entries: list[KnowledgeEntry] = []

        for section_name, items in sections.items():
            key_prefix = _SECTION_MAP.get(section_name)
            if not key_prefix:
                continue

            for i, item in enumerate(items):
                if not item.strip():
                    continue

                date_match = _DATE_PREFIX.match(item)
                if since and date_match:
                    try:
                        item_date = datetime.fromisoformat(date_match.group(1))
                        if item_date < since:
                            continue
                    except ValueError:
                        pass

                slug = self._slugify(item)
                if not slug:
                    continue

                key = f"{key_prefix}:{slug}"
                if validate_key(key) is not None:
                    log.warning("Skipping invalid key: %s", key)
                    continue

                provenance = json.dumps(
                    {
                        "source": "cerebrum.md",
                        "section": section_name,
                        "item_index": i,
                    }
                )

                entries.append(
                    KnowledgeEntry(
                        key=key,
                        value=item.strip(),
                        level=0,
                        tags=key_prefix,
                        ingested_from="openwolf",
                        provenance=provenance,
                    )
                )

        return entries

    def _extract_buglog(self, since: datetime | None = None) -> list[KnowledgeEntry]:
        path = self._wolf_dir / "buglog.json"
        if not path.exists():
            return []

        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            log.warning("Failed to parse buglog.json")
            return []

        bugs = data.get("bugs", [])
        if not isinstance(bugs, list):
            return []

        entries: list[KnowledgeEntry] = []
        for bug in bugs:
            if not isinstance(bug, dict):
                continue

            bug_id = bug.get("id", "")
            if since and bug.get("timestamp"):
                try:
                    bug_date = datetime.fromisoformat(bug.get("timestamp"))
                    if bug_date < since:
                        continue
                except ValueError:
                    pass

            slug = (
                str(bug_id).strip()
                if bug_id
                else self._slugify(
                    bug.get("error_message", bug.get("root_cause", "unknown"))
                )
            )
            key = f"bug:{slug}"
            if validate_key(key) is not None:
                log.warning("Skipping invalid bug key: %s", key)
                continue

            parts = []
            if bug.get("error_message"):
                parts.append(f"Error: {bug['error_message']}")
            if bug.get("root_cause"):
                parts.append(f"Root cause: {bug['root_cause']}")
            if bug.get("fix"):
                parts.append(f"Fix: {bug['fix']}")
            if bug.get("file"):
                parts.append(f"File: {bug['file']}")

            value = "\n".join(parts) if parts else str(bug)
            if not value.strip():
                continue

            tags_list = bug.get("tags", [])
            tags = (
                ",".join(tags_list)
                if isinstance(tags_list, list) and tags_list
                else "bug"
            )

            provenance = json.dumps(
                {
                    "source": "buglog.json",
                    "bug_id": str(bug_id),
                }
            )

            entries.append(
                KnowledgeEntry(
                    key=key,
                    value=value,
                    level=0,
                    tags=tags,
                    ingested_from="openwolf",
                    provenance=provenance,
                )
            )

        return entries

    @staticmethod
    def _parse_sections(text: str) -> dict[str, list[str]]:
        sections: dict[str, list[str]] = {}
        current_section: str | None = None
        current_items: list[str] = []

        for line in text.split("\n"):
            heading_match = re.match(r"^##\s+(.+)$", line)
            if heading_match:
                if current_section is not None:
                    sections[current_section] = current_items
                current_section = heading_match.group(1).strip()
                current_items = []
                continue

            if current_section is None:
                continue

            if line.startswith("- "):
                current_items.append(line[2:].strip())
            elif current_items and line.startswith("  "):
                current_items[-1] += " " + line.strip()

        if current_section is not None:
            sections[current_section] = current_items

        return sections

    @staticmethod
    def _slugify(text: str) -> str:
        text = _DATE_PREFIX.sub("", text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        words = re.findall(r"[a-zA-Z0-9]+", text)
        slug = "-".join(words[:5]).lower()
        return slug[:60]
