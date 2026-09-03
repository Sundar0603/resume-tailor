"""
Compression: selection, response validation, and application.

Selection is deterministic and made entirely by application code — the model
never chooses what to compress. Validation happens on the way back in, before
anything touches the resume, and a rejected compression keeps the original
bullet rather than raising.
"""

import json

import pytest

from src.revision import compression
from src.revision.exceptions import InvalidCompressionJSON, InvalidCompressionResponse
from src.revision.models import EntityKind

from .conftest import make_bullet, make_resume


def _long_resume(**overrides):
    """Return a resume whose every bullet wraps to two lines."""
    settings = dict(bullet_words=30, project_bullets=(3, 3), fulltime_bullets=6, intern_bullets=3)
    settings.update(overrides)
    return make_resume(**settings)


def _reply(candidates, text=None):
    """Return a well-formed reply compressing each candidate to a safe string."""
    return json.dumps(
        {
            "compressions": [
                {
                    "bullet_id": c.bullet.bullet_id,
                    "text": text if text is not None else _safe_text(c),
                }
                for c in candidates
            ]
        }
    )


def _safe_text(candidate):
    """Return a short rewrite that keeps every protected fact."""
    kept = list(candidate.facts.numerics) + list(candidate.facts.terms)
    return "Delivered {0}.".format(", ".join(kept)) if kept else "Delivered the work."


class TestEligibility:
    """Only bullets that already wrap are candidates."""

    def test_a_one_line_bullet_is_not_eligible(self):
        resume = make_resume(bullet_words=8)
        assert compression.eligible_bullets(resume) == []

    def test_a_two_line_bullet_is_eligible(self):
        assert compression.eligible_bullets(_long_resume()) != []

    def test_only_the_wrapping_bullets_are_offered(self):
        resume = _long_resume()
        resume.projects[1].highlights[2] = "Short one."
        offered = [b.bullet_id for b in compression.eligible_bullets(resume)]
        assert "proj_002:bullet_3" not in offered


class TestSelectionOrder:
    """Projects, then Experience (Internship, then Full-Time). Skills never."""

    def test_projects_are_offered_before_experience(self):
        first = compression.eligible_bullets(_long_resume())[0]
        assert first.entity_kind is EntityKind.PROJECT

    def test_the_weakest_project_is_offered_first(self):
        assert compression.eligible_bullets(_long_resume())[0].entity_id == "proj_002"

    def test_the_lowest_priority_bullet_within_an_entity_comes_first(self):
        offered = compression.eligible_bullets(_long_resume())
        assert offered[0].bullet_id == "proj_002:bullet_3"
        assert offered[1].bullet_id == "proj_002:bullet_2"

    def test_internship_bullets_come_before_full_time_ones(self):
        offered = [b.entity_id for b in compression.eligible_bullets(_long_resume())]
        assert offered.index("exp_002") < offered.index("exp_001")

    def test_skills_are_never_offered_for_compression(self):
        # A skill category is not prose. Shortening it means either deleting
        # skills, which is deterministic deletion, or renaming a technology,
        # which is by definition mutating a protected fact. Deliberate
        # divergence from the task doc's priority list.
        kinds = {b.entity_kind for b in compression.eligible_bullets(_long_resume())}
        assert EntityKind.SKILL_CATEGORY not in kinds

    def test_the_order_is_deterministic(self):
        resume = _long_resume()
        first = [b.bullet_id for b in compression.eligible_bullets(resume)]
        second = [b.bullet_id for b in compression.eligible_bullets(resume)]
        assert first == second


class TestSelectionSizing:
    """Enough bullets to address the calculated shortfall, and no more."""

    def test_no_shortfall_selects_nothing(self):
        assert compression.select_candidates(_long_resume(), 0) == []

    def test_a_negative_shortfall_selects_nothing(self):
        assert compression.select_candidates(_long_resume(), -3) == []

    def test_a_shortfall_of_one_selects_one_bullet(self):
        assert len(compression.select_candidates(_long_resume(), 1)) == 1

    def test_a_larger_shortfall_selects_more_bullets(self):
        small = compression.select_candidates(_long_resume(), 1)
        large = compression.select_candidates(_long_resume(), 4)
        assert len(large) > len(small)

    def test_selection_stops_once_the_shortfall_is_covered(self):
        candidates = compression.select_candidates(_long_resume(), 3)
        recovered = sum(c.estimated_lines - 1 for c in candidates)
        assert recovered >= 3
        assert sum(c.estimated_lines - 1 for c in candidates[:-1]) < 3

    def test_an_impossible_shortfall_selects_every_eligible_bullet(self):
        resume = _long_resume()
        candidates = compression.select_candidates(resume, 999)
        assert len(candidates) == len(compression.eligible_bullets(resume))

    def test_every_candidate_carries_its_protected_facts(self):
        resume = _long_resume()
        resume.projects[1].highlights[2] = make_bullet("Built Redis caching cutting latency by 40%", 30)
        candidate = compression.select_candidates(resume, 1)[0]
        assert "40%" in candidate.facts.numerics
        assert "Redis" in candidate.facts.terms


class TestResponseParsing:
    """Malformed replies fail safely, and loudly."""

    def test_a_well_formed_reply_parses(self):
        candidates = compression.select_candidates(_long_resume(), 2)
        assert len(compression.parse_response(_reply(candidates))) == 2

    def test_a_fenced_reply_parses(self):
        candidates = compression.select_candidates(_long_resume(), 1)
        fenced = "```json\n" + _reply(candidates) + "\n```"
        assert len(compression.parse_response(fenced)) == 1

    def test_an_empty_reply_raises(self):
        with pytest.raises(InvalidCompressionResponse):
            compression.parse_response("")

    def test_a_whitespace_reply_raises(self):
        with pytest.raises(InvalidCompressionResponse):
            compression.parse_response("   \n  ")

    def test_malformed_json_raises(self):
        with pytest.raises(InvalidCompressionJSON):
            compression.parse_response('{"compressions": [')

    def test_a_reply_without_the_array_raises(self):
        with pytest.raises(InvalidCompressionResponse):
            compression.parse_response('{"result": "done"}')

    def test_a_non_array_compressions_field_raises(self):
        with pytest.raises(InvalidCompressionResponse):
            compression.parse_response('{"compressions": "none"}')

    def test_non_object_entries_are_dropped_rather_than_raising(self):
        assert compression.parse_response('{"compressions": ["nope", 3]}') == []


class TestResponseJudgement:
    """Every check the task doc names, made in application code."""

    def test_a_valid_reply_is_accepted(self):
        candidates = compression.select_candidates(_long_resume(), 2)
        outcomes = compression.evaluate_response(_reply(candidates), candidates)
        assert all(o.accepted for o in outcomes)

    def test_one_outcome_per_candidate_in_selection_order(self):
        candidates = compression.select_candidates(_long_resume(), 3)
        outcomes = compression.evaluate_response(_reply(candidates), candidates)
        assert [o.bullet_id for o in outcomes] == [c.bullet.bullet_id for c in candidates]

    def test_a_missing_bullet_id_is_rejected_not_invented(self):
        candidates = compression.select_candidates(_long_resume(), 2)
        partial = json.loads(_reply(candidates))
        partial["compressions"] = partial["compressions"][:1]
        outcomes = compression.evaluate_response(json.dumps(partial), candidates)
        assert outcomes[0].accepted is True
        assert outcomes[1].accepted is False
        assert "no compression returned" in outcomes[1].rejection

    def test_an_unknown_bullet_id_is_ignored(self):
        candidates = compression.select_candidates(_long_resume(), 1)
        raw = json.dumps(
            {"compressions": [{"bullet_id": "proj_999:bullet_1", "text": "Invented."}]}
        )
        outcomes = compression.evaluate_response(raw, candidates)
        assert len(outcomes) == 1
        assert outcomes[0].accepted is False

    def test_a_duplicate_bullet_id_is_rejected(self):
        candidates = compression.select_candidates(_long_resume(), 1)
        entry = {"bullet_id": candidates[0].bullet.bullet_id, "text": _safe_text(candidates[0])}
        outcomes = compression.evaluate_response(
            json.dumps({"compressions": [entry, dict(entry)]}), candidates
        )
        assert outcomes[0].accepted is False
        assert "duplicate" in outcomes[0].rejection

    def test_a_reply_over_the_word_limit_is_rejected(self):
        candidates = compression.select_candidates(_long_resume(), 1)
        long_text = " ".join(["word"] * 20) + "."
        outcomes = compression.evaluate_response(_reply(candidates, long_text), candidates)
        assert outcomes[0].accepted is False
        assert "limit is 15" in outcomes[0].rejection

    def test_an_empty_compressed_text_is_rejected(self):
        candidates = compression.select_candidates(_long_resume(), 1)
        outcomes = compression.evaluate_response(_reply(candidates, "   "), candidates)
        assert outcomes[0].accepted is False

    def test_a_lost_protected_fact_is_rejected(self):
        resume = _long_resume()
        resume.projects[1].highlights[2] = make_bullet("Built Redis caching cutting latency by 40%", 30)
        candidates = compression.select_candidates(resume, 1)
        outcomes = compression.evaluate_response(
            _reply(candidates, "Improved the caching layer noticeably."), candidates
        )
        assert outcomes[0].accepted is False

    def test_a_fabricated_metric_is_rejected(self):
        candidates = compression.select_candidates(_long_resume(), 1)
        outcomes = compression.evaluate_response(
            _reply(candidates, "Built the component, cutting latency by 40%."), candidates
        )
        assert outcomes[0].accepted is False
        assert "fabricated" in outcomes[0].rejection

    def test_malformed_json_raises_rather_than_silently_accepting(self):
        candidates = compression.select_candidates(_long_resume(), 1)
        with pytest.raises(InvalidCompressionJSON):
            compression.evaluate_response("{not json", candidates)


class TestApplication:
    """Only the selected bullets change, and nothing else moves."""

    def _applied(self, resume, shortfall=2, text=None):
        candidates = compression.select_candidates(resume, shortfall)
        outcomes = compression.evaluate_response(_reply(candidates, text), candidates)
        return candidates, outcomes, compression.apply_compressions(resume, candidates, outcomes)

    def test_an_accepted_compression_replaces_the_bullet_text(self):
        resume = _long_resume()
        candidates, _, after = self._applied(resume)
        target = candidates[0].bullet
        assert after.projects[1].highlights[target.index] != target.text

    def test_unselected_bullets_are_untouched(self):
        resume = _long_resume()
        candidates, _, after = self._applied(resume, shortfall=1)
        selected = {c.bullet.bullet_id for c in candidates}
        for index, text in enumerate(after.projects[0].highlights):
            assert "proj_001:bullet_{0}".format(index + 1) not in selected
            assert text == resume.projects[0].highlights[index]

    def test_bullet_positions_are_preserved(self):
        resume = _long_resume()
        _, _, after = self._applied(resume)
        assert len(after.projects[1].highlights) == len(resume.projects[1].highlights)

    def test_entity_ids_and_sources_survive(self):
        resume = _long_resume()
        _, _, after = self._applied(resume)
        assert [p.id for p in after.projects] == [p.id for p in resume.projects]
        assert [p.source for p in after.projects] == [p.source for p in resume.projects]

    def test_immutable_sections_survive(self):
        resume = _long_resume()
        _, _, after = self._applied(resume)
        assert after.summary == resume.summary
        assert after.education == resume.education
        assert after.contact == resume.contact
        assert after.skills == resume.skills

    def test_a_rejected_compression_leaves_the_original_bullet(self):
        resume = _long_resume()
        candidates, _, after = self._applied(resume, text=" ".join(["word"] * 30))
        target = candidates[0].bullet
        assert after.projects[1].highlights[target.index] == target.text

    def test_the_input_resume_is_never_mutated(self):
        resume = _long_resume()
        before = resume.model_dump_json()
        self._applied(resume)
        assert resume.model_dump_json() == before

    def test_no_entity_is_created_or_removed(self):
        resume = _long_resume()
        _, _, after = self._applied(resume)
        assert len(after.projects) == len(resume.projects)
        assert len(after.experiences) == len(resume.experiences)

    def test_a_bullet_that_moved_since_selection_is_not_written(self):
        # Indices are positional and a removal renumbers everything after it.
        resume = _long_resume()
        candidates = compression.select_candidates(resume, 1)
        outcomes = compression.evaluate_response(_reply(candidates), candidates)
        moved = resume.model_copy(deep=True)
        moved.projects[1].highlights = ["Something else entirely."] * len(
            moved.projects[1].highlights
        )
        after = compression.apply_compressions(moved, candidates, outcomes)
        assert after.projects[1].highlights == moved.projects[1].highlights
