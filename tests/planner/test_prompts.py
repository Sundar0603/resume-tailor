"""
Unit tests for planner prompt construction.

Covers PII exclusion, byte-identical determinism, and the brace-doubling
that keeps the JSON schema skeleton intact through ``str.format``.
"""

from src.planner.models import PlanningMode
from src.planner.prompts import build_planning_prompt

from .conftest import make_job_analysis, make_resume


class TestResumeProjection:

    def test_prompt_contains_entity_ids(self):
        prompt = build_planning_prompt(make_resume(), make_job_analysis())
        assert "exp_001" in prompt
        assert "exp_002" in prompt
        assert "proj_001" in prompt
        assert "proj_002" in prompt
        assert "skill_001" in prompt
        assert "skill_002" in prompt

    def test_prompt_excludes_pii(self):
        prompt = build_planning_prompt(make_resume(), make_job_analysis())
        resume = make_resume()
        assert resume.contact.email not in prompt
        assert resume.contact.phone not in prompt
        assert resume.contact.name not in prompt

    def test_prompt_excludes_education(self):
        prompt = build_planning_prompt(make_resume(), make_job_analysis())
        assert "edu_001" not in prompt


class TestDeterminism:

    def test_prompt_is_byte_identical_across_builds(self):
        resume = make_resume()
        analysis = make_job_analysis()
        first = build_planning_prompt(resume, analysis)
        second = build_planning_prompt(resume, analysis)
        assert first == second

    def test_mode_changes_the_prompt(self):
        resume = make_resume()
        analysis = make_job_analysis()
        aggressive = build_planning_prompt(resume, analysis, PlanningMode.AGGRESSIVE)
        strict = build_planning_prompt(resume, analysis, PlanningMode.STRICT)
        assert aggressive != strict
        assert "GENERATE is forbidden" in strict


class TestBraceDoubling:

    def test_schema_skeleton_survived_formatting(self):
        prompt = build_planning_prompt(make_resume(), make_job_analysis())
        assert '"summary_plan": {' in prompt
        assert "{{" not in prompt
        assert "}}" not in prompt
