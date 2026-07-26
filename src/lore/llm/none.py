from __future__ import annotations

from lore.llm.base import DocChunkExtraction, KnowledgeCandidate, LLMProvider
from lore.store.base import KnowledgeEntry


class NoneProvider(LLMProvider):
    def synthesize(self, topic: str, candidates: list[KnowledgeEntry]) -> str:
        if not candidates:
            return "No relevant knowledge found."
        return "\n".join(f"[{e.key}] {e.value}" for e in candidates)

    def extract_knowledge(
        self,
        transcript: str,
        existing: list[KnowledgeEntry],
        project_config=None,
    ) -> list[KnowledgeCandidate]:
        return []

    def extract_from_chunk(
        self,
        chunk_text: str,
        heading: str,
        source_file: str,
    ) -> list[DocChunkExtraction]:
        return []
