"""
Test doubles and factories for the Revision Engine.

No ``unittest.mock`` — the suite has never used it. Every double is a
hand-written class, and the provider doubles subclass the real
:class:`~src.analyzer.provider.LLMProvider` ABC, the same way
``tests/planner/conftest.py`` and ``tests/pipeline/conftest.py`` do.

The interesting one is :class:`CountingGate`. Every other component in this
project could be faked with canned data, but a *convergence loop* cannot: it
needs a verdict that actually responds to the resume getting smaller, or the
test proves nothing. There is no compiler in the repo that succeeds without a
TeX distribution — ``tests/pipeline/test_end_to_end.py::_never_compiles`` fakes
only a failing engine — so this file supplies the missing half.

The pairing is faithful rather than convenient: :class:`StubCompiler` writes the
**real** rendered LaTeX to disk, and :class:`CountingGate` counts the **real**
macros in it. Nothing tells the gate what the resume contained; it reads what
the renderer actually produced, so a renderer change that stopped emitting
bullets would break these tests rather than sail past them.
"""

import copy
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.analyzer.provider import LLMProvider
from src.compiler.models import CompilationResult
from src.parser.models import (
    Contact,
    Education,
    EntitySource,
    Experience,
    Metadata,
    Project,
    Resume,
    SkillCategory,
)
from src.revision.measure import estimated_lines
from src.quality.models import (
    QualityGateResult,
    QualityIssue,
    QualityIssueCode,
    QualityMetrics,
    QualitySeverity,
    QualityStage,
)

#: Words used to pad a bullet to a chosen length. Deliberately plain: these
#: must not look like protected facts to :mod:`src.revision.facts`.
_FILLER = "and then the team worked on the thing across the system for a while longer"


def make_bullet(lead: str, words: int) -> str:
    """Return a bullet of roughly ``words`` words, starting with ``lead``."""
    tokens = lead.split()
    filler = _FILLER.split()
    while len(tokens) < words:
        tokens.extend(filler[: words - len(tokens)])
    return " ".join(tokens[:words]) + "."


def make_resume(
    project_bullets=(4, 4),
    fulltime_bullets: int = 6,
    intern_bullets: int = 3,
    skill_sizes=(4, 4, 4),
    bullet_words: int = 10,
    template: str = "cybersecurity",
) -> Resume:
    """
    Build a resume with an exactly known shape.

    Every count the retention floors care about is a parameter, so a test can
    construct precisely the situation it means to exercise rather than trimming
    a fixture down to it.

    ``bullet_words`` at 10 keeps every bullet on one rendered line; raise it
    past 15 to make bullets eligible for compression.
    """
    projects = [
        Project(
            id="proj_{0:03d}".format(index + 1),
            source=EntitySource.CANONICAL,
            name="Project {0}".format(index + 1),
            type="Personal",
            technologies=["Redis", "Docker"],
            domains=["Backend Development"],
            highlights=[
                make_bullet("Built component {0} of project {1}".format(n + 1, index + 1), bullet_words)
                for n in range(count)
            ],
        )
        for index, count in enumerate(project_bullets)
    ]

    experiences = [
        Experience(
            id="exp_001",
            company="Acme Corp",
            role="Backend Engineer",
            employment_type="Full Time",
            duration="2023 - Present",
            location="Chennai",
            technologies=["Java"],
            domains=["Backend Development"],
            highlights=[
                make_bullet("Delivered full-time item {0}".format(n + 1), bullet_words)
                for n in range(fulltime_bullets)
            ],
        ),
        Experience(
            id="exp_002",
            company="Beta Labs",
            role="Intern",
            employment_type="Internship",
            duration="2022 - 2023",
            location="Chennai",
            technologies=["Python"],
            domains=["Automation"],
            highlights=[
                make_bullet("Delivered internship item {0}".format(n + 1), bullet_words)
                for n in range(intern_bullets)
            ],
        ),
    ]

    skills = [
        SkillCategory(
            id="skill_{0:03d}".format(index + 1),
            category="Category {0}".format(index + 1),
            skills=["Skill {0}{1}".format(index + 1, n + 1) for n in range(count)],
        )
        for index, count in enumerate(skill_sizes)
    ]

    return copy.deepcopy(
        Resume(
            metadata=Metadata(resume="test", template=template, version="1.0"),
            contact=Contact(
                name="Test Candidate",
                phone="+91 00000 00000",
                email="test@example.com",
                linkedin="linkedin.com/in/test",
                github="github.com/test",
            ),
            summary="A backend engineer with experience building services and APIs.",
            skills=skills,
            experiences=experiences,
            projects=projects,
            education=[
                Education(
                    id="edu_001",
                    institution="Test University",
                    degree="B.E.",
                    major="Computer Science",
                    duration="2019 - 2023",
                )
            ],
        )
    )


# ----------------------------------------------------------------------
# Compiler and gate doubles
# ----------------------------------------------------------------------


class StubCompiler:
    """
    A compiler that writes real artifacts without needing a TeX distribution.

    The ``.tex`` it writes is the renderer's genuine output, which is what
    makes :class:`CountingGate` a real measurement rather than a canned answer.
    The ``.pdf`` is a minimal file carrying the magic bytes, because nothing
    downstream of here opens it.
    """

    def __init__(self) -> None:
        self.calls = 0

    def compile(
        self,
        latex_source: str,
        output_directory: str = "output/compile",
        job_name: str = "resume",
    ) -> CompilationResult:
        """Write ``{job_name}.tex``, ``.pdf`` and ``.log`` and report success."""
        self.calls += 1
        directory = Path(output_directory)
        directory.mkdir(parents=True, exist_ok=True)

        tex = directory / "{0}.tex".format(job_name)
        pdf = directory / "{0}.pdf".format(job_name)
        log = directory / "{0}.log".format(job_name)
        tex.write_text(latex_source, encoding="utf-8")
        pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
        log.write_text("Output written on {0}.pdf (1 page).\n".format(job_name), encoding="utf-8")

        return CompilationResult(
            pdf_path=str(pdf),
            log_path=str(log),
            tex_path=str(tex),
            engine="stub",
            exit_code=0,
            duration_seconds=0.0,
        )


def _macro_arguments(body: str, macro: str) -> List[str]:
    """Return the brace-matched argument of every ``macro`` occurrence in ``body``."""
    arguments = []  # type: List[str]
    start = body.find(macro)
    while start != -1:
        cursor = start + len(macro)
        depth = 1
        while cursor < len(body) and depth:
            if body[cursor] == "{":
                depth += 1
            elif body[cursor] == "}":
                depth -= 1
            cursor += 1
        arguments.append(body[start + len(macro) : cursor - 1])
        start = body.find(macro, cursor)
    return arguments


_LATEX_NOISE = re.compile(r"\\[A-Za-z]+\*?|[{}$&%#_~^\\]")


def _plain(text: str) -> str:
    """Strip LaTeX markup so the remainder can be measured as body text."""
    return _LATEX_NOISE.sub("", text).strip()


def rendered_rows(latex: str) -> int:
    """
    Return how many rendered lines the LaTeX body is expected to occupy.

    Measures the **text**, not the macro count. That distinction is the whole
    point: a gate that counted ``\resumeItem`` occurrences would be blind to
    compression, since shortening a bullet leaves the macro exactly where it
    was — and a convergence test using it would report the compression path as
    broken when it was working.

    Only the document body is measured; the preamble defines ``\resumeItem``
    and would otherwise count as content.
    """
    body = latex.split(r"\begin{document}")[-1]

    rows = 0
    for argument in _macro_arguments(body, r"\resumeItem{"):
        rows += estimated_lines(_plain(argument))
    for line in body.splitlines():
        if r"\textbf{\normalsize{" in line:
            rows += estimated_lines(_plain(line))
    return rows



class CountingGate:
    """
    A Quality Gate whose verdict responds to the resume shrinking.

    Reads the ``.tex`` the compiler wrote, counts its content rows, and calls
    anything above ``capacity`` overflow. That is a crude model of page
    fitting — the real gate measures a compiled PDF — but it is *monotone in
    content*, which is the only property a convergence test needs and the one
    property a canned result cannot have.
    """

    def __init__(self, capacity: int, issue_code: QualityIssueCode = QualityIssueCode.INVALID_PAGE_COUNT) -> None:
        self.capacity = capacity
        self.calls = 0
        self.rows_seen = []  # type: List[int]
        self._issue_code = issue_code

    def evaluate(self, pdf_path: str, latex_path: str, compiler_result) -> QualityGateResult:
        """Judge the rendered LaTeX at ``latex_path``."""
        self.calls += 1
        rows = rendered_rows(Path(latex_path).read_text(encoding="utf-8"))
        self.rows_seen.append(rows)
        return self.verdict(rows)

    def verdict(self, rows: int) -> QualityGateResult:
        """Return the verdict for a given row count."""
        spill = max(0, rows - self.capacity)
        pages = 1 if spill == 0 else 2
        issues = []  # type: List[QualityIssue]
        if spill:
            issues.append(
                QualityIssue(
                    code=self._issue_code,
                    severity=QualitySeverity.ERROR,
                    stage=QualityStage.STAGE_1,
                    message="expected 1 page, found {0}".format(pages),
                    magnitude=float(pages),
                )
            )
        return QualityGateResult(
            passed=not issues,
            stage_reached=QualityStage.STAGE_2,
            issues=issues,
            metrics=QualityMetrics(
                page_count=pages,
                overfull_hbox_count=0,
                max_overfull_points=0.0,
                missing_glyph_count=0,
                overlap_count=0,
                orphan_word_count=0,
                rule_collision_count=0,
                bullet_spacing_anomaly_count=0,
                total_text_lines=rows,
                overflow_line_count=spill,
                overflow_height_points=float(spill) * 13.55,
            ),
        )


def passing_result() -> QualityGateResult:
    """Return a verdict that clears the gate, orphan warnings and all."""
    return QualityGateResult(
        passed=True,
        stage_reached=QualityStage.STAGE_2,
        issues=[
            QualityIssue(
                code=QualityIssueCode.ORPHAN_WORD,
                severity=QualitySeverity.WARNING,
                stage=QualityStage.STAGE_2,
                message="Orphan word on page 1: 'validation.'",
                page=1,
                line_text="validation.",
            )
        ],
        metrics=QualityMetrics(
            page_count=1,
            overfull_hbox_count=0,
            max_overfull_points=0.0,
            missing_glyph_count=0,
            overlap_count=0,
            orphan_word_count=1,
            rule_collision_count=0,
            bullet_spacing_anomaly_count=0,
            total_text_lines=60,
            overflow_line_count=0,
            overflow_height_points=0.0,
        ),
    )


def failing_result(spill: int = 8) -> QualityGateResult:
    """Return a verdict that fails on page count, with ``spill`` lines over."""
    return QualityGateResult(
        passed=False,
        stage_reached=QualityStage.STAGE_2,
        issues=[
            QualityIssue(
                code=QualityIssueCode.INVALID_PAGE_COUNT,
                severity=QualitySeverity.ERROR,
                stage=QualityStage.STAGE_1,
                message="expected 1 page, found 2",
                magnitude=2.0,
            )
        ],
        metrics=QualityMetrics(
            page_count=2,
            overfull_hbox_count=0,
            max_overfull_points=0.0,
            missing_glyph_count=0,
            overlap_count=0,
            orphan_word_count=0,
            rule_collision_count=0,
            bullet_spacing_anomaly_count=0,
            total_text_lines=70 + spill,
            overflow_line_count=spill,
            overflow_height_points=float(spill) * 13.55,
        ),
    )


# ----------------------------------------------------------------------
# Provider doubles
# ----------------------------------------------------------------------


class ScriptedCompressor(LLMProvider):
    """
    Returns a canned reply, and records every call.

    ``replies`` are consumed in order; the last one repeats once exhausted, so
    a multi-pass test does not have to predict how many passes will happen.
    """

    def __init__(self, replies: List[str]) -> None:
        self.replies = list(replies)
        self.prompts = []  # type: List[str]
        self.options = []  # type: List[Optional[Dict[str, Any]]]

    def generate(self, prompt: str, options: Optional[Dict[str, Any]] = None) -> str:
        """Record the request and return the next scripted reply."""
        self.prompts.append(prompt)
        self.options.append(options)
        index = min(len(self.prompts) - 1, len(self.replies) - 1)
        return self.replies[index]

    @property
    def calls(self) -> int:
        """Return how many times the provider was asked to generate."""
        return len(self.prompts)


class ExplodingProvider(LLMProvider):
    """Fails if it is ever called. Proves the deterministic path used no LLM."""

    def generate(self, prompt: str, options: Optional[Dict[str, Any]] = None) -> str:
        """Always raise."""
        raise AssertionError("the provider must not be called on this path")
