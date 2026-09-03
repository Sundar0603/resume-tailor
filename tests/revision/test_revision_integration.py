"""
The engine against the real toolchain: real renderer, real pdflatex, real gate.

Skipped cleanly when no TeX distribution is on PATH, matching
``tests/quality/test_quality_gate_integration.py`` and
``tests/compiler/test_compilation_integration.py``. There are no pytest markers
registered in ``pyproject.toml``, so ``skipif`` *is* this project's integration
marker.

The inputs are the resumes six earlier live runs actually produced, reloaded
from ``output/runs/<name>/04_generated_resume.json``. That matters:
PROJECT_KNOWLEDGE §9 lesson 6 is the project's most expensive lesson — the
planner shipped with 318 green tests while every real invocation failed. These
tests use genuine model output and the genuine toolchain, and still cost no
inference.

**Zero LLM calls.** The provider is one that raises if touched, so a
deterministic convergence that quietly reached for a model would fail here.
"""

import json
import shutil

import pytest

from src.compiler.exceptions import CompilationFailedError
from src.compiler.pdf_compiler import PDFCompiler
from src.parser import ResumeParser
from src.parser.models import Resume
from src.quality.quality_gate import QualityGate
from src.renderer.latex_renderer import LatexRenderer
from src.revision import RevisionEngine, floors
from src.revision.models import RevisionAction

from .conftest import ExplodingProvider

pytestmark = pytest.mark.skipif(
    shutil.which("pdflatex") is None, reason="pdflatex is not installed"
)

#: Resumes produced by earlier live runs. Absent ones are skipped rather than
#: failed: the artifacts are gitignored and a fresh clone has none.
LIVE_RUNS = [
    "backend_strict",
    "backend_aggressive",
    "cybersecurity_strict",
    "cybersecurity_aggressive",
    "fullstack_strict",
    "fullstack_aggressive",
]


def _load(name):
    """Return a live-generated resume, or skip when it is not on disk."""
    path = "output/runs/{0}/04_generated_resume.json".format(name)
    try:
        with open(path, encoding="utf-8") as handle:
            return Resume.model_validate(json.load(handle))
    except (IOError, OSError):
        pytest.skip("no generated resume at {0}".format(path))


def _judge(resume, directory):
    """Render, compile and judge a resume for real."""
    latex = LatexRenderer().render(resume)
    gate = QualityGate()
    try:
        compilation = PDFCompiler().compile(
            latex, output_directory=str(directory), job_name="before"
        )
    except CompilationFailedError as failure:
        return gate.evaluate_compilation_failure(failure)
    return gate.evaluate(compilation.pdf_path, compilation.tex_path, compilation)


def _revise(resume, tmp_path):
    """Run a real revision with a provider that must never be called."""
    before = _judge(resume, tmp_path / "before")
    engine = RevisionEngine(provider=ExplodingProvider())
    return before, engine.revise(
        source_resume=resume,
        current_resume=resume,
        quality_result=before,
        output_directory=str(tmp_path / "run"),
    )


class TestTheCanonicalResumes:
    """The three source resumes, straight through the real chain."""

    @pytest.mark.parametrize("name", ["backend", "cybersecurity", "fullstack"])
    def test_a_canonical_resume_is_delivered_on_one_page(self, name, tmp_path):
        resume = ResumeParser().parse("content/{0}_resume.md".format(name))
        _, result = _revise(resume, tmp_path)
        assert result.passed is True
        assert result.quality.metrics.page_count == 1


class TestTheLiveGeneratedResumes:
    """
    The six runs measured in PROJECT_KNOWLEDGE §10g, spilling 0-18 lines.

    Under the task 017 floors every one of them should converge by deletion
    alone. A failure here is the signal that the floors or the removal order
    need revisiting — it is the cheapest real evidence this project has.
    """

    @pytest.mark.parametrize("name", LIVE_RUNS)
    def test_it_converges_on_one_page(self, name, tmp_path):
        _, result = _revise(_load(name), tmp_path)
        assert result.passed is True
        assert result.quality.metrics.page_count == 1
        assert result.quality.metrics.overflow_line_count == 0

    @pytest.mark.parametrize("name", LIVE_RUNS)
    def test_it_needs_no_llm(self, name, tmp_path):
        _, result = _revise(_load(name), tmp_path)
        assert result.llm_calls == 0
        assert result.compression_passes == 0

    @pytest.mark.parametrize("name", LIVE_RUNS)
    def test_the_delivered_resume_respects_every_floor(self, name, tmp_path):
        # The floor is a *trimming* policy, not a generation guarantee. Some
        # live runs arrive already below one — cybersecurity_aggressive ships a
        # four-bullet full-time role against a floor of five, fullstack_strict a
        # two-bullet internship against a floor of three. The engine cannot lift
        # those and must not make them worse, so the promise it can actually
        # keep is "never below the floor, and never below where it started".
        # See TestGenerationCanArriveBelowAFloor.
        resume = _load(name)
        _, result = _revise(resume, tmp_path)
        delivered = result.resume

        assert len(delivered.projects) >= min(floors.MIN_PROJECTS, len(resume.projects))
        assert delivered.total_skills() >= min(floors.MIN_TOTAL_SKILLS, resume.total_skills())
        assert len(delivered.experiences) == floors.REQUIRED_EXPERIENCES

        for project in delivered.projects:
            started_at = next(p for p in resume.projects if p.id == project.id)
            assert len(project.highlights) >= min(
                floors.PROJECT_BULLET_FLOOR, len(started_at.highlights)
            )
        for experience in delivered.experiences:
            started_at = next(e for e in resume.experiences if e.id == experience.id)
            assert len(experience.highlights) >= min(
                floors.experience_bullet_floor(experience), len(started_at.highlights)
            )

    @pytest.mark.parametrize("name", LIVE_RUNS)
    def test_no_unit_is_trimmed_below_its_floor_by_the_engine(self, name, tmp_path):
        """Anything that started at or above its floor still is."""
        resume = _load(name)
        _, result = _revise(resume, tmp_path)
        for experience in result.resume.experiences:
            floor = floors.experience_bullet_floor(experience)
            started_at = next(e for e in resume.experiences if e.id == experience.id)
            if len(started_at.highlights) >= floor:
                assert len(experience.highlights) >= floor
        for project in result.resume.projects:
            started_at = next(p for p in resume.projects if p.id == project.id)
            if len(started_at.highlights) >= floors.PROJECT_BULLET_FLOOR:
                assert len(project.highlights) >= floors.PROJECT_BULLET_FLOOR

    @pytest.mark.parametrize("name", LIVE_RUNS)
    def test_nothing_immutable_changed(self, name, tmp_path):
        resume = _load(name)
        _, result = _revise(resume, tmp_path)
        assert result.resume.summary == resume.summary
        assert result.resume.contact == resume.contact
        assert result.resume.education == resume.education
        assert result.resume.metadata == resume.metadata


class TestTheDeliveredArtifacts:
    """A caller must be able to find and open what the engine produced."""

    def test_the_final_pdf_exists_and_is_a_pdf(self, tmp_path):
        _, result = _revise(_load("backend_aggressive"), tmp_path)
        with open(result.pdf_path, "rb") as handle:
            assert handle.read(5) == b"%PDF-"

    def test_the_final_tex_exists(self, tmp_path):
        _, result = _revise(_load("backend_aggressive"), tmp_path)
        with open(result.tex_path, encoding="utf-8") as handle:
            assert r"\begin{document}" in handle.read()

    def test_the_trail_records_every_removal(self, tmp_path):
        _, result = _revise(_load("backend_aggressive"), tmp_path)
        with open(result.trail_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        assert len(payload["steps"]) == len(result.trail)
        assert all(step["reason"] for step in payload["steps"])

    def test_the_trail_names_the_entity_each_step_touched(self, tmp_path):
        _, result = _revise(_load("backend_aggressive"), tmp_path)
        for step in result.trail:
            if step.action is not RevisionAction.COMPRESS_BULLETS:
                assert step.entity_id


class TestTrimmingIsCoarserThanOneLinePerBullet:
    """
    Task 016 measured spill going 7 -> 7 -> 0 against real artifacts: the
    subheading blocks move as a unit rather than reflowing line by line. This
    pins the consequence — the loop must be driven by the recompiled verdict,
    never by the line estimates.
    """

    def test_at_least_one_removal_frees_no_lines_at_all(self, tmp_path):
        _, result = _revise(_load("backend_aggressive"), tmp_path)
        spills = [step.spill for step in result.trail]
        assert len(spills) > 1
        assert any(
            later == earlier for earlier, later in zip(spills, spills[1:])
        ), "expected at least one step to change nothing: {0}".format(spills)


class TestGenerationCanArriveBelowAFloor:
    """
    A real gap, found by this suite and worth keeping visible.

    The retention floors govern *trimming*. Nothing in the Generator knows
    about them, so a generated resume can arrive already below one — and the
    Revision Engine can only decline to make it worse, never lift it. Closing
    the gap belongs to generation, exactly as bullet length and summary length
    were closed there rather than at revision time.
    """

    def test_a_live_run_arrives_below_the_full_time_floor(self):
        resume = _load("cybersecurity_aggressive")
        full_time = next(e for e in resume.experiences if not floors.is_internship(e))
        assert len(full_time.highlights) < floors.FULLTIME_BULLET_FLOOR

    def test_a_live_run_arrives_below_the_internship_floor(self):
        resume = _load("fullstack_strict")
        internship = next(e for e in resume.experiences if floors.is_internship(e))
        assert len(internship.highlights) < floors.INTERNSHIP_BULLET_FLOOR

    def test_the_engine_declines_to_trim_a_unit_already_below_its_floor(self, tmp_path):
        resume = _load("cybersecurity_aggressive")
        before = len(next(e for e in resume.experiences if not floors.is_internship(e)).highlights)
        _, result = _revise(resume, tmp_path)
        after = len(next(e for e in result.resume.experiences if not floors.is_internship(e)).highlights)
        assert after == before
