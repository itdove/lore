from __future__ import annotations

from dataclasses import dataclass, field

from lore.llm.base import KnowledgeCandidate, LLMProvider
from lore.store.base import StoreBackend


@dataclass
class CaptureResult:
    candidates: list[KnowledgeCandidate] = field(default_factory=list)
    new: list[KnowledgeCandidate] = field(default_factory=list)
    updates: list[KnowledgeCandidate] = field(default_factory=list)
    duplicates: list[KnowledgeCandidate] = field(default_factory=list)
    negations: list[KnowledgeCandidate] = field(default_factory=list)


def capture_knowledge(
    transcript: str,
    store: StoreBackend,
    provider: LLMProvider,
) -> CaptureResult:
    existing = store.list_entries()
    candidates = provider.extract_knowledge(transcript, existing)
    result = CaptureResult(candidates=list(candidates))

    existing_by_key = {e.key: e for e in existing}

    for c in candidates:
        # Negations also fall through to new/dup/update — a negation
        # candidate records *both* the replacement entry and the stale ref.
        if c.negate_key:
            result.negations.append(c)

        entry = existing_by_key.get(c.key)
        if entry is None:
            result.new.append(c)
        elif entry.value.strip() == c.value.strip():
            result.duplicates.append(c)
        else:
            result.updates.append(c)

    return result
