from __future__ import annotations

import pytest

from lore.llm.base import (
    CAPTURE_PROMPT,
    SYNTHESIS_PROMPTS,
    KnowledgeCandidate,
    LLMProvider,
)

# =====================================================================
# AC1: LLMProvider ABC with synthesize + extract_knowledge
# =====================================================================


def test_llm_provider_is_abstract():
    with pytest.raises(TypeError):
        LLMProvider()


def test_knowledge_candidate_required_fields():
    c = KnowledgeCandidate(key="bug:api:timeout", value="fix: increase timeout")
    assert c.key == "bug:api:timeout"
    assert c.value == "fix: increase timeout"


def test_knowledge_candidate_defaults():
    c = KnowledgeCandidate(key="k", value="v")
    assert c.tags == []
    assert c.suggested_level == "individual"
    assert c.negate_key is None
    assert c.negate_reason is None


def test_knowledge_candidate_all_fields():
    c = KnowledgeCandidate(
        key="bug:api:timeout",
        value="fix: increase timeout",
        tags=["api", "bug"],
        suggested_level="team",
        negate_key="pattern:api:retry",
        negate_reason="retry no longer needed",
    )
    assert c.tags == ["api", "bug"]
    assert c.suggested_level == "team"
    assert c.negate_key == "pattern:api:retry"
    assert c.negate_reason == "retry no longer needed"


def test_synthesis_prompts_has_required_keys():
    assert "small" in SYNTHESIS_PROMPTS
    assert "medium" in SYNTHESIS_PROMPTS
    for key in SYNTHESIS_PROMPTS:
        assert len(SYNTHESIS_PROMPTS[key]) > 0


def test_capture_prompt_is_nonempty():
    assert isinstance(CAPTURE_PROMPT, str)
    assert len(CAPTURE_PROMPT) > 0


def test_abc_methods_defined():
    assert hasattr(LLMProvider, "synthesize")
    assert hasattr(LLMProvider, "extract_knowledge")
