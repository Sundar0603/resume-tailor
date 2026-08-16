"""
Tests for the strict-mode fabrication checks.

The ResumeValidator cannot see these violations: technologies and skills are
mutable by design, so it has no basis for calling one invented. That is the gap
``src/generator/constraints.py`` closes, and these tests are the only thing
standing between "the prompt asked nicely" and "the rule is enforced".
"""

import pytest

from src.generator import (
    GenerationConstraintError,
    ResumeGenerator,
    enforce_strict,
    source_numbers,
    source_vocabulary,
)
from src.parser.models import SkillCategory

from .conftest import (
    projects_response,
    SequencedProvider,
    experience_entry,
    experiences_response,
    make_job_analysis,
    make_plan,
    make_resume,
)


class TestSourceVocabulary:
    def test_includes_structured_terms(self):
        vocabulary = source_vocabulary(make_resume())
        assert "python" in vocabulary
        assert "aws" in vocabulary
        assert "docker" in vocabulary

    def test_includes_words_from_prose(self):
        # "payments" appears only in the summary and a highlight, never as a
        # structured term. A technology named in a bullet is still supported.
        vocabulary = source_vocabulary(make_resume())
        assert "payments" in vocabulary

    def test_is_case_insensitive(self):
        vocabulary = source_vocabulary(make_resume())
        assert "python" in vocabulary
        assert "Python" not in vocabulary

    def test_excludes_absent_terms(self):
        vocabulary = source_vocabulary(make_resume())
        assert "kubernetes" not in vocabulary


class TestSourceNumbers:
    def test_finds_plain_and_percentage_numbers(self):
        numbers = source_numbers(make_resume())
        assert "10000" in numbers
        assert "30%" in numbers

    def test_normalises_thousands_separators(self):
        resume = make_resume()
        resume.experiences[1].highlights = ["Served 1,200 requests per second."]
        assert "1200" in source_numbers(resume)


class TestTermEnforcement:
    def test_supported_terms_pass(self):
        source = make_resume()
        generated = source.model_copy(deep=True)
        generated.experiences[1].technologies = ["Python", "Go"]
        enforce_strict(source, generated)

    def test_new_technology_is_rejected(self):
        source = make_resume()
        generated = source.model_copy(deep=True)
        generated.experiences[1].technologies = ["Python", "Kubernetes"]
        with pytest.raises(GenerationConstraintError):
            enforce_strict(source, generated)

    def test_new_skill_is_rejected(self):
        source = make_resume()
        generated = source.model_copy(deep=True)
        generated.skills.append(
            SkillCategory(id="skill_003", category="Orchestration", skills=["Helm"])
        )
        with pytest.raises(GenerationConstraintError):
            enforce_strict(source, generated)

    def test_new_domain_is_rejected(self):
        source = make_resume()
        generated = source.model_copy(deep=True)
        generated.projects[0].domains = ["Machine Learning"]
        with pytest.raises(GenerationConstraintError):
            enforce_strict(source, generated)

    def test_compound_term_of_supported_words_passes(self):
        # "Python tooling" is fine when both words appear in the source.
        source = make_resume()
        generated = source.model_copy(deep=True)
        generated.projects[0].domains = ["Python Tooling"]
        enforce_strict(source, generated)

    def test_error_names_the_offending_term(self):
        source = make_resume()
        generated = source.model_copy(deep=True)
        generated.experiences[1].technologies = ["Kubernetes"]
        with pytest.raises(GenerationConstraintError) as exc:
            enforce_strict(source, generated)
        assert "Kubernetes" in str(exc.value)


class TestMetricEnforcement:
    def test_reused_metric_passes(self):
        source = make_resume()
        generated = source.model_copy(deep=True)
        generated.experiences[1].highlights = [
            "Cut API latency by 30% through query optimization."
        ]
        enforce_strict(source, generated)

    def test_fabricated_metric_is_rejected(self):
        source = make_resume()
        generated = source.model_copy(deep=True)
        generated.experiences[1].highlights = [
            "Cut API latency by 45% through query optimization."
        ]
        with pytest.raises(GenerationConstraintError):
            enforce_strict(source, generated)

    def test_fabricated_metric_in_the_summary_is_rejected(self):
        source = make_resume()
        generated = source.model_copy(deep=True)
        generated.summary = source.summary + " Delivered 99.9% uptime."
        with pytest.raises(GenerationConstraintError):
            enforce_strict(source, generated)

    def test_small_numbers_are_tolerated(self):
        # "three services" becoming "3 services" is a rephrasing, not a
        # fabrication. Flagging it produces more noise than it prevents.
        source = make_resume()
        generated = source.model_copy(deep=True)
        generated.experiences[1].highlights = ["Owned 3 backend services."]
        enforce_strict(source, generated)

    def test_thousands_separator_variation_passes(self):
        source = make_resume()
        generated = source.model_copy(deep=True)
        generated.experiences[1].highlights = [
            "Shipped a payments service handling 10,000 requests per second."
        ]
        enforce_strict(source, generated)

    def test_error_names_the_offending_number(self):
        source = make_resume()
        generated = source.model_copy(deep=True)
        generated.experiences[1].highlights = ["Cut latency by 45%."]
        with pytest.raises(GenerationConstraintError) as exc:
            enforce_strict(source, generated)
        assert "45%" in str(exc.value)


class TestAggressiveModeSkipsChecks:
    def _rewrite_plan(self, mode):
        return make_plan(
            mode=mode,
            experience_plans=[
                {
                    "experience_id": "exp_001",
                    "action": "KEEP",
                    "priority": "LOW",
                    "rewrite_strategy": None,
                    "keywords_to_include": [],
                    "themes_to_emphasize": [],
                    "reasoning": "Less relevant.",
                },
                {
                    "experience_id": "exp_002",
                    "action": "REWRITE",
                    "priority": "CRITICAL",
                    "rewrite_strategy": "Lead with scale.",
                    "keywords_to_include": [],
                    "themes_to_emphasize": [],
                    "reasoning": "Closest match.",
                },
            ],
        )

    def _fabricating_response(self):
        return experiences_response(
            experience_entry(
                "exp_002",
                technologies=["Kubernetes"],
                highlights=["Cut deployment time by 75%."],
            )
        )

    def test_aggressive_permits_a_job_technology_and_new_metrics(self):
        # Kubernetes is in the job description but not the resume. Aggressive
        # tailoring is exactly what that case is for.
        generator = ResumeGenerator(
            SequencedProvider([self._fabricating_response()])
        )
        result = generator.generate(
            source_resume=make_resume(),
            job_analysis=make_job_analysis(),
            resume_plan=self._rewrite_plan("AGGRESSIVE"),
        )
        assert "Kubernetes" in result.experiences[1].technologies
        assert "75%" in result.experiences[1].highlights[0]

    def test_aggressive_refuses_a_technology_in_neither_resume_nor_job(self):
        # "Jest" reached a real generated resume this way: named nowhere in the
        # source and nowhere in the job. That is invention, not tailoring.
        source = make_resume()
        generator = ResumeGenerator(
            SequencedProvider(
                [
                    experiences_response(
                        experience_entry(
                            "exp_002",
                            technologies=["Jest"],
                            highlights=["Shipped a payments service."],
                        )
                    )
                ]
            )
        )
        result = generator.generate(
            source_resume=source,
            job_analysis=make_job_analysis(),
            resume_plan=self._rewrite_plan("AGGRESSIVE"),
        )
        assert "Jest" not in result.experiences[1].technologies
        assert result.experiences[1].technologies == source.experiences[1].technologies

    def test_strict_filters_an_unsupported_technology(self):
        # Terms are filtered rather than raised on. enforce_strict would kill a
        # 65-second generation over one vague label the model lifted from the
        # job description; strict mode explicitly permits reordering and
        # subsetting what the resume already says, so that is what happens.
        generator = ResumeGenerator(
            SequencedProvider(
                [
                    experiences_response(
                        experience_entry(
                            "exp_002",
                            technologies=["Python", "Kubernetes"],
                            highlights=["Shipped a payments service."],
                        )
                    )
                ]
            )
        )
        source = make_resume()
        result = generator.generate(
            source_resume=source,
            job_analysis=make_job_analysis(),
            resume_plan=self._rewrite_plan("STRICT"),
        )
        # Kubernetes is refused, so the resume's own technologies are retained
        # alongside what survived rather than the field being thinned.
        assert result.experiences[1].technologies == ["Python", "Go"]

    def test_strict_falls_back_when_filtering_would_empty(self):
        # The validator rejects an experience with no technologies, so an
        # entirely unsupported list falls back to the source's own.
        source = make_resume()
        generator = ResumeGenerator(
            SequencedProvider(
                [
                    experiences_response(
                        experience_entry(
                            "exp_002",
                            technologies=["Kubernetes", "Helm"],
                            highlights=["Shipped a payments service."],
                        )
                    )
                ]
            )
        )
        result = generator.generate(
            source_resume=source,
            job_analysis=make_job_analysis(),
            resume_plan=self._rewrite_plan("STRICT"),
        )
        assert result.experiences[1].technologies == source.experiences[1].technologies

    def test_strict_preserves_the_models_ordering(self):
        # Re-emphasising by reordering is exactly what strict mode allows.
        generator = ResumeGenerator(
            SequencedProvider(
                [
                    experiences_response(
                        experience_entry(
                            "exp_002",
                            technologies=["Go", "Python"],
                            highlights=["Shipped a payments service."],
                        )
                    )
                ]
            )
        )
        result = generator.generate(
            source_resume=make_resume(),
            job_analysis=make_job_analysis(),
            resume_plan=self._rewrite_plan("STRICT"),
        )
        assert result.experiences[1].technologies == ["Go", "Python"]

    def _domains_after(self, mode, domains):
        generator = ResumeGenerator(
            SequencedProvider(
                [
                    experiences_response(
                        experience_entry(
                            "exp_002",
                            domains=domains,
                            highlights=["Shipped a payments service."],
                        )
                    )
                ]
            )
        )
        result = generator.generate(
            source_resume=make_resume(),
            job_analysis=make_job_analysis(),
            resume_plan=self._rewrite_plan(mode),
        )
        return result.experiences[1].domains

    def test_process_language_never_replaces_a_real_domain(self):
        # The source has Backend and Cloud. A job written entirely in process
        # language offers no competitor for the slot, so the resume keeps what
        # it had rather than trading it for phrases that say nothing.
        source = make_resume()
        after = self._domains_after(
            "AGGRESSIVE",
            ["Application Software Development", "Code Quality", "Defect Handling"],
        )
        assert after == source.experiences[1].domains

    def test_a_genuinely_specific_domain_does_replace(self):
        # When a job names a real domain, the swap is the whole point of
        # tailoring and goes ahead.
        after = self._domains_after("AGGRESSIVE", ["Payments", "Backend"])
        assert after == ["Payments", "Backend"]

    def test_a_partial_refusal_retains_the_source_terms(self):
        # One refusal means the model's judgement was declined for that term,
        # so the resume's own domains come back alongside the survivors.
        # Without this, six empty phrases and one thin real one would leave the
        # field holding only the thin one — worse than either the original or
        # a clean swap.
        source = make_resume()
        after = self._domains_after("AGGRESSIVE", ["Payments", "Code Quality"])
        assert after[:1] == ["Payments"]
        assert after[1:] == source.experiences[1].domains

    def test_an_unrefused_response_replaces_outright(self):
        # Nothing refused means the model is trusted completely, which is what
        # keeps genuine retargeting possible. Both terms are in the source
        # prose, so both pass.
        after = self._domains_after("AGGRESSIVE", ["Payments", "Backend"])
        assert after == ["Payments", "Backend"]

    def test_a_source_domain_is_kept_even_if_generic(self):
        # The candidate's own wording is theirs. The filter judges proposed
        # replacements, never what the resume already says.
        source = make_resume()
        source.experiences[1].domains = ["System Maintenance"]
        generator = ResumeGenerator(
            SequencedProvider(
                [
                    experiences_response(
                        experience_entry(
                            "exp_002",
                            domains=["System Maintenance"],
                            highlights=["Shipped a payments service."],
                        )
                    )
                ]
            )
        )
        result = generator.generate(
            source_resume=source,
            job_analysis=make_job_analysis(),
            resume_plan=self._rewrite_plan("AGGRESSIVE"),
        )
        assert result.experiences[1].domains == ["System Maintenance"]

    def test_generic_technologies_are_also_refused(self):
        source = make_resume()
        generator = ResumeGenerator(
            SequencedProvider(
                [
                    experiences_response(
                        experience_entry(
                            "exp_002",
                            technologies=["App Services", "Software Systems"],
                            highlights=["Shipped a payments service."],
                        )
                    )
                ]
            )
        )
        result = generator.generate(
            source_resume=source,
            job_analysis=make_job_analysis(),
            resume_plan=self._rewrite_plan("AGGRESSIVE"),
        )
        assert (
            result.experiences[1].technologies
            == source.experiences[1].technologies
        )

    def test_a_generated_project_also_refuses_weak_terms(self):
        # A generated project has no source terms to fall back on, so weak
        # ones are simply dropped rather than substituted.
        plan = make_plan(
            mode="AGGRESSIVE",
            project_plans=[
                {
                    "project_id": "proj_001",
                    "action": "KEEP",
                    "priority": "MEDIUM",
                    "rewrite_strategy": None,
                    "generation_brief": None,
                    "keywords_to_include": [],
                    "themes_to_emphasize": [],
                    "reasoning": "Still relevant.",
                },
                {
                    "project_id": "proj_002",
                    "action": "KEEP",
                    "priority": "MEDIUM",
                    "rewrite_strategy": None,
                    "generation_brief": None,
                    "keywords_to_include": [],
                    "themes_to_emphasize": [],
                    "reasoning": "Still relevant.",
                },
                {
                    "project_id": None,
                    "action": "GENERATE",
                    "priority": "HIGH",
                    "rewrite_strategy": None,
                    "generation_brief": "A cloud platform demo.",
                    "keywords_to_include": [],
                    "themes_to_emphasize": [],
                    "reasoning": "The job mentions OCI.",
                },
            ],
        )
        generator = ResumeGenerator(
            SequencedProvider(
                [
                    projects_response(
                        {
                            "project_id": None,
                            "name": "Cloud Platform",
                            "type": "Personal",
                            "technologies": ["Kubernetes", "App Services", "Python"],
                            "domains": ["Code Quality"],
                            "highlights": ["Built a cloud platform."],
                        }
                    )
                ]
            )
        )
        result = generator.generate(
            source_resume=make_resume(),
            job_analysis=make_job_analysis(),
            resume_plan=plan,
        )
        # Positions follow priority order now, so select by source.
        generated = next(
            p for p in result.projects if p.source.value == "GENERATED"
        )
        assert generated.technologies == ["Kubernetes", "Python"]
        assert generated.domains == []

    def test_aggressive_keeps_source_and_job_terms_together(self):
        generator = ResumeGenerator(
            SequencedProvider(
                [
                    experiences_response(
                        experience_entry(
                            "exp_002",
                            technologies=["Python", "Kubernetes"],
                            highlights=["Shipped a payments service."],
                        )
                    )
                ]
            )
        )
        result = generator.generate(
            source_resume=make_resume(),
            job_analysis=make_job_analysis(),
            resume_plan=self._rewrite_plan("AGGRESSIVE"),
        )
        # Python from the resume, Kubernetes from the job.
        assert result.experiences[1].technologies == ["Python", "Kubernetes"]

    def test_strict_still_raises_on_a_fabricated_metric(self):
        generator = ResumeGenerator(
            SequencedProvider([self._fabricating_response()])
        )
        with pytest.raises(GenerationConstraintError):
            generator.generate(
                source_resume=make_resume(),
                job_analysis=make_job_analysis(),
                resume_plan=self._rewrite_plan("STRICT"),
            )
