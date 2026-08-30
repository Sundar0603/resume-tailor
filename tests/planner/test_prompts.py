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
    Both modes carry an entry manifest, and each carries its own.

    Originally strict-only. Measured on cybersecurity_resume against the
    application-developer JD, 4 trials per condition:

        mode          without manifest   with STRICT manifest
        STRICT             0/4               4/4
        AGGRESSIVE         4/4               0/4

    That reading — "aggressive needs no manifest" — was true of the pairing it
    was measured on and false in general. The first real end-to-end run found
    aggressive failing 0/4 on backend+backend with the same shape bleed, so it
    now gets a manifest of its own. Re-measured across three pairings, before
    and after, 4 trials each:

        pairing        mode         before   after
        backend        STRICT          4/4     4/4
        backend        AGGRESSIVE      0/4     4/4
        cyber+appdev   STRICT          4/4     4/4
        cyber+appdev   AGGRESSIVE      4/4     4/4
        fullstack      STRICT          4/4     4/4
        fullstack      AGGRESSIVE      4/4     4/4

    The strict prompt is byte-identical before and after; the aggressive one
    differs by a pure insertion of its manifest. See the comments above
    ``_ENTRY_MANIFEST_TEMPLATE`` and ``_AGGRESSIVE_ENTRY_MANIFEST_TEMPLATE``.
    """

    def test_strict_prompts_carry_the_manifest(self):
        resume, analysis = make_resume(), make_job_analysis()
        prompt = build_planning_prompt(resume, analysis, PlanningMode.STRICT)
        assert "Entry manifest for THIS resume" in prompt

    def test_aggressive_prompts_carry_one_too(self):
        resume, analysis = make_resume(), make_job_analysis()
        prompt = build_planning_prompt(resume, analysis, PlanningMode.AGGRESSIVE)
        assert "Entry manifest for THIS resume" in prompt

    def test_the_aggressive_manifest_leaves_room_for_generate(self):
        # Forcing the *strict* manifest on aggressive stops the bleed but fails
        # a different way: "one entry per id, in this order" leaves nowhere to
        # put a GENERATE entry, so the model attaches a real id to one and
        # trips "GENERATE requires project_id to be null" (0/4). The aggressive
        # manifest must say where a new entry goes.
        resume, analysis = make_resume(), make_job_analysis()
        prompt = build_planning_prompt(resume, analysis, PlanningMode.AGGRESSIVE)
        assert '"project_id": null' in prompt
        assert '"category_id": null' in prompt
        assert "append" in prompt

    def test_the_aggressive_manifest_still_pins_experiences(self):
        # Experiences can never be added, removed or reordered, in any mode.
        resume, analysis = make_resume(), make_job_analysis()
        prompt = build_planning_prompt(resume, analysis, PlanningMode.AGGRESSIVE)
        assert "EXACTLY {} entries".format(len(resume.experiences)) in prompt
        assert "Never append to this array" in prompt

    def test_neither_prompt_has_a_stray_blank_line(self):
        # One extra blank line changed greedy output enough to invert an A/B
        # result during development, so this is pinned rather than trusted.
        resume, analysis = make_resume(), make_job_analysis()
        for mode in (PlanningMode.STRICT, PlanningMode.AGGRESSIVE):
            prompt = build_planning_prompt(resume, analysis, mode)
            assert "\n\n\nReturn ONLY" not in prompt
            assert "\n\n\nEntry manifest" not in prompt

    def test_the_aggressive_manifest_names_every_entity_id(self):
        resume = make_resume()
        prompt = build_planning_prompt(
            resume, make_job_analysis(), PlanningMode.AGGRESSIVE
        )
        manifest = prompt[prompt.index("Entry manifest") :]
        for group in (resume.skills, resume.experiences, resume.projects):
            for entity in group:
                assert entity.id in manifest

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
