from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request

from lore.llm.base import (
    CAPTURE_PROMPT,
    SYNTHESIS_PROMPTS,
    KnowledgeCandidate,
    LLMProvider,
)
from lore.store.base import KnowledgeEntry

log = logging.getLogger("lore.llm")

_SMALL_MODEL_PATTERNS = ("phi", "qwen", ":1b", ":3b", ":7b", "gemma:2b")


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
        self, transcript: str, existing: list[KnowledgeEntry]
    ) -> list[KnowledgeCandidate]:
        existing_text = "\n".join(f"- [{e.key}]: {e.value}" for e in existing)
        prompt = (
            f"{CAPTURE_PROMPT}\n\n"
            f"Existing knowledge:\n{existing_text}\n\n"
            f"Session transcript:\n{transcript}"
        )
        raw = self._generate(prompt)
        if not raw:
            return []
        return _parse_candidates(raw)


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
        candidates.append(
            KnowledgeCandidate(
                key=item["key"],
                value=item["value"],
                tags=item.get("tags", []),
                suggested_level=item.get("suggested_level", "individual"),
                negate_key=item.get("negate_key"),
                negate_reason=item.get("negate_reason"),
            )
        )
    return candidates
