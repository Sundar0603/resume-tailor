"""
The engine: the loop, the stopping rule, the artifacts and the failure mode.

Driven by :class:`~tests.revision.conftest.CountingGate`, whose verdict is read
off the **real** rendered LaTeX, so shrinking the resume genuinely changes the
answer. Without that the loop cannot be tested at all: a canned verdict either
always passes or never does.
"""

import json
from pathlib import Path

import pytest

from src.revision import RevisionEngine, floors
from src.revision.exceptions import OnePageInfeasibleError, RevisionStateError
from src.revision.models import RevisionAction
from src.renderer.latex_renderer import LatexRenderer

from .conftest import (
    CountingGate,
    make_bullet,
    ExplodingProvider,
    ScriptedCompressor,
    StubCompiler,
    failing_result,
    make_resume,
    passing_result,
    rendered_rows,
)


def _rows(resume):
    """Return the row count the gate will see for this resume."""
    return rendered_rows(LatexRenderer().render(resume))


def _engine(capacity, provider=None, **kwargs):
    """Return an engine wired to doubles that need no TeX distribution."""
    return RevisionEngine(
        provider=provider,
        compiler=StubCompiler(),
        quality_gate=CountingGate(capacity),
        **kwargs
    )


def _revise(engine, resume, tmp_path, quality=None):
    """Run one revision against a temporary output directory."""
    return engine.revise(
        source_resume=resume,
        current_resume=resume,
        quality_result=quality if quality is not None else failing_result(),
        output_directory=str(tmp_path),
    )


class TestTheGateDoubleIsHonest:
    """If this is wrong every other test in the file is meaningless."""

    def test_removing_a_bullet_lowers_the_row_count(self):
        big = _rows(make_resume(project_bullets=(4, 4)))
        small = _rows(make_resume(project_bullets=(3, 4)))
        assert small < big

    def test_removing_a_skill_category_lowers_the_row_count(self):
        big = _rows(make_resume(skill_sizes=(4, 4, 4)))
        small = _rows(make_resume(skill_sizes=(4, 4)))
        assert small < big


class TestAPassingResumeIsReturnedUnchanged:
    """The task doc is explicit about this case."""

    def test_it_is_returned_unchanged(self, tmp_path):
        resume = make_resume()
        result = _revise(_engine(999), resume, tmp_path, quality=passing_result())
        assert result.resume == resume

    def test_nothing_is_recorded_as_revised(self, tmp_path):
        result = _revise(_engine(999), make_resume(), tmp_path, quality=passing_result())
        assert result.revised is False
        assert result.attempts == 0
        assert result.trail == []

    def test_nothing_is_compiled(self, tmp_path):
        compiler = StubCompiler()
        engine = RevisionEngine(compiler=compiler, quality_gate=CountingGate(999))
        engine.revise(
            source_resume=make_resume(),
            current_resume=make_resume(),
            quality_result=passing_result(),
            output_directory=str(tmp_path),
        )
        assert compiler.calls == 0

    def test_orphan_warnings_do_not_trigger_a_revision(self, tmp_path):
        # ORPHAN_WORD is the only WARNING and never blocks. Trimming further
        # because warnings exist would be exactly the mistake the task doc names.
        result = _revise(_engine(999), make_resume(), tmp_path, quality=passing_result())
        assert result.quality.warnings
        assert result.revised is False


class TestDeterministicConvergence:
    """It trims until the page fits, and stops the moment it does."""

    def test_it_converges(self, tmp_path):
        resume = make_resume(project_bullets=(4, 4), fulltime_bullets=8)
        result = _revise(_engine(_rows(resume) - 3), resume, tmp_path)
        assert result.passed is True

    def test_it_uses_no_llm_at_all(self, tmp_path):
        resume = make_resume(project_bullets=(4, 4), fulltime_bullets=8)
        engine = _engine(_rows(resume) - 3, provider=ExplodingProvider())
        result = _revise(engine, resume, tmp_path)
        assert result.llm_calls == 0
        assert result.compression_passes == 0

    def test_it_stops_immediately_once_the_gate_passes(self, tmp_path):
        resume = make_resume(project_bullets=(4, 4), fulltime_bullets=8)
        gate = CountingGate(_rows(resume) - 2)
        engine = RevisionEngine(compiler=StubCompiler(), quality_gate=gate)
        result = _revise(engine, resume, tmp_path)
        assert result.passed is True
        assert gate.calls == result.attempts
        assert result.trail[-1].passed is True
        assert all(step.passed is False for step in result.trail[:-1])

    def test_a_resume_needing_one_removal_takes_one_attempt(self, tmp_path):
        resume = make_resume(project_bullets=(4, 4))
        result = _revise(_engine(_rows(resume) - 1), resume, tmp_path)
        assert result.attempts == 1
        assert result.deterministic_steps == 1

    def test_the_returned_resume_is_the_changed_one(self, tmp_path):
        resume = make_resume(project_bullets=(4, 4), fulltime_bullets=8)
        result = _revise(_engine(_rows(resume) - 3), resume, tmp_path)
        assert result.resume != resume
        assert result.resume.total_highlights() < resume.total_highlights()


class TestFloorsAreNeverBreached:
    """Not even to avoid failing."""

    def test_the_delivered_resume_respects_every_floor(self, tmp_path):
        resume = make_resume(
            project_bullets=(5, 5, 5), skill_sizes=(6, 6, 6), fulltime_bullets=9, intern_bullets=6
        )
        result = _revise(_engine(_rows(resume) - 12), resume, tmp_path)
        delivered = result.resume
        assert len(delivered.projects) >= floors.MIN_PROJECTS
        assert all(len(p.highlights) >= floors.PROJECT_BULLET_FLOOR for p in delivered.projects)
        assert delivered.total_skills() >= floors.MIN_TOTAL_SKILLS
        assert len(delivered.experiences) == floors.REQUIRED_EXPERIENCES
        assert len(delivered.experiences[0].highlights) >= floors.FULLTIME_BULLET_FLOOR
        assert len(delivered.experiences[1].highlights) >= floors.INTERNSHIP_BULLET_FLOOR

    def test_an_impossible_target_raises_rather_than_breaching(self, tmp_path):
        resume = make_resume()
        with pytest.raises(OnePageInfeasibleError):
            _revise(_engine(1), resume, tmp_path)

    def test_the_failure_carries_its_diagnostics(self, tmp_path):
        with pytest.raises(OnePageInfeasibleError) as caught:
            _revise(_engine(1), make_resume(), tmp_path)
        assert caught.value.spill > 0
        assert caught.value.steps_taken > 0
        assert caught.value.trail_path is not None

    def test_the_original_failing_resume_is_never_returned_as_a_success(self, tmp_path):
        # The engine raises instead. There is no path that reports success
        # while handing back the resume that failed.
        with pytest.raises(OnePageInfeasibleError):
            _revise(_engine(1), make_resume(), tmp_path)


class TestStatedInvariants:
    """No internship means the removal order cannot be applied."""

    def test_a_resume_with_no_internship_raises(self, tmp_path):
        resume = make_resume()
        resume.experiences[1].employment_type = "Full Time"
        with pytest.raises(RevisionStateError):
            _revise(_engine(999), resume, tmp_path)

    def test_it_raises_before_anything_is_compiled(self, tmp_path):
        resume = make_resume()
        resume.experiences[1].employment_type = "Full Time"
        compiler = StubCompiler()
        engine = RevisionEngine(compiler=compiler, quality_gate=CountingGate(999))
        with pytest.raises(RevisionStateError):
            engine.revise(
                source_resume=resume,
                current_resume=resume,
                quality_result=failing_result(),
                output_directory=str(tmp_path),
            )
        assert compiler.calls == 0


class TestNoMutation:
    """The source resume is never modified, and neither is the input."""

    def test_the_source_resume_is_untouched(self, tmp_path):
        resume = make_resume(project_bullets=(4, 4), fulltime_bullets=8)
        before = resume.model_dump_json()
        _revise(_engine(_rows(resume) - 3), resume, tmp_path)
        assert resume.model_dump_json() == before

    def test_the_current_resume_is_untouched(self, tmp_path):
        source = make_resume()
        current = make_resume(project_bullets=(4, 4), fulltime_bullets=8)
        before = current.model_dump_json()
        engine = _engine(_rows(current) - 3)
        engine.revise(
            source_resume=source,
            current_resume=current,
            quality_result=failing_result(),
            output_directory=str(tmp_path),
        )
        assert current.model_dump_json() == before


class TestArtifacts:
    """The engine owns attempt numbering; checkpoints, not every iteration."""

    def test_the_final_artifacts_are_written(self, tmp_path):
        resume = make_resume(project_bullets=(4, 4), fulltime_bullets=8)
        _revise(_engine(_rows(resume) - 3), resume, tmp_path)
        assert (tmp_path / "final" / "resume.tex").is_file()
        assert (tmp_path / "final" / "resume.pdf").is_file()

    def test_the_trail_is_persisted(self, tmp_path):
        resume = make_resume(project_bullets=(4, 4), fulltime_bullets=8)
        result = _revise(_engine(_rows(resume) - 3), resume, tmp_path)
        payload = json.loads((tmp_path / "revision_trail.json").read_text(encoding="utf-8"))
        assert payload["attempts"] == result.attempts
        assert len(payload["steps"]) == len(result.trail)

    def test_every_step_is_in_the_trail_not_only_the_checkpoints(self, tmp_path):
        resume = make_resume(project_bullets=(4, 4), fulltime_bullets=8)
        result = _revise(_engine(_rows(resume) - 4), resume, tmp_path)
        assert len(result.trail) == result.deterministic_steps
        assert len(list(tmp_path.glob("attempt_*"))) < len(result.trail)

    def test_each_trail_entry_records_what_happened(self, tmp_path):
        resume = make_resume(project_bullets=(4, 4), fulltime_bullets=8)
        result = _revise(_engine(_rows(resume) - 3), resume, tmp_path)
        for step in result.trail:
            assert step.action in list(RevisionAction)
            assert step.page_count is not None
            assert step.spill is not None

    def test_attempt_numbers_are_sequential_from_one(self, tmp_path):
        resume = make_resume(project_bullets=(4, 4), fulltime_bullets=8)
        result = _revise(_engine(_rows(resume) - 4), resume, tmp_path)
        assert [s.attempt for s in result.trail] == list(range(1, len(result.trail) + 1))

    def test_a_failed_run_still_leaves_a_trail_and_a_checkpoint(self, tmp_path):
        with pytest.raises(OnePageInfeasibleError):
            _revise(_engine(1), make_resume(), tmp_path)
        assert (tmp_path / "revision_trail.json").is_file()
        assert list(tmp_path.glob("attempt_*"))

    def test_intermediate_attempts_share_one_work_directory(self, tmp_path):
        resume = make_resume(project_bullets=(4, 4), fulltime_bullets=8)
        _revise(_engine(_rows(resume) - 4), resume, tmp_path)
        assert (tmp_path / "work" / "resume.tex").is_file()


class TestTheCompressionPath:
    """Only reachable once deterministic deletion is exhausted."""

    def _cornered(self):
        """
        Return a resume at every floor whose bullets all wrap to two lines.

        The bullets are deliberately fact-free — no numbers, no technologies —
        so this test exercises the *loop*, not the verifier. Rejection is
        covered in ``test_compression.py`` against bullets that do carry facts.
        """
        resume = make_resume(
            project_bullets=(2, 2),
            skill_sizes=(3, 2),
            fulltime_bullets=5,
            intern_bullets=3,
            bullet_words=30,
        )
        filler = make_bullet("Handled the ongoing work for the wider group", 30)
        for project in resume.projects:
            project.highlights = [filler] * len(project.highlights)
        for experience in resume.experiences:
            experience.highlights = [filler] * len(experience.highlights)
        return resume

    def _accepting_reply(self, resume):
        """Return a reply that keeps every protected fact in every bullet."""
        from src.revision import compression

        candidates = compression.select_candidates(resume, 99)
        return json.dumps(
            {
                "compressions": [
                    {"bullet_id": c.bullet.bullet_id, "text": "Delivered the work item."}
                    for c in candidates
                ]
            }
        )

    def test_no_provider_means_no_compression(self, tmp_path):
        resume = self._cornered()
        with pytest.raises(OnePageInfeasibleError):
            _revise(_engine(1, provider=None), resume, tmp_path)

    def test_it_makes_exactly_one_call_per_pass(self, tmp_path):
        resume = self._cornered()
        provider = ScriptedCompressor([self._accepting_reply(resume)])
        engine = _engine(_rows(resume) - 1, provider=provider)
        _revise(engine, resume, tmp_path)
        assert provider.calls == 1

    def test_several_bullets_travel_in_one_prompt(self, tmp_path):
        resume = self._cornered()
        provider = ScriptedCompressor([self._accepting_reply(resume)])
        engine = _engine(_rows(resume) - 1, provider=provider)
        _revise(engine, resume, tmp_path)
        assert provider.prompts[0].count('"bullet_id"') > 2

    def test_it_uses_the_deterministic_sampling_options(self, tmp_path):
        resume = self._cornered()
        provider = ScriptedCompressor([self._accepting_reply(resume)])
        engine = _engine(_rows(resume) - 1, provider=provider)
        _revise(engine, resume, tmp_path)
        assert provider.options[0]["temperature"] == 0.0
        assert provider.options[0]["json_mode"] is True

    def test_an_accepted_compression_reaches_the_resume(self, tmp_path):
        resume = self._cornered()
        provider = ScriptedCompressor([self._accepting_reply(resume)])
        engine = _engine(_rows(resume) - 1, provider=provider)
        result = _revise(engine, resume, tmp_path)
        assert "Delivered the work item." in result.resume.projects[1].highlights

    def test_the_compression_is_recorded_in_the_trail(self, tmp_path):
        resume = self._cornered()
        provider = ScriptedCompressor([self._accepting_reply(resume)])
        engine = _engine(_rows(resume) - 1, provider=provider)
        result = _revise(engine, resume, tmp_path)
        entry = result.trail[-1]
        assert entry.action is RevisionAction.COMPRESS_BULLETS
        assert entry.bullet_ids
        assert entry.shortfall_before is not None

    def test_a_rejected_reply_is_recorded_and_stops_the_path(self, tmp_path):
        resume = self._cornered()
        provider = ScriptedCompressor([json.dumps({"compressions": []})])
        engine = _engine(1, provider=provider)
        with pytest.raises(OnePageInfeasibleError):
            _revise(engine, resume, tmp_path)
        assert provider.calls == 1

    def test_the_compression_budget_is_capped(self, tmp_path):
        resume = self._cornered()
        provider = ScriptedCompressor([self._accepting_reply(resume)])
        engine = _engine(1, provider=provider, max_compression_passes=2)
        with pytest.raises(OnePageInfeasibleError):
            _revise(engine, resume, tmp_path)
        assert provider.calls <= 2

    def test_the_default_cap_matches_the_architecture_budget(self):
        from src.revision.revision_engine import MAX_COMPRESSION_PASSES

        assert MAX_COMPRESSION_PASSES == 3
