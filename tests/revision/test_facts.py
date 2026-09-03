"""
Protected-fact extraction and verification.

The tables here are copied from ``tasks/017-revision-engine.md`` — the numbers,
technologies and named facts it names explicitly, and every accept/reject pair
it gives. Extraction happens in Python before the call and verification in
Python after it, because "the LLM response must never be trusted solely because
it followed the prompt."
"""

from src.revision import facts
from src.revision.models import ProtectedFacts

from .conftest import make_resume


def _lexicon():
    """Return a lexicon built from a resume naming the usual technologies."""
    resume = make_resume()
    resume.projects[0].technologies = [
        "Python",
        "Redis",
        "Spring Boot",
        "PostgreSQL",
        "Docker",
        "Kubernetes",
        "Java",
    ]
    return facts.build_lexicon(resume)


class TestTheLexicon:
    """Built from the resume itself, which is the only lexicon that cannot go stale."""

    def test_it_collects_skills_technologies_domains_and_project_names(self):
        resume = make_resume()
        lexicon = facts.build_lexicon(resume)
        assert "Redis" in lexicon
        assert "Docker" in lexicon
        assert "Backend Development" in lexicon
        assert "Project 1" in lexicon

    def test_longer_terms_come_first(self):
        lexicon = _lexicon()
        assert lexicon.index("Spring Boot") < lexicon.index("Redis")

    def test_duplicates_are_dropped(self):
        resume = make_resume()
        resume.projects[0].technologies = ["Redis", "redis", "REDIS"]
        assert sum(1 for t in facts.build_lexicon(resume) if t.casefold() == "redis") == 1

    def test_very_short_terms_are_not_protected(self):
        resume = make_resume()
        resume.projects[0].technologies = ["Go", "C", "Redis"]
        lexicon = facts.build_lexicon(resume)
        assert "Go" not in lexicon
        assert "Redis" in lexicon


class TestNumericExtraction:
    """Every shape the task doc names."""

    def test_a_percentage(self):
        assert facts.extract_numerics("Cut latency by 40% overall.") == ["40%"]

    def test_a_count_with_a_plus(self):
        assert facts.extract_numerics("Served 500+ users.") == ["500+"]

    def test_a_multiplier(self):
        assert facts.extract_numerics("Improved throughput 3x.") == ["3x"]

    def test_a_fractional_percentage(self):
        assert facts.extract_numerics("Held 99.9% uptime.") == ["99.9%"]

    def test_a_duration_with_a_unit(self):
        assert facts.extract_numerics("Responded in 30 ms.") == ["30 ms"]

    def test_a_version_number(self):
        assert facts.extract_numerics("Shipped v2.1 of the service.") == ["v2.1"]

    def test_a_bare_year(self):
        assert facts.extract_numerics("Delivered in 2025.") == ["2025"]

    def test_several_facts_in_one_bullet(self):
        found = facts.extract_numerics("Cut 30 ms to 12 ms for 500+ users, a 60% gain.")
        assert found == ["30 ms", "12 ms", "500+", "60%"]

    def test_prose_with_no_numbers_yields_nothing(self):
        assert facts.extract_numerics("Built a caching layer for the API.") == []


class TestNamedFactExtraction:
    """Concrete names the resume's own fields do not list."""

    def test_a_versioned_standard(self):
        assert "OAuth 2.0" in facts.extract_named_facts("Implemented OAuth 2.0 flows.")

    def test_a_multi_word_product_name(self):
        assert "Triage Studio" in facts.extract_named_facts("Shipped Triage Studio to production.")

    def test_a_three_word_protocol_name(self):
        found = facts.extract_named_facts("Adopted Model Context Protocol for tooling.")
        assert "Model Context Protocol" in found

    def test_a_sentence_initial_capital_is_not_a_named_fact(self):
        assert facts.extract_named_facts("Built a caching layer.") == []

    def test_a_capitalised_verb_mid_sentence_is_not_a_named_fact(self):
        assert facts.extract_named_facts("The team Built a caching layer.") == []


class TestProtectedFactExtraction:
    """The two classes, gathered together from one bullet."""

    def test_numbers_and_technologies_are_both_collected(self):
        bullet = "Built Redis caching with Spring Boot, cutting API latency by 40%."
        found = facts.extract_protected_facts(bullet, _lexicon())
        assert "40%" in found.numerics
        assert "Redis" in found.terms
        assert "Spring Boot" in found.terms

    def test_a_named_fact_outside_the_lexicon_is_still_collected(self):
        bullet = "Implemented OAuth 2.0 across the platform for every client."
        found = facts.extract_protected_facts(bullet, _lexicon())
        assert "OAuth 2.0" in found.terms

    def test_a_bullet_with_nothing_concrete_protects_nothing(self):
        found = facts.extract_protected_facts("Improved the process for the team.", _lexicon())
        assert found.is_empty()

    def test_extraction_is_deterministic(self):
        bullet = "Built Redis caching with Spring Boot, cutting API latency by 40%."
        first = facts.extract_protected_facts(bullet, _lexicon())
        second = facts.extract_protected_facts(bullet, _lexicon())
        assert first == second


class TestVerificationAccepts:
    """What must pass, or the engine rejects everything and raises."""

    def test_an_unchanged_bullet_verifies(self):
        bullet = "Built Redis caching with Spring Boot, cutting API latency by 40%."
        assert facts.verify(facts.extract_protected_facts(bullet, _lexicon()), bullet) == []

    def test_a_metric_kept_exactly_is_accepted(self):
        assert facts.verify(ProtectedFacts(numerics=["40%"]), "Cut latency 40%.") == []

    def test_a_technology_kept_exactly_is_accepted(self):
        assert facts.verify(ProtectedFacts(terms=["Redis"]), "Built Redis caching.") == []

    def test_a_case_change_on_a_term_is_accepted(self):
        found = ProtectedFacts(numerics=["40%"], terms=["API Latency"])
        assert facts.verify(found, "Cut API latency 40%.") == []

    def test_a_spacing_change_on_a_unit_is_accepted(self):
        assert facts.verify(ProtectedFacts(numerics=["30 ms"]), "Replied in 30ms.") == []

    def test_a_genuinely_shorter_bullet_verifies(self):
        original = (
            "Built a Redis caching layer in front of the Spring Boot service, "
            "which reduced API latency by 40% for end users."
        )
        found = facts.extract_protected_facts(original, _lexicon())
        assert facts.verify(found, "Built Redis caching for Spring Boot, cutting API latency 40%.") == []


class TestVerificationRejects:
    """Every failure the task doc names."""

    def test_a_changed_metric_is_rejected(self):
        reasons = facts.verify(ProtectedFacts(numerics=["40%"]), "Cut latency 50%.")
        assert any("40%" in r for r in reasons)

    def test_a_changed_metric_also_reads_as_a_fabrication(self):
        reasons = facts.verify(ProtectedFacts(numerics=["40%"]), "Cut latency 50%.")
        assert any("fabricated" in r for r in reasons)

    def test_a_missing_metric_is_rejected(self):
        assert facts.verify(ProtectedFacts(numerics=["40%"]), "Cut latency notably.") != []

    def test_a_fabricated_metric_is_rejected(self):
        reasons = facts.verify(ProtectedFacts(numerics=[]), "Cut latency by 40%.")
        assert any("fabricated" in r for r in reasons)

    def test_a_generalised_technology_is_rejected(self):
        reasons = facts.verify(ProtectedFacts(terms=["Redis"]), "Built caching for the API.")
        assert any("Redis" in r for r in reasons)

    def test_a_generalised_framework_is_rejected(self):
        reasons = facts.verify(ProtectedFacts(terms=["Spring Boot"]), "Built a framework service.")
        assert any("Spring Boot" in r for r in reasons)

    def test_a_generalised_named_feature_is_rejected(self):
        reasons = facts.verify(ProtectedFacts(terms=["OAuth 2.0"]), "Implemented authentication.")
        assert any("OAuth 2.0" in r for r in reasons)

    def test_keeping_only_half_a_two_word_term_is_rejected(self):
        reasons = facts.verify(ProtectedFacts(terms=["Spring Boot"]), "Built the Spring service.")
        assert any("Spring Boot" in r for r in reasons)

    def test_every_violation_is_reported_at_once(self):
        found = ProtectedFacts(numerics=["40%"], terms=["Redis", "Spring Boot"])
        assert len(facts.verify(found, "Improved things.")) == 3


class TestBoundaries:
    """Substring matching is where a naive verifier goes wrong."""

    def test_a_larger_number_does_not_satisfy_a_smaller_one(self):
        assert facts.verify(ProtectedFacts(numerics=["40%"]), "Grew usage 140%.") != []

    def test_a_term_inside_a_longer_word_does_not_count(self):
        assert facts.verify(ProtectedFacts(terms=["Java"]), "Wrote JavaScript modules.") != []

    def test_punctuation_around_a_term_still_matches(self):
        assert facts.verify(ProtectedFacts(terms=["Redis"]), "Used (Redis) for caching.") == []

    def test_a_term_carrying_punctuation_matches(self):
        assert facts.verify(ProtectedFacts(terms=["Node.js"]), "Built Node.js services.") == []
