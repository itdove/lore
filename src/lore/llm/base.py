from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from lore.store.base import KnowledgeEntry


@dataclass
class KnowledgeCandidate:
    key: str
    value: str
    tags: list[str] = field(default_factory=list)
    suggested_level: str = "individual"
    negate_key: str | None = None
    negate_reason: str | None = None


class LLMProvider(ABC):
    @abstractmethod
    def synthesize(self, topic: str, candidates: list[KnowledgeEntry]) -> str: ...

    @abstractmethod
    def extract_knowledge(
        self,
        transcript: str,
        existing: list[KnowledgeEntry],
        project_config=None,
    ) -> list[KnowledgeCandidate]: ...


SYNTHESIS_PROMPTS = {
    "small": (
        "You are a knowledge retrieval assistant.\n"
        "Priority order (highest wins): individual > team > product > org.\n"
        "Return the most relevant answer for the topic.\n"
        'Be concise. If nothing relevant: reply "no relevant knowledge found".'
    ),
    "medium": (
        "Synthesize the most relevant knowledge for the topic.\n"
        "Respect priority hierarchy. Attribute facts to their source level."
    ),
}

CAPTURE_PROMPT_BASE = (
    "You are a knowledge extraction assistant.\n"
    "From this session transcript, extract:\n"
    "1. Bugs found — root cause and fix pattern\n"
    "2. Decisions made — what was chosen and why\n"
    "3. Patterns discovered — non-obvious conventions or constraints\n"
    "\n"
    "For each, provide:\n"
    "- key: colon-separated segments (e.g., bug:api:jwt)\n"
    "- value: the knowledge (include WHY, not just WHAT)\n"
    "- tags: relevant tags\n"
    "- suggested_level: use one of the available level names\n"
    "\n"
    "Also identify entries from the existing knowledge list that are\n"
    "contradicted by this session's findings. Return as negations with\n"
    "negate_key and negate_reason fields.\n"
    "\n"
    "Skip: ephemeral task state, git history, conversation filler.\n"
    "Output as JSON array."
)


def build_capture_prompt(
    project_config=None,
) -> str:
    parts = [CAPTURE_PROMPT_BASE]

    if project_config is not None:
        level_lines = [f"- individual: {project_config.individual_description}"]
        for h in project_config.hierarchy:
            rw = "writable" if h.writable else "read-only"
            name = h.name or f"level-{h.level}"
            desc = h.description or f"Level {h.level} shared knowledge"
            level_lines.append(f"- {name} (level {h.level}, {rw}): {desc}")

        parts.append("\nAvailable levels:\n" + "\n".join(level_lines))
        parts.append("\nDo NOT suggest non-writable levels for new entries.")

        ks = project_config.key_structure
        if ks.examples:
            examples = ", ".join(ks.examples)
            parts.append(f"\nKey format: {ks.description}")
            parts.append(f"Examples: {examples}")

    return "\n".join(parts)
