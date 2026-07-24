from __future__ import annotations

from lore.llm.base import KnowledgeCandidate, LLMProvider
from lore.store.base import KnowledgeEntry


class NoneProvider(LLMProvider):
    def synthesize(self, topic: str, candidates: list[KnowledgeEntry]) -> str:
        if not candidates:
            return "No relevant knowledge found."
        return "\n".join(f"[{e.key}] {e.value}" for e in candidates)

    def extract_knowledge(
        self, transcript: str, existing: list[KnowledgeEntry]
    ) -> list[KnowledgeCandidate]:
        return []
