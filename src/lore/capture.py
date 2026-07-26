from __future__ import annotations

import logging
from dataclasses import dataclass, field

from lore.llm.base import KnowledgeCandidate, LLMProvider
from lore.store.base import StoreBackend

logger = logging.getLogger(__name__)


@dataclass
class CaptureAction:
    candidate: KnowledgeCandidate
    action: str
    existing_key: str | None = None
    existing_value: str | None = None
    distance: float | None = None


@dataclass
class CaptureResult:
    candidates: list[KnowledgeCandidate] = field(default_factory=list)
    new: list[KnowledgeCandidate] = field(default_factory=list)
    updates: list[KnowledgeCandidate] = field(default_factory=list)
    duplicates: list[KnowledgeCandidate] = field(default_factory=list)
    negations: list[KnowledgeCandidate] = field(default_factory=list)
    enrichments: list[CaptureAction] = field(default_factory=list)
    skipped: list[CaptureAction] = field(default_factory=list)


def capture_knowledge(
    transcript: str,
    store: StoreBackend,
    provider: LLMProvider,
    project_config=None,
    capture_config=None,
) -> CaptureResult:
    existing = store.list_entries()
    candidates = provider.extract_knowledge(
        transcript, existing, project_config=project_config
    )
    result = CaptureResult(candidates=list(candidates))

    max_entries = 5
    if capture_config:
        max_entries = capture_config.max_entries_per_session

    if len(result.candidates) > max_entries:
        result.skipped.extend(
            CaptureAction(candidate=c, action="rate_limited")
            for c in result.candidates[max_entries:]
        )
        result.candidates = result.candidates[:max_entries]

    existing_by_key = {e.key: e for e in existing}

    emb_provider = None
    dedup_threshold = 0.20
    try:
        from lore.config.manager import get_global_config

        cfg = get_global_config()
        dedup_threshold = cfg.search.dedup_threshold
        if cfg.search.embedding_provider != "none":
            from lore.embedding import get_embedding_provider

            emb_provider = get_embedding_provider()
    except Exception:
        pass

    for c in result.candidates:
        if c.negate_key:
            result.negations.append(c)

        entry = existing_by_key.get(c.key)
        if entry is not None:
            if entry.value.strip() == c.value.strip():
                result.duplicates.append(c)
                result.skipped.append(
                    CaptureAction(
                        candidate=c,
                        action="exact_match",
                        existing_key=entry.key,
                    )
                )
            else:
                result.updates.append(c)
            continue

        if emb_provider:
            try:
                emb = emb_provider.embed(f"{c.key} {c.value}")
                if emb:
                    dupes = store.query_vector(emb, limit=1, filter_levels=None)
                    if dupes:
                        closest, dist = dupes[0]
                        if dist < dedup_threshold:
                            result.enrichments.append(
                                CaptureAction(
                                    candidate=c,
                                    action="enrich",
                                    existing_key=closest.key,
                                    existing_value=closest.value,
                                    distance=dist,
                                )
                            )
                            continue
            except Exception:
                logger.debug("Embedding check failed for %s", c.key)

        result.new.append(c)

    return result
