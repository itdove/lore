from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request

from lore.llm.base import (
    DOC_CHUNK_PROMPT,
    SYNTHESIS_PROMPTS,
    DocChunkExtraction,
    KnowledgeCandidate,
    LLMProvider,
)
from lore.store.base import KnowledgeEntry, sanitize_key

log = logging.getLogger("lore.llm")

_SMALL_MODEL_PATTERNS = ("phi", "qwen", ":1b", ":3b", ":7b", "gemma:2b")
_CAPTURE_VALUE_SNIPPET_CHARS = 240
_CAPTURE_FALLBACK_ENTRY_LIMIT = 50


class OllamaProvider(LLMProvider):
    def __init__(self, model: str, base_url: str = "http://localhost:11434") -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")

    def _model_tier(self) -> str:
        name = self._model.lower()
        for pattern in _SMALL_MODEL_PATTERNS:
            if pattern in name:
                return "small"
        return "medium"

    def _generate(self, prompt: str) -> str:
        body = json.dumps(
            {"model": self._model, "prompt": prompt, "stream": False}
        ).encode()
        req = urllib.request.Request(
            f"{self._base_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
                return data.get("response", "")
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            log.warning("Ollama request failed: %s", exc)
            return ""

    def synthesize(self, topic: str, candidates: list[KnowledgeEntry]) -> str:
        if not candidates:
            return "No relevant knowledge found."
        system_prompt = SYNTHESIS_PROMPTS[self._model_tier()]
        entries_text = "\n".join(
            f"- [{e.key}] (level {e.level}): {e.value}" for e in candidates
        )
        prompt = (
            f"{system_prompt}\n\n"
            f"Topic: {topic}\n\n"
            f"Knowledge entries:\n{entries_text}"
        )
        result = self._generate(prompt)
        return result or "No relevant knowledge found."

    def extract_knowledge(
        self,
        transcript: str,
        existing: list[KnowledgeEntry],
        project_config=None,
    ) -> list[KnowledgeCandidate]:
        from lore.llm.base import build_capture_prompt

        existing_text = _format_capture_existing(existing)
        capture_prompt = build_capture_prompt(project_config)
        prompt = (
            f"{capture_prompt}\n\n"
            f"Existing knowledge:\n{existing_text}\n\n"
            f"Session transcript:\n{transcript}"
        )
        raw = self._generate(prompt)
        if not raw:
            return []
        return _parse_candidates(raw)

    def extract_from_chunk(
        self,
        chunk_text: str,
        heading: str,
        source_file: str,
    ) -> list[DocChunkExtraction]:
        prompt = (
            f"{DOC_CHUNK_PROMPT}\n\n"
            f"Source file: {source_file}\n"
            f"Section heading: {heading or '(no heading)'}\n\n"
            f"Document section:\n{chunk_text}"
        )
        raw = self._generate(prompt)
        if not raw:
            return []
        return _parse_doc_extractions(raw)


def _format_capture_existing(existing: list[KnowledgeEntry]) -> str:
    """Format bounded capture context with optional short value snippets.

    Capture passes value-less entries when semantic search is unavailable. In
    that case, keeping only the key preserves duplicate and negation hints
    without adding unbounded or low-quality context to the prompt.
    """

    lines = []
    for entry in existing[-_CAPTURE_FALLBACK_ENTRY_LIMIT:]:
        if not entry.value:
            lines.append(f"- {entry.key}")
            continue

        value = " ".join(entry.value.split())
        if len(value) > _CAPTURE_VALUE_SNIPPET_CHARS:
            value = value[:_CAPTURE_VALUE_SNIPPET_CHARS].rstrip() + "..."
        lines.append(f"- {entry.key}: {value}")
    return "\n".join(lines)


def _parse_doc_extractions(raw: str) -> list[DocChunkExtraction]:
    text = re.sub(r"```(?:json)?\s*", "", raw).strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        log.warning("No JSON array found in LLM doc extraction response")
        return []
    try:
        items = json.loads(match.group())
    except json.JSONDecodeError:
        log.warning("Failed to parse JSON from LLM doc extraction response")
        return []
    results: list[DocChunkExtraction] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        summary = item.get("summary") or item.get("value", "")
        if not key or not summary:
            continue
        key = sanitize_key(key)
        if not key:
            continue
        results.append(
            DocChunkExtraction(
                key=key,
                summary=summary,
                tags=item.get("tags", []),
                content_type=item.get("content_type", "general"),
                suggested_level=item.get("suggested_level", "individual"),
            )
        )
    return results


def _parse_candidates(raw: str) -> list[KnowledgeCandidate]:
    text = re.sub(r"```(?:json)?\s*", "", raw).strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        log.warning("No JSON array found in LLM response")
        return []
    try:
        items = json.loads(match.group())
    except json.JSONDecodeError:
        log.warning("Failed to parse JSON from LLM response")
        return []
    candidates = []
    for item in items:
        if not isinstance(item, dict) or "key" not in item or "value" not in item:
            continue
        key = sanitize_key(item["key"])
        if not key:
            continue
        candidates.append(
            KnowledgeCandidate(
                key=key,
                value=item["value"],
                tags=item.get("tags", []),
                suggested_level=item.get("suggested_level", "individual"),
                negate_key=(
                    sanitize_key(item["negate_key"]) if item.get("negate_key") else None
                ),
                negate_reason=item.get("negate_reason"),
            )
        )
    return candidates
