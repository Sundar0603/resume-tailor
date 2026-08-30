"""
Determinism and purity.

Running the gate twice against the same artifacts must produce equivalent
results. The gate must not use randomness, modify artifacts, call an LLM or
depend on external services.
"""

import ast
import pathlib

from src.quality import QualityGate, QualityIssueCode
from src.quality.models import QualityGateResult

from .conftest import (
    FakeExtractor,
    make_compilation_result,
    make_line,
    make_log,
    make_page,
    make_rule,
    write_log,
)

SOURCE_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "quality"


def build(tmp_path, log_text=None):
    path = write_log(tmp_path, log_text or make_log(pages=2, overfull=[2.0, 9.0]))
    pages = [
        make_page([make_line(), make_line(baseline=696.0)], rules=[make_rule()]),
        make_page([make_line(page=2)], page_number=2),
    ]
    gate = QualityGate(extractor=FakeExtractor(pages))
    return gate, path


class TestDeterminism:
    def test_two_evaluations_are_equal(self, tmp_path):
        gate, path = build(tmp_path)
        result = make_compilation_result(path)
        first = gate.evaluate("r.pdf", "r.tex", result)
        second = gate.evaluate("r.pdf", "r.tex", result)
        assert first == second

    def test_issue_ordering_is_stable(self, tmp_path):
        gate, path = build(tmp_path)
        result = make_compilation_result(path)
        first = gate.evaluate("r.pdf", "r.tex", result)
        second = gate.evaluate("r.pdf", "r.tex", result)
        assert [i.code for i in first.issues] == [i.code for i in second.issues]

    def test_the_result_carries_no_timing_field(self):
        # CompilationResult has duration_seconds; this one must not, because a
        # wall-clock value would break `first == second` on every run.
        assert "duration_seconds" not in QualityGateResult.model_fields


class TestPurity:
    def test_the_artifacts_are_not_modified(self, tmp_path):
        gate, path = build(tmp_path)
        before = pathlib.Path(path).read_bytes()
        gate.evaluate("r.pdf", "r.tex", make_compilation_result(path))
        assert pathlib.Path(path).read_bytes() == before

    def test_the_gate_writes_no_files(self, tmp_path):
        gate, path = build(tmp_path)
        before = sorted(p.name for p in tmp_path.iterdir())
        gate.evaluate("r.pdf", "r.tex", make_compilation_result(path))
        assert sorted(p.name for p in tmp_path.iterdir()) == before


class TestNoLLM:
    def test_the_package_imports_no_provider(self):
        # The gate is the termination test for the revision loop; a component
        # that decides when to stop cannot be non-deterministic.
        forbidden = ("src.providers", "src.analyzer", "src.planner", "src.generator")
        for path in SOURCE_DIR.glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert not node.module.startswith(forbidden), (
                        "{0} imports {1}".format(path.name, node.module)
                    )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not alias.name.startswith(forbidden), (
                            "{0} imports {1}".format(path.name, alias.name)
                        )

    def test_the_package_makes_no_network_calls(self):
        forbidden = ("requests", "urllib", "http", "socket", "openai", "anthropic")
        for path in SOURCE_DIR.glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name.split(".")[0] not in forbidden
                elif isinstance(node, ast.ImportFrom) and node.module:
                    assert node.module.split(".")[0] not in forbidden
