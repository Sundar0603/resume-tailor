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


class TestEntryManifest:
    """
    The strict-mode entry manifest, and the whitespace boundary around it.

    Measured on cybersecurity_resume against the application-developer JD,
    4 trials per condition against one fixed JobAnalysis:

        mode          without manifest   with manifest
        STRICT             0/4               4/4
        AGGRESSIVE         4/4               0/4

    Hence strict-only. See the comment above ``_ENTRY_MANIFEST_TEMPLATE``.
    """

    def test_strict_prompts_carry_the_manifest(self):
        resume, analysis = make_resume(), make_job_analysis()
        prompt = build_planning_prompt(resume, analysis, PlanningMode.STRICT)
        assert "Entry manifest for THIS resume" in prompt

    def test_aggressive_prompts_do_not(self):
        resume, analysis = make_resume(), make_job_analysis()
        prompt = build_planning_prompt(resume, analysis, PlanningMode.AGGRESSIVE)
        assert "Entry manifest" not in prompt

    def test_the_aggressive_prompt_has_no_stray_blank_line(self):
        # The manifest slot must contribute exactly nothing in aggressive mode.
        # One extra blank line changed greedy output enough to invert an A/B
        # result during development, so this is pinned rather than trusted.
        resume, analysis = make_resume(), make_job_analysis()
        prompt = build_planning_prompt(resume, analysis, PlanningMode.AGGRESSIVE)
        assert "</job_analysis>\n\nReturn ONLY" in prompt
        assert "\n\n\nReturn ONLY" not in prompt

    def test_the_manifest_names_every_entity_id(self):
        resume = make_resume()
        prompt = build_planning_prompt(resume, make_job_analysis(), PlanningMode.STRICT)
        manifest = prompt[prompt.index("Entry manifest") :]
        for group in (resume.skills, resume.experiences, resume.projects):
            for entity in group:
                assert entity.id in manifest

    def test_the_manifest_states_the_exact_experience_count(self):
        resume = make_resume()
        prompt = build_planning_prompt(resume, make_job_analysis(), PlanningMode.STRICT)
        assert "EXACTLY {} entries".format(len(resume.experiences)) in prompt

    def test_the_manifest_is_deterministic(self):
        resume, analysis = make_resume(), make_job_analysis()
        left = build_planning_prompt(resume, analysis, PlanningMode.STRICT)
        right = build_planning_prompt(resume, analysis, PlanningMode.STRICT)
        assert left == right
