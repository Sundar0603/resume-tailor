"""
Determinism, and where it deliberately stops.

Given the same source resume, current resume, quality result and configuration,
every deterministic removal decision must be identical. The LLM compression
step is the only intentionally non-deterministic part of the process — and even
there, protected-fact extraction and verification are deterministic, because
they are what stands between the model and the resume.
"""

import ast
import pathlib

from src.revision import compression, deletion, facts, measure
from src.revision.prompts import build_compression_prompt

from .conftest import (
    CountingGate,
    StubCompiler,
    failing_result,
    make_bullet,
    make_resume,
)

SOURCE_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "revision"

#: The modules that must stay pure: no provider, no network, no I/O. The
#: engine itself is excluded — it owns the artifacts and the one LLM call.
PURE_MODULES = ("deletion.py", "floors.py", "measure.py", "facts.py", "models.py")


def _big_resume():
    """Return a resume with room to trim in every section."""
    return make_resume(
        project_bullets=(5, 4, 4), skill_sizes=(6, 5, 5), fulltime_bullets=9, intern_bullets=6
    )


class TestTheDeletionPolicyIsDeterministic:
    """The same resume always yields the same sequence."""

    def test_the_same_resume_yields_the_same_next_step(self):
        first = deletion.next_removal(_big_resume())
        second = deletion.next_removal(_big_resume())
        assert first == second

    def test_the_same_resume_yields_the_same_whole_plan(self):
        first = deletion.removal_plan(_big_resume())
        second = deletion.removal_plan(_big_resume())
        assert first == second

    def test_freeable_lines_is_stable(self):
        assert deletion.freeable_lines(_big_resume()) == deletion.freeable_lines(_big_resume())

    def test_the_plan_does_not_depend_on_call_history(self):
        resume = _big_resume()
        deletion.removal_plan(resume)
        deletion.freeable_lines(resume)
        assert deletion.removal_plan(resume) == deletion.removal_plan(_big_resume())


class TestTheEngineIsDeterministic:
    """Two identical runs produce identical resumes and identical trails."""

    def _run(self, tmp_path, name):
        from src.revision import RevisionEngine

        resume = _big_resume()
        engine = RevisionEngine(
            compiler=StubCompiler(), quality_gate=CountingGate(40)
        )
        return engine.revise(
            source_resume=resume,
            current_resume=resume,
            quality_result=failing_result(),
            output_directory=str(tmp_path / name),
        )

    def test_two_runs_deliver_the_same_resume(self, tmp_path):
        first = self._run(tmp_path, "a")
        second = self._run(tmp_path, "b")
        assert first.resume == second.resume

    def test_two_runs_take_the_same_steps(self, tmp_path):
        first = self._run(tmp_path, "a")
        second = self._run(tmp_path, "b")
        assert first.trail == second.trail

    def test_two_runs_take_the_same_number_of_attempts(self, tmp_path):
        assert self._run(tmp_path, "a").attempts == self._run(tmp_path, "b").attempts

    def test_the_result_carries_no_wall_clock_field(self):
        from src.revision.models import RevisionResult

        # A duration would break first == second on every run, exactly as it
        # would for QualityGateResult.
        assert "duration_seconds" not in RevisionResult.model_fields


class TestFactHandlingIsDeterministic:
    """The guard between the model and the resume cannot itself be flaky."""

    def test_the_lexicon_is_stable(self):
        assert facts.build_lexicon(_big_resume()) == facts.build_lexicon(_big_resume())

    def test_extraction_is_stable(self):
        bullet = "Built Redis caching with Spring Boot, cutting API latency by 40%."
        lexicon = facts.build_lexicon(_big_resume())
        assert facts.extract_protected_facts(bullet, lexicon) == facts.extract_protected_facts(
            bullet, lexicon
        )

    def test_verification_is_stable(self):
        from src.revision.models import ProtectedFacts

        found = ProtectedFacts(numerics=["40%"], terms=["Redis"])
        assert facts.verify(found, "Cut latency 40%.") == facts.verify(found, "Cut latency 40%.")


class TestSelectionAndPromptsAreDeterministic:
    """The model receives byte-identical input for identical state."""

    def _resume(self):
        resume = make_resume(bullet_words=30, project_bullets=(3, 3))
        resume.projects[1].highlights[2] = make_bullet("Built Redis caching cutting latency by 40%", 30)
        return resume

    def test_selection_is_stable(self):
        first = compression.select_candidates(self._resume(), 3)
        second = compression.select_candidates(self._resume(), 3)
        assert first == second

    def test_the_prompt_is_byte_identical(self):
        first = build_compression_prompt(compression.select_candidates(self._resume(), 3))
        second = build_compression_prompt(compression.select_candidates(self._resume(), 3))
        assert first == second


class TestMeasurementIsPure:
    """No hidden state anywhere in the estimates."""

    def test_line_estimates_are_stable(self):
        text = make_bullet("Built", 30)
        assert measure.estimated_lines(text) == measure.estimated_lines(text)

    def test_the_resume_estimate_is_stable(self):
        assert measure.estimated_resume_lines(_big_resume()) == measure.estimated_resume_lines(
            _big_resume()
        )


class TestThePureModulesStayPure:
    """
    Enforced structurally, not by convention. The deletion policy has to remain
    callable in a unit test with no provider, no network and no TeX.
    """

    def _imports(self, filename):
        tree = ast.parse((SOURCE_DIR / filename).read_text(encoding="utf-8"))
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            elif isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
        return names

    def test_the_pure_modules_import_no_provider(self):
        forbidden = ("src.providers", "src.analyzer.provider", "src.generator", "src.planner")
        for filename in PURE_MODULES:
            for name in self._imports(filename):
                assert not name.startswith(forbidden), "{0} imports {1}".format(filename, name)

    def test_the_pure_modules_make_no_network_calls(self):
        forbidden = ("requests", "urllib", "http", "socket", "openai", "anthropic")
        for filename in PURE_MODULES:
            for name in self._imports(filename):
                assert not name.startswith(forbidden), "{0} imports {1}".format(filename, name)

    def test_the_deletion_policy_touches_no_filesystem(self):
        forbidden = ("pathlib", "shutil", "tempfile", "subprocess", "os")
        for filename in ("deletion.py", "floors.py", "measure.py", "facts.py"):
            for name in self._imports(filename):
                assert not name.startswith(forbidden), "{0} imports {1}".format(filename, name)

    def test_the_prompt_module_builds_prompts_and_nothing_else(self):
        forbidden = ("src.providers", "src.analyzer.provider", "pathlib", "shutil", "subprocess")
        for name in self._imports("prompts.py"):
            assert not name.startswith(forbidden), "prompts.py imports {0}".format(name)


class TestFloorsAreNotDuplicated:
    """
    Every floor literal lives in floors.py. A second copy is how a policy
    change silently half-lands.
    """

    def test_no_other_module_hard_codes_a_floor(self):
        offenders = []
        for path in SOURCE_DIR.glob("*.py"):
            if path.name in ("floors.py", "__init__.py"):
                continue
            source = path.read_text(encoding="utf-8")
            for token in ("MIN_PROJECTS", "PROJECT_BULLET_FLOOR", "MIN_TOTAL_SKILLS",
                          "INTERNSHIP_BULLET_FLOOR", "FULLTIME_BULLET_FLOOR"):
                if "{0} =".format(token) in source:
                    offenders.append("{0}:{1}".format(path.name, token))
        assert offenders == []
