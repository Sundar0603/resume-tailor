"""
What the Retriever must *not* do.

Task 020 §12 lists the prohibitions explicitly: retrieval does not generate,
rewrite, decide, render or compile. §30 adds that the Knowledge Base is a
read-only input and that the LLM may never mutate it.

Those are architectural claims, and an architectural claim that nothing checks
becomes folklore. These tests check them where they can actually be broken —
in the imports — following ``tests/report/test_the_package_makes_no_llm_call``
and ``tests/revision/test_floors.py``'s "single home" test.
"""

from pathlib import Path

import pytest

from src.retrieval import selection

PACKAGE = Path("src/retrieval")

#: Importing any of these would mean the package had grown a capability it is
#: forbidden to have.
FORBIDDEN_IMPORTS = (
    "provider",
    "prompts",
    "sampling",
    "subprocess",
    "src.generator",
    "src.planner",
    "src.renderer",
    "src.compiler",
    "src.quality",
    "src.revision",
    "src.report",
    "src.cli",
)


def source_files():
    return sorted(PACKAGE.glob("*.py"))


def import_lines(path: Path):
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith(("import ", "from "))
    ]


class TestTheFixtureIsNotVacuous:
    def test_the_package_has_source_files(self):
        assert len(source_files()) >= 6

    def test_those_files_have_imports(self):
        assert any(import_lines(path) for path in source_files())


class TestTheRetrieverMakesNoLLMCall:
    @pytest.mark.parametrize("path", source_files(), ids=lambda p: p.name)
    def test_no_forbidden_import(self, path):
        for line in import_lines(path):
            for forbidden in FORBIDDEN_IMPORTS:
                assert forbidden not in line, (path.name, line)

    def test_the_retriever_takes_no_provider(self):
        """
        Every other orchestrator in this project is constructed with a
        provider. This one declares no constructor at all, which is the
        strongest form the "no LLM" rule can take: there is nowhere to inject
        one.
        """
        from src.retrieval import KnowledgeBaseRetriever

        assert "__init__" not in vars(KnowledgeBaseRetriever)

    def test_retrieve_takes_only_data(self):
        import inspect

        from src.retrieval import KnowledgeBaseRetriever

        parameters = list(
            inspect.signature(KnowledgeBaseRetriever.retrieve).parameters
        )
        assert parameters == ["self", "knowledge_base", "job_analysis"]


class TestTheRetrieverWritesNothing:
    @pytest.mark.parametrize("path", source_files(), ids=lambda p: p.name)
    def test_no_file_writing(self, path):
        body = path.read_text(encoding="utf-8")
        for forbidden in ("write_text(", "open(", "mkdir(", "shutil"):
            assert forbidden not in body, (path.name, forbidden)


class TestSelectionConstantsHaveASingleHome:
    """
    Mirrors ``tests/revision/test_floors.py``. A constant defined twice drifts,
    and a budget that drifts silently changes what every run is allowed to use.
    """

    CONSTANTS = (
        "FULL_TIME_HIGHLIGHTS",
        "INTERNSHIP_HIGHLIGHTS",
        "MAX_PROJECTS",
        "MIN_PROJECTS",
        "MAX_PROJECT_HIGHLIGHTS",
        "MAX_SKILL_CATEGORIES",
        "DUPLICATE_THRESHOLD",
        "SKILL_SUBSUMPTION_THRESHOLD",
    )

    @pytest.mark.parametrize("name", CONSTANTS)
    def test_defined_only_in_selection(self, name):
        definition = "{0} = ".format(name)
        owners = [
            path.name
            for path in source_files()
            if definition in path.read_text(encoding="utf-8")
        ]
        assert owners == ["selection.py"], (name, owners)

    @pytest.mark.parametrize("name", CONSTANTS)
    def test_the_constant_exists(self, name):
        assert hasattr(selection, name)


class TestBudgetsNestAboveTheFloorsBelowThem:
    """
    The three layers must nest, or a resume arrives already below a floor the
    Revision Engine is supposed to defend (PROJECT_KNOWLEDGE §10h records that
    happening when generation did not know about them).
    """

    def test_full_time_budget_is_at_least_the_revision_floor(self):
        from src.revision import floors

        assert selection.FULL_TIME_HIGHLIGHTS >= floors.FULLTIME_BULLET_FLOOR

    def test_internship_budget_is_at_least_the_revision_floor(self):
        from src.revision import floors

        assert selection.INTERNSHIP_HIGHLIGHTS >= floors.INTERNSHIP_BULLET_FLOOR

    def test_projects_selected_is_at_least_the_validator_minimum(self):
        assert selection.MAX_PROJECTS >= selection.MIN_PROJECTS

    def test_experience_budget_is_within_the_validator_ceiling(self):
        from src.validation.validator import _MAX_EXPERIENCE_HIGHLIGHTS

        assert selection.FULL_TIME_HIGHLIGHTS <= _MAX_EXPERIENCE_HIGHLIGHTS

    def test_project_budget_is_within_the_validator_ceiling(self):
        from src.validation.validator import _MAX_PROJECT_HIGHLIGHTS

        assert selection.MAX_PROJECT_HIGHLIGHTS <= _MAX_PROJECT_HIGHLIGHTS


class TestTheProjectMinimumAgreesEverywhere:
    """
    ``MIN_PROJECTS`` is stated in three places for three different layers:
    the Validator enforces it, the Revision Engine refuses to trim below it,
    and retrieval refuses to hand over a Knowledge Base that cannot meet it.

    One number in three files is how a floor silently stops covering the rule
    it exists for. Asserting agreement is cheaper than plumbing an import
    across three packages in the wrong dependency direction.
    """

    def test_retrieval_agrees_with_the_revision_floor(self):
        from src.revision import floors

        assert selection.MIN_PROJECTS == floors.MIN_PROJECTS

    def test_retrieval_agrees_with_the_validator(self):
        from src.validation.validator import _MIN_PROJECT_COUNT

        assert selection.MIN_PROJECTS == _MIN_PROJECT_COUNT
