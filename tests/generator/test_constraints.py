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

    def test_aggressive_permits_new_technologies_and_metrics(self):
        generator = ResumeGenerator(
            SequencedProvider([self._fabricating_response()])
        )
        result = generator.generate(
            source_resume=make_resume(),
            job_analysis=make_job_analysis(),
            resume_plan=self._rewrite_plan("AGGRESSIVE"),
        )
        assert "Kubernetes" in result.experiences[1].technologies

    def test_strict_rejects_the_same_response(self):
        generator = ResumeGenerator(
            SequencedProvider([self._fabricating_response()])
        )
        with pytest.raises(GenerationConstraintError):
            generator.generate(
                source_resume=make_resume(),
                job_analysis=make_job_analysis(),
                resume_plan=self._rewrite_plan("STRICT"),
            )
