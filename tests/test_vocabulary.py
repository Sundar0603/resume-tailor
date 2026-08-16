"""
Tests for the "is this term too general to be worth a swap" judgement.

The rule is a conjunction: a phrase is refused only when *every* significant
word in it is generic. That is what makes it lenient — one specific word
anywhere saves the phrase.

The examples below are real. The "too general" ones came out of an actual
generation against a corporate competency-framework job description; the
specific ones came out of a real product job description and out of the source
resume. Both sets should keep passing.
"""

import pytest

from src.vocabulary import (
    GENERIC_TERMS,
    decapitalise_mid_sentence,
    is_too_general,
    normalise,
    normalised_set,
)


class TestTooGeneral:
    @pytest.mark.parametrize(
        "phrase",
        [
            # A job description's own section headings, extracted as "domains".
            "Application Software Development",
            "Development Operations",
            "Issue/Defect Collaboration",
            "Practices and Standards Compliance",
            "Software Development and Coding",
            "System Maintenance",
            # Phrases a model wrote into a domains field.
            "Code Quality",
            "Defect Handling",
            "Production Support",
            "Software Testing",
            "Secure Coding Standards",
            "Architectural Guidelines",
            "App Services",
            # Single generic words.
            "Debugging",
            "Troubleshooting",
        ],
    )
    def test_process_language_is_refused(self, phrase):
        assert is_too_general(phrase) is True

    @pytest.mark.parametrize(
        "phrase",
        [
            # From the source resume.
            "SOC Platforms",
            "Rule Management",
            "Workflow Automation",
            "Caching",
            "API Design",
            "SOC",
            "Deployment",
            "Data Retention",
            # From the resume schema's own examples.
            "Threat Intelligence",
            "Firewall Security",
            "Malware Analysis",
            "SOC Automation",
            # Real domains a real job description asked for.
            "sales territory planning",
            "quota management",
            "compensation systems",
            "Go-to-Market (GTM) planning",
            "Sales Planning",
            "performance management",
            # Near-misses that must survive on one specific word.
            "Web Services",
            "Financial Services",
            "Application Security",
            "Production Planning",
            "Data Handling",
            "Payments",
            "Observability",
            "Distributed Systems",
        ],
    )
    def test_subject_matter_survives(self, phrase):
        assert is_too_general(phrase) is False

    def test_one_specific_word_saves_a_phrase(self):
        # This is the whole design: the rule is a conjunction, not a
        # disjunction, so the filter stays lenient.
        assert is_too_general("Software Development") is True
        assert is_too_general("Payments Software Development") is False

    def test_stopwords_neither_save_nor_condemn(self):
        assert is_too_general("Practices and Standards") is True
        assert is_too_general("Standards of Payments") is False

    def test_slash_and_ampersand_are_separators(self):
        assert is_too_general("Issue/Defect") is True
        assert is_too_general("Testing & Quality") is True
        assert is_too_general("Testing & Payments") is False

    def test_case_and_whitespace_are_ignored(self):
        assert is_too_general("  APPLICATION   SOFTWARE  ") is True

    def test_empty_input_is_not_refused(self):
        # Nothing to judge. Emptiness is the caller's problem, not this rule's.
        assert is_too_general("") is False
        assert is_too_general("   ") is False


class TestGenericTermsList:
    @pytest.mark.parametrize(
        "word",
        ["design", "automation", "deployment", "data", "workflow", "rule", "security", "caching"],
    )
    def test_anchor_words_are_deliberately_excluded(self, word):
        # Each of these can head a genuine domain. Adding one to the list
        # would delete a real domain, which is a worse failure than leaving a
        # vague one in place.
        assert word not in GENERIC_TERMS


class TestHelpers:
    def test_normalise_lowercases_and_collapses(self):
        assert normalise("  SOC   Platforms ") == "soc platforms"

    def test_normalise_tolerates_non_strings(self):
        assert normalise(None) == ""

    def test_normalised_set_drops_blanks(self):
        assert normalised_set(["SOC", "  ", ""]) == {"soc"}


class TestDecapitalisation:
    """
    Job-description vocabulary worked into prose comes back Capitalised.
    Lowercasing it is safe only because the rule is keyed to GENERIC_TERMS —
    a real proper noun is never in that set.
    """

    def test_process_phrases_are_lowercased(self):
        assert decapitalise_mid_sentence(
            "Ensured Code Quality across the service."
        ) == "Ensured code quality across the service."

    def test_acronyms_are_never_touched(self):
        text = "Designed REST APIs with JWT on OCI."
        assert decapitalise_mid_sentence(text) == text

    def test_proper_nouns_are_never_touched(self):
        text = "Built services in Java, Redis and MySQL at Zoho using Spring Boot."
        assert decapitalise_mid_sentence(text) == text

    def test_an_unknown_technology_is_never_touched(self):
        # Terraform is in no vocabulary the project holds; lowercasing it would
        # read as a typo.
        text = "Automated provisioning with Terraform, cutting deploy time by 60%."
        assert decapitalise_mid_sentence(text) == text

    def test_a_sentence_start_keeps_its_capital(self):
        assert decapitalise_mid_sentence(
            "Software testing was thorough."
        ) == "Software testing was thorough."

    def test_a_capital_after_a_full_stop_is_kept(self):
        assert decapitalise_mid_sentence(
            "Shipped it. Code Quality was maintained."
        ) == "Shipped it. Code quality was maintained."

    def test_a_whole_run_moves_together(self):
        # Lowercasing half a run leaves "system Design", which reads worse than
        # leaving it alone — so one generic word carries the whole phrase.
        assert decapitalise_mid_sentence(
            "Applied System Design principles."
        ) == "Applied system design principles."

    def test_a_run_with_no_generic_word_is_left_alone(self):
        text = "Deployed on Oracle Cloud Infrastructure last quarter."
        assert decapitalise_mid_sentence(text) == text

    def test_a_leading_run_lowercases_all_but_the_first_word(self):
        assert decapitalise_mid_sentence(
            "Application Software Development professional."
        ) == "Application software development professional."

    def test_non_strings_and_blanks_pass_through(self):
        assert decapitalise_mid_sentence("") == ""
        assert decapitalise_mid_sentence(None) is None
