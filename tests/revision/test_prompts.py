"""
The compression prompt.

Prompt construction only. The important properties are that the model is given
a closed list, that everything it must not touch is *absent* rather than
forbidden, and that the same candidates always produce byte-identical text.
"""

from src.revision import prompts
from src.revision.measure import ONE_LINE_WORD_BUDGET
from src.revision.models import (
    BulletRef,
    CompressionCandidate,
    EntityKind,
    ProtectedFacts,
)


def _candidate(bullet_id="proj_002:bullet_3", text=None, numerics=None, terms=None):
    """Return one compression candidate."""
    return CompressionCandidate(
        bullet=BulletRef(
            bullet_id=bullet_id,
            entity_id=bullet_id.split(":")[0],
            entity_kind=EntityKind.PROJECT,
            index=2,
            text=text or "Built a Redis caching layer that reduced API latency by 40%.",
        ),
        estimated_lines=2,
        facts=ProtectedFacts(numerics=numerics or ["40%"], terms=terms or ["Redis", "API"]),
    )


class TestWhatThePromptContains:
    """Everything the LLM Compression Contract lists."""

    def test_the_bullet_ids_are_given(self):
        assert "proj_002:bullet_3" in prompts.build_compression_prompt([_candidate()])

    def test_the_original_text_is_given(self):
        prompt = prompts.build_compression_prompt([_candidate()])
        assert "Built a Redis caching layer" in prompt

    def test_the_protected_facts_are_given(self):
        prompt = prompts.build_compression_prompt([_candidate()])
        assert "40%" in prompt
        assert "Redis" in prompt

    def test_the_word_limit_is_stated(self):
        prompt = prompts.build_compression_prompt([_candidate()])
        assert str(ONE_LINE_WORD_BUDGET) in prompt

    def test_the_response_schema_is_stated(self):
        prompt = prompts.build_compression_prompt([_candidate()])
        assert '"compressions"' in prompt
        assert '"bullet_id"' in prompt

    def test_a_custom_word_limit_reaches_the_prompt(self):
        assert " 12 words or fewer" in prompts.build_compression_prompt(
            [_candidate()], max_words=12
        )


class TestWhatThePromptOmits:
    """
    The model cannot rewrite what it never sees. Absence beats prohibition.
    """

    def test_the_summary_is_not_in_the_prompt(self):
        prompt = prompts.build_compression_prompt([_candidate()])
        assert "summary" not in prompt.lower()

    def test_education_is_not_in_the_prompt(self):
        assert "education" not in prompts.build_compression_prompt([_candidate()]).lower()

    def test_contact_details_are_not_in_the_prompt(self):
        assert "linkedin" not in prompts.build_compression_prompt([_candidate()]).lower()

    def test_unselected_bullets_are_not_in_the_prompt(self):
        prompt = prompts.build_compression_prompt([_candidate()])
        assert "proj_001" not in prompt


class TestTheRules:
    """The rules the task doc requires the prompt to state."""

    def test_it_forbids_inventing_a_number(self):
        assert "Never invent a number" in prompts.build_compression_prompt([_candidate()])

    def test_it_forbids_adjusting_an_existing_number(self):
        prompt = prompts.build_compression_prompt([_candidate()])
        assert "raise, lower or round" in prompt

    def test_it_forbids_generalising_a_name(self):
        prompt = prompts.build_compression_prompt([_candidate()])
        assert "does not become" in prompt

    def test_it_requires_every_protected_fact_to_survive(self):
        prompt = prompts.build_compression_prompt([_candidate()])
        assert "must appear in your rewrite, unchanged" in prompt

    def test_it_forbids_adding_merging_or_splitting(self):
        prompt = prompts.build_compression_prompt([_candidate()])
        assert "Do not add content" in prompt
        assert "Do not merge two bullets" in prompt


class TestDeterminism:
    """Byte-identical for the same candidates."""

    def test_the_same_candidates_give_the_same_prompt(self):
        first = prompts.build_compression_prompt([_candidate()])
        second = prompts.build_compression_prompt([_candidate()])
        assert first == second

    def test_candidate_order_is_preserved(self):
        prompt = prompts.build_compression_prompt(
            [_candidate("proj_002:bullet_3"), _candidate("exp_001:bullet_5")]
        )
        assert prompt.index("proj_002:bullet_3") < prompt.index("exp_001:bullet_5")

    def test_no_candidates_still_builds(self):
        assert '"compressions"' in prompts.build_compression_prompt([])


class TestTheDispatchMarkers:
    """
    ``tests/pipeline/conftest.py`` routes scripted replies on these. Exposing
    them from the prompt module is what stops that fixture drifting silently.
    """

    def test_every_marker_appears_in_the_prompt(self):
        prompt = prompts.build_compression_prompt([_candidate()])
        assert all(marker in prompt for marker in prompts.response_markers())

    def test_the_markers_are_not_empty(self):
        assert prompts.response_markers()
